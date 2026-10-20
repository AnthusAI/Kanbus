#![allow(dead_code)]

use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc,
};
use virtuus_store::{
    FileStore, ObjectPage, ObjectStore, Scope, StoreError, StoredObject, WriteCondition,
};

/// Native quoted revisions and accessor counters for integration regressions.
pub struct InspectStore {
    /// Real portable filesystem backend.
    pub inner: FileStore,
    /// Canonical issue read attempts.
    pub issue_reads: AtomicUsize,
    /// Canonical event read attempts.
    pub event_reads: AtomicUsize,
    /// Calls using the raw unbounded accessor.
    pub unbounded_reads: AtomicUsize,
}

impl InspectStore {
    /// Wrap a backend without changing its stored bytes.
    pub fn new(inner: FileStore) -> Arc<Self> {
        Arc::new(Self {
            inner,
            issue_reads: AtomicUsize::new(0),
            event_reads: AtomicUsize::new(0),
            unbounded_reads: AtomicUsize::new(0),
        })
    }
}

fn quoted(mut object: StoredObject) -> StoredObject {
    object.revision = format!("\"{}\"", object.revision);
    object
}

fn native(revision: &str) -> virtuus_store::Result<String> {
    if !revision.starts_with('"') || !revision.ends_with('"') {
        return Err(StoreError::Invalid(
            "Backend requires original quoted revision".into(),
        ));
    }
    Ok(revision.trim_matches('"').to_string())
}

#[async_trait::async_trait]
impl ObjectStore for InspectStore {
    async fn get(&self, scope: &Scope, path: &str) -> virtuus_store::Result<Option<StoredObject>> {
        self.unbounded_reads.fetch_add(1, Ordering::Relaxed);
        if path.contains("/issues/") {
            self.issue_reads.fetch_add(1, Ordering::Relaxed);
        }
        if path.contains("/events/") {
            self.event_reads.fetch_add(1, Ordering::Relaxed);
        }
        Ok(self.inner.get(scope, path).await?.map(quoted))
    }
    async fn get_bounded(
        &self,
        scope: &Scope,
        path: &str,
        max_bytes: usize,
    ) -> virtuus_store::Result<Option<StoredObject>> {
        if path.contains("/issues/") {
            self.issue_reads.fetch_add(1, Ordering::Relaxed);
        }
        if path.contains("/events/") {
            self.event_reads.fetch_add(1, Ordering::Relaxed);
        }
        Ok(self
            .inner
            .get_bounded(scope, path, max_bytes)
            .await?
            .map(quoted))
    }
    async fn list(
        &self,
        scope: &Scope,
        prefix: &str,
        cursor: Option<&str>,
        limit: usize,
    ) -> virtuus_store::Result<ObjectPage> {
        self.inner.list(scope, prefix, cursor, limit).await
    }
    async fn put(
        &self,
        scope: &Scope,
        path: &str,
        bytes: &[u8],
        content_type: &str,
        condition: WriteCondition,
        operation_id: Option<&str>,
    ) -> virtuus_store::Result<StoredObject> {
        let condition = match condition {
            WriteCondition::Revision(revision) => WriteCondition::Revision(native(&revision)?),
            condition => condition,
        };
        self.inner
            .put(scope, path, bytes, content_type, condition, operation_id)
            .await
            .map(quoted)
    }
    async fn delete(
        &self,
        scope: &Scope,
        path: &str,
        expected_revision: &str,
    ) -> virtuus_store::Result<()> {
        self.inner
            .delete(scope, path, &native(expected_revision)?)
            .await
    }
    async fn get_control(
        &self,
        scope: &Scope,
        path: &str,
    ) -> virtuus_store::Result<Option<StoredObject>> {
        self.inner.get_control(scope, path).await
    }
    async fn put_control(
        &self,
        scope: &Scope,
        path: &str,
        bytes: &[u8],
        condition: WriteCondition,
    ) -> virtuus_store::Result<StoredObject> {
        self.inner.put_control(scope, path, bytes, condition).await
    }
    async fn list_control(
        &self,
        scope: &Scope,
        prefix: &str,
        cursor: Option<&str>,
        limit: usize,
    ) -> virtuus_store::Result<ObjectPage> {
        self.inner.list_control(scope, prefix, cursor, limit).await
    }
    async fn delete_control(
        &self,
        scope: &Scope,
        path: &str,
        expected_revision: &str,
    ) -> virtuus_store::Result<()> {
        self.inner
            .delete_control(scope, path, expected_revision)
            .await
    }
}

/// Which backend call a pause hook waits for.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum PausePoint {
    /// Immediately after a successful canonical or control write.
    AfterPut,
    /// Immediately before a canonical or control write is attempted.
    BeforePut,
}

struct PauseHook {
    point: PausePoint,
    path_contains: String,
    reached: tokio::sync::oneshot::Sender<()>,
    resume: tokio::sync::oneshot::Receiver<()>,
}

/// Filesystem backend that can hold one in-flight write at a chosen point so a test
/// can run another complete operation in the gap, making interleavings deterministic.
pub struct PauseStore {
    inner: FileStore,
    hooks: std::sync::Mutex<Vec<PauseHook>>,
}

/// Test-side handle for one armed pause.
pub struct PauseHandle {
    reached: tokio::sync::oneshot::Receiver<()>,
    resume: tokio::sync::oneshot::Sender<()>,
}

impl PauseHandle {
    /// Wait until a request is held at the armed point.
    pub async fn held(&mut self) {
        (&mut self.reached).await.expect("pause point was reached");
    }

    /// Let the held request continue.
    pub fn release(self) {
        let _ = self.resume.send(());
    }
}

impl PauseStore {
    /// Wrap a backend without changing its stored bytes.
    pub fn new(inner: FileStore) -> Arc<Self> {
        Arc::new(Self {
            inner,
            hooks: std::sync::Mutex::new(Vec::new()),
        })
    }

    /// Hold the next write whose path contains the given text at the given point.
    pub fn arm(&self, point: PausePoint, path_contains: &str) -> PauseHandle {
        let (reached_sender, reached) = tokio::sync::oneshot::channel();
        let (resume, resume_receiver) = tokio::sync::oneshot::channel();
        self.hooks.lock().unwrap().push(PauseHook {
            point,
            path_contains: path_contains.into(),
            reached: reached_sender,
            resume: resume_receiver,
        });
        PauseHandle { reached, resume }
    }

    async fn pause_if_armed(&self, point: PausePoint, path: &str) {
        let hook = {
            let mut hooks = self.hooks.lock().unwrap();
            hooks
                .iter()
                .position(|hook| hook.point == point && path.contains(&hook.path_contains))
                .map(|index| hooks.remove(index))
        };
        if let Some(hook) = hook {
            let _ = hook.reached.send(());
            let _ = hook.resume.await;
        }
    }
}

#[async_trait::async_trait]
impl ObjectStore for PauseStore {
    async fn get(&self, scope: &Scope, path: &str) -> virtuus_store::Result<Option<StoredObject>> {
        self.inner.get(scope, path).await
    }
    async fn get_bounded(
        &self,
        scope: &Scope,
        path: &str,
        max_bytes: usize,
    ) -> virtuus_store::Result<Option<StoredObject>> {
        self.inner.get_bounded(scope, path, max_bytes).await
    }
    async fn list(
        &self,
        scope: &Scope,
        prefix: &str,
        cursor: Option<&str>,
        limit: usize,
    ) -> virtuus_store::Result<ObjectPage> {
        self.inner.list(scope, prefix, cursor, limit).await
    }
    async fn put(
        &self,
        scope: &Scope,
        path: &str,
        bytes: &[u8],
        content_type: &str,
        condition: WriteCondition,
        operation_id: Option<&str>,
    ) -> virtuus_store::Result<StoredObject> {
        self.pause_if_armed(PausePoint::BeforePut, path).await;
        let stored = self
            .inner
            .put(scope, path, bytes, content_type, condition, operation_id)
            .await?;
        self.pause_if_armed(PausePoint::AfterPut, path).await;
        Ok(stored)
    }
    async fn delete(
        &self,
        scope: &Scope,
        path: &str,
        expected_revision: &str,
    ) -> virtuus_store::Result<()> {
        self.inner.delete(scope, path, expected_revision).await
    }
    async fn get_control(
        &self,
        scope: &Scope,
        path: &str,
    ) -> virtuus_store::Result<Option<StoredObject>> {
        self.inner.get_control(scope, path).await
    }
    async fn put_control(
        &self,
        scope: &Scope,
        path: &str,
        bytes: &[u8],
        condition: WriteCondition,
    ) -> virtuus_store::Result<StoredObject> {
        self.pause_if_armed(PausePoint::BeforePut, path).await;
        let stored = self
            .inner
            .put_control(scope, path, bytes, condition)
            .await?;
        self.pause_if_armed(PausePoint::AfterPut, path).await;
        Ok(stored)
    }
    async fn list_control(
        &self,
        scope: &Scope,
        prefix: &str,
        cursor: Option<&str>,
        limit: usize,
    ) -> virtuus_store::Result<ObjectPage> {
        self.inner.list_control(scope, prefix, cursor, limit).await
    }
    async fn delete_control(
        &self,
        scope: &Scope,
        path: &str,
        expected_revision: &str,
    ) -> virtuus_store::Result<()> {
        self.inner
            .delete_control(scope, path, expected_revision)
            .await
    }
}

/// Archive state in a folder beside a store bound to a single board.
pub fn lifecycle_beside(directory: &std::path::Path) -> kanbus_api::BoardLifecycle {
    kanbus_api::BoardLifecycle::new(
        30,
        Arc::new(FileStore::new(directory.join("archive-state")).unwrap()),
    )
    .unwrap()
}
