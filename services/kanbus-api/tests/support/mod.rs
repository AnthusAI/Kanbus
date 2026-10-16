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
}
