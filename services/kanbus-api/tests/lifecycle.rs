//! Executable examples for the board lifecycle scenarios of features/writable_api.feature.

use kanbus_api::{
    Api, ApiError, ApiRequest, ApiResponse, BoardLifecycle, Grant, Principal, ProjectGrant,
    SWEEP_BATCH_LIMIT,
};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    sync::{
        atomic::{AtomicI64, Ordering},
        Arc, Mutex,
    },
};
use tempfile::TempDir;
use virtuus_store::{
    Catalog, CatalogQuery, FileStore, JournaledStore, MemoryCatalog, ObjectPage, ObjectStore,
    Scope, StoreError, StoredObject, WriteCondition,
};

struct FlakyDeleteStore {
    inner: FileStore,
    deletes_allowed: AtomicI64,
}

impl FlakyDeleteStore {
    fn permit_deletes_then_fail(&self, count: i64) {
        self.deletes_allowed.store(count, Ordering::SeqCst);
    }

    fn stop_failing(&self) {
        self.deletes_allowed.store(i64::MAX, Ordering::SeqCst);
    }

    fn spend_delete(&self) -> virtuus_store::Result<()> {
        if self.deletes_allowed.fetch_sub(1, Ordering::SeqCst) <= 0 {
            self.deletes_allowed.store(0, Ordering::SeqCst);
            return Err(StoreError::Unavailable("injected delete failure".into()));
        }
        Ok(())
    }
}

#[async_trait::async_trait]
impl ObjectStore for FlakyDeleteStore {
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
        self.inner
            .put(scope, path, bytes, content_type, condition, operation_id)
            .await
    }
    async fn delete(
        &self,
        scope: &Scope,
        path: &str,
        expected_revision: &str,
    ) -> virtuus_store::Result<()> {
        self.spend_delete()?;
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
        self.spend_delete()?;
        self.inner
            .delete_control(scope, path, expected_revision)
            .await
    }
}

type TestClock = Arc<Mutex<chrono::DateTime<chrono::Utc>>>;

struct Harness {
    _directory: TempDir,
    api: Api,
    objects: Arc<FlakyDeleteStore>,
    catalog: Arc<MemoryCatalog>,
    clock: TestClock,
}

impl Harness {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let objects = Arc::new(FlakyDeleteStore {
            inner: FileStore::new(directory.path()).unwrap(),
            deletes_allowed: AtomicI64::new(i64::MAX),
        });
        let catalog = Arc::new(MemoryCatalog::default());
        let store = JournaledStore::new(objects.clone(), catalog.clone());
        let clock: TestClock = Arc::new(Mutex::new(chrono::Utc::now()));
        let reader = clock.clone();
        let api = Api::with_clock(
            store,
            objects.clone(),
            BoardLifecycle::new(30, objects.clone()).unwrap(),
            Arc::new(move || *reader.lock().unwrap()),
        )
        .unwrap();
        Self {
            _directory: directory,
            api,
            objects,
            catalog,
            clock,
        }
    }

    fn now(&self) -> chrono::DateTime<chrono::Utc> {
        *self.clock.lock().unwrap()
    }

    fn advance_days(&self, days: i64) {
        *self.clock.lock().unwrap() += chrono::Duration::days(days);
    }

    async fn send(
        &self,
        principal: &Principal,
        method: &str,
        path: &str,
        body: Value,
        revision: Option<&str>,
    ) -> Result<ApiResponse, ApiError> {
        self.send_with_operation(
            principal,
            method,
            path,
            body,
            revision,
            &uuid::Uuid::new_v4().to_string(),
        )
        .await
    }

    async fn send_with_operation(
        &self,
        principal: &Principal,
        method: &str,
        path: &str,
        body: Value,
        revision: Option<&str>,
        operation: &str,
    ) -> Result<ApiResponse, ApiError> {
        let mut headers = BTreeMap::from([("x-operation-id".to_string(), operation.to_string())]);
        if let Some(revision) = revision {
            headers.insert("if-match".into(), revision.into());
        }
        self.api
            .handle(ApiRequest {
                method: method.into(),
                path: path.into(),
                query: BTreeMap::new(),
                headers,
                body,
                principal: principal.clone(),
            })
            .await
    }

    async fn lifecycle_call(
        &self,
        principal: &Principal,
        method: &str,
        path: &str,
        operation: &str,
    ) -> Result<ApiResponse, ApiError> {
        self.send_with_operation(principal, method, path, json!(null), None, operation)
            .await
    }

    async fn provision(&self, board: &str) {
        let response = self
            .send(
                &service(true),
                "PUT",
                &format!("/{board}/api/config"),
                json!(null),
                None,
            )
            .await
            .unwrap();
        assert_eq!(response.status, 201);
    }

    async fn create_issue(&self, board: &str, body: Value) -> String {
        let response = self
            .send(
                &service(true),
                "POST",
                &format!("/{board}/api/issues"),
                body,
                None,
            )
            .await
            .unwrap();
        response.body["issue"]["id"].as_str().unwrap().to_string()
    }

    async fn populate(&self, board: &str) -> String {
        self.provision(board).await;
        let epic = self
            .create_issue(board, json!({"type":"epic","title":"Epic"}))
            .await;
        self.create_issue(board, json!({"type":"task","title":"Task","parent":epic}))
            .await;
        epic
    }

    async fn archive(&self, board: &str) -> ApiResponse {
        self.send(
            &service(true),
            "POST",
            &format!("/{board}/api/board/archive"),
            json!(null),
            None,
        )
        .await
        .unwrap()
    }

    async fn purge(&self, board: &str) -> Result<ApiResponse, ApiError> {
        self.send(
            &service(true),
            "DELETE",
            &format!("/{board}/api/board"),
            json!(null),
            None,
        )
        .await
    }

    async fn snapshot(&self, board: &str) -> Snapshot {
        let (tenant, project) = board.split_once('/').unwrap();
        let scope = Scope::new(tenant, project).unwrap();
        let mut canonical = Vec::new();
        let mut cursor: Option<String> = None;
        loop {
            let page = self
                .objects
                .list(&scope, "", cursor.as_deref(), 1000)
                .await
                .unwrap();
            canonical.extend(page.paths);
            cursor = page.next_cursor;
            if cursor.is_none() {
                break;
            }
        }
        let mut control = Vec::new();
        let mut cursor: Option<String> = None;
        loop {
            let page = self
                .objects
                .list_control(&scope, "", cursor.as_deref(), 1000)
                .await
                .unwrap();
            control.extend(page.paths);
            cursor = page.next_cursor;
            if cursor.is_none() {
                break;
            }
        }
        let catalog = self
            .catalog
            .query(&scope, &CatalogQuery::default(), None, 1000)
            .await
            .unwrap()
            .cards
            .into_iter()
            .map(|card| format!("{}@{}", card.path, card.revision))
            .collect();
        Snapshot {
            canonical,
            control,
            catalog,
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
struct Snapshot {
    canonical: Vec<String>,
    control: Vec<String>,
    catalog: Vec<String>,
}

fn service(provision: bool) -> Principal {
    Principal {
        actor: "arn:aws:sts::123456789012:assumed-role/control/session".into(),
        grants: vec![Grant {
            tenant: "acme".into(),
            project: ProjectGrant::AllInTenant,
        }],
        provision,
        delegate_actor: false,
    }
}

fn member() -> Principal {
    Principal {
        actor: "member-1".into(),
        grants: vec![Grant {
            tenant: "acme".into(),
            project: ProjectGrant::AllInTenant,
        }],
        provision: false,
        delegate_actor: false,
    }
}

fn other_service() -> Principal {
    let mut principal = service(true);
    principal.actor = "arn:aws:sts::123456789012:assumed-role/other/session".into();
    principal
}

fn error_of(result: Result<ApiResponse, ApiError>) -> (u16, &'static str, Value) {
    let error = result.err().expect("the request is rejected");
    (error.status, error.code, error.body())
}

#[tokio::test]
async fn archived_boards_are_hidden_from_members_and_read_only_for_provisioning_services() {
    let harness = Harness::new();
    let epic = harness.populate("acme/bot").await;
    let before = harness
        .send(&member(), "GET", "/acme/bot/api/issues", json!(null), None)
        .await
        .unwrap();
    assert_eq!(before.status, 200);
    let archived = harness.archive("acme/bot").await;
    assert_eq!(archived.status, 200);
    assert!(archived.body["archived_at"].is_string());
    assert!(archived.body["purge_after"].is_string());

    let missing = error_of(
        harness
            .send(
                &member(),
                "GET",
                "/acme/ghost/api/config",
                json!(null),
                None,
            )
            .await,
    );
    assert_eq!((missing.0, missing.1), (404, "not_found"));
    let board_routes = [
        ("GET", "/acme/bot/api/config".to_string()),
        ("GET", "/acme/bot/api/issues".to_string()),
        ("GET", format!("/acme/bot/api/issues/{epic}")),
        ("GET", format!("/acme/bot/api/issues/{epic}/events")),
        ("POST", "/acme/bot/api/issues".to_string()),
        ("PATCH", format!("/acme/bot/api/issues/{epic}")),
        ("DELETE", format!("/acme/bot/api/issues/{epic}")),
        ("POST", format!("/acme/bot/api/issues/{epic}/comments")),
        ("PUT", "/acme/bot/api/config".to_string()),
    ];
    for principal in [member(), service(false)] {
        for (method, path) in &board_routes {
            let hidden = error_of(
                harness
                    .send(
                        &principal,
                        method,
                        path,
                        json!({"title":"x","text":"x"}),
                        Some("\"r\""),
                    )
                    .await,
            );
            assert_eq!((hidden.0, hidden.1), (404, "not_found"), "{method} {path}");
            assert_eq!(hidden.2, missing.2);
        }
    }

    for path in [
        "/acme/bot/api/config".to_string(),
        "/acme/bot/api/issues".to_string(),
        format!("/acme/bot/api/issues/{epic}"),
        format!("/acme/bot/api/issues/{epic}/events"),
    ] {
        let read = harness
            .send(&service(true), "GET", &path, json!(null), None)
            .await
            .unwrap();
        assert_eq!(read.status, 200, "{path}");
    }
    for (method, path) in &board_routes[4..] {
        let rejected = error_of(
            harness
                .send(
                    &service(true),
                    method,
                    path,
                    json!({"title":"x","type":"task","text":"x"}),
                    Some("\"r\""),
                )
                .await,
        );
        assert_eq!(
            (rejected.0, rejected.1),
            (409, "board_archived"),
            "{method} {path}"
        );
    }

    let mut listing = BTreeMap::new();
    listing.insert("projects".to_string(), "bot".to_string());
    let list_request = |principal: Principal| ApiRequest {
        method: "GET".into(),
        path: "/acme/api/issues".into(),
        query: listing.clone(),
        headers: BTreeMap::new(),
        body: json!(null),
        principal,
    };
    let hidden = harness
        .api
        .handle(list_request(member()))
        .await
        .err()
        .unwrap();
    assert_eq!((hidden.status, hidden.code), (404, "not_found"));
    assert_eq!(
        harness
            .api
            .handle(list_request(service(true)))
            .await
            .unwrap()
            .status,
        200
    );
}

#[tokio::test]
async fn restoring_returns_the_board_to_normal_and_removes_it_from_the_index() {
    let harness = Harness::new();
    harness.populate("acme/bot").await;
    harness.archive("acme/bot").await;
    let restored = harness
        .send(
            &service(true),
            "POST",
            "/acme/bot/api/board/restore",
            json!(null),
            None,
        )
        .await
        .unwrap();
    assert_eq!(
        (restored.status, restored.body),
        (200, json!({"restored":true}))
    );
    let listed = harness
        .send(&member(), "GET", "/acme/bot/api/issues", json!(null), None)
        .await
        .unwrap();
    assert_eq!(listed.body["issues"].as_array().unwrap().len(), 2);
    let created = harness
        .send(
            &member(),
            "POST",
            "/acme/bot/api/issues",
            json!({"type":"task","title":"After"}),
            None,
        )
        .await
        .unwrap();
    assert_eq!(created.status, 201);
    harness.advance_days(365);
    let report = harness
        .api
        .sweep_expired_archives(harness.now())
        .await
        .unwrap();
    assert_eq!(report, kanbus_api::SweepReport::default());
    assert_eq!(
        harness
            .send(&member(), "GET", "/acme/bot/api/config", json!(null), None)
            .await
            .unwrap()
            .status,
        200
    );
}

#[tokio::test]
async fn purge_and_restore_require_an_archived_board_and_remove_nothing() {
    let harness = Harness::new();
    harness.populate("acme/bot").await;
    let before = harness.snapshot("acme/bot").await;
    let purge = error_of(harness.purge("acme/bot").await);
    assert_eq!((purge.0, purge.1), (409, "board_not_archived"));
    let restore = error_of(
        harness
            .send(
                &service(true),
                "POST",
                "/acme/bot/api/board/restore",
                json!(null),
                None,
            )
            .await,
    );
    assert_eq!((restore.0, restore.1), (409, "board_not_archived"));
    assert_eq!(harness.snapshot("acme/bot").await, before);
}

#[tokio::test]
async fn archiving_requires_an_existing_board_and_rejects_a_second_archive() {
    let harness = Harness::new();
    let ghost = error_of(
        harness
            .send(
                &service(true),
                "POST",
                "/acme/ghost/api/board/archive",
                json!(null),
                None,
            )
            .await,
    );
    assert_eq!((ghost.0, ghost.1), (404, "not_found"));
    harness.populate("acme/bot").await;
    harness.archive("acme/bot").await;
    let again = error_of(
        harness
            .send(
                &service(true),
                "POST",
                "/acme/bot/api/board/archive",
                json!(null),
                None,
            )
            .await,
    );
    assert_eq!((again.0, again.1), (409, "board_archived"));
}

#[tokio::test]
async fn purge_removes_the_archived_board_and_never_touches_other_boards() {
    let harness = Harness::new();
    harness.populate("acme/doomed").await;
    harness.populate("acme/neighbor").await;
    harness.populate("acme/doomed-twin").await;
    let mut foreign = service(true);
    foreign.grants.push(Grant {
        tenant: "globex".into(),
        project: ProjectGrant::AllInTenant,
    });
    let foreign_board = harness
        .send(
            &foreign,
            "PUT",
            "/globex/neighbor/api/config",
            json!(null),
            None,
        )
        .await
        .unwrap();
    assert_eq!(foreign_board.status, 201);
    let doomed_before = harness.snapshot("acme/doomed").await;
    assert!(doomed_before.canonical.len() >= 5 && !doomed_before.catalog.is_empty());
    assert!(doomed_before
        .control
        .iter()
        .any(|path| path.starts_with("relations/")));
    let others_before = (
        harness.snapshot("acme/neighbor").await,
        harness.snapshot("acme/doomed-twin").await,
        harness.snapshot("globex/neighbor").await,
    );

    harness.archive("acme/doomed").await;
    let purged = harness.purge("acme/doomed").await.unwrap();
    assert_eq!((purged.status, purged.body), (200, json!({"purged":true})));

    let after = harness.snapshot("acme/doomed").await;
    assert!(after.canonical.is_empty(), "{:?}", after.canonical);
    assert!(after.catalog.is_empty());
    assert!(
        after.control.iter().all(|path| path.starts_with("purge/")),
        "{:?}",
        after.control
    );
    assert_eq!(
        others_before,
        (
            harness.snapshot("acme/neighbor").await,
            harness.snapshot("acme/doomed-twin").await,
            harness.snapshot("globex/neighbor").await,
        )
    );
    for principal in [service(true), member()] {
        for path in ["/acme/doomed/api/config", "/acme/doomed/api/issues"] {
            let gone = error_of(
                harness
                    .send(&principal, "GET", path, json!(null), None)
                    .await,
            );
            assert_eq!((gone.0, gone.1), (404, "not_found"), "{path}");
        }
    }
    let neighbor = harness
        .send(
            &member(),
            "GET",
            "/acme/neighbor/api/issues",
            json!(null),
            None,
        )
        .await
        .unwrap();
    assert_eq!(neighbor.body["issues"].as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn a_purged_board_can_be_provisioned_again_from_scratch() {
    let harness = Harness::new();
    harness.populate("acme/bot").await;
    harness.archive("acme/bot").await;
    harness.purge("acme/bot").await.unwrap();
    harness.provision("acme/bot").await;
    let listed = harness
        .send(&member(), "GET", "/acme/bot/api/issues", json!(null), None)
        .await
        .unwrap();
    assert!(listed.body["issues"].as_array().unwrap().is_empty());
    let created = harness
        .send(
            &member(),
            "POST",
            "/acme/bot/api/issues",
            json!({"type":"task","title":"Fresh"}),
            None,
        )
        .await
        .unwrap();
    assert_eq!(created.status, 201);
}

#[tokio::test]
async fn an_interrupted_purge_resumes_with_the_same_operation_id() {
    let harness = Harness::new();
    harness.populate("acme/doomed").await;
    harness.populate("acme/neighbor").await;
    let neighbor_before = harness.snapshot("acme/neighbor").await;
    harness.archive("acme/doomed").await;
    let operation = uuid::Uuid::new_v4().to_string();

    harness.objects.permit_deletes_then_fail(2);
    let interrupted = error_of(
        harness
            .lifecycle_call(
                &service(true),
                "DELETE",
                "/acme/doomed/api/board",
                &operation,
            )
            .await,
    );
    assert_eq!(interrupted.0, 503);
    let partial = harness.snapshot("acme/doomed").await;
    assert!(!partial.canonical.is_empty() || !partial.control.is_empty());

    harness.objects.stop_failing();
    let other_operation = error_of(
        harness
            .lifecycle_call(
                &service(true),
                "DELETE",
                "/acme/doomed/api/board",
                &uuid::Uuid::new_v4().to_string(),
            )
            .await,
    );
    assert_eq!(
        (other_operation.0, other_operation.1),
        (409, "purge_in_progress")
    );
    let restore = error_of(
        harness
            .send(
                &service(true),
                "POST",
                "/acme/doomed/api/board/restore",
                json!(null),
                None,
            )
            .await,
    );
    assert_eq!((restore.0, restore.1), (409, "purge_in_progress"));

    let resumed = harness
        .lifecycle_call(
            &service(true),
            "DELETE",
            "/acme/doomed/api/board",
            &operation,
        )
        .await
        .unwrap();
    assert_eq!(resumed.body, json!({"purged":true}));
    let after = harness.snapshot("acme/doomed").await;
    assert!(after.canonical.is_empty() && after.catalog.is_empty());
    assert!(after.control.iter().all(|path| path.starts_with("purge/")));
    assert_eq!(harness.snapshot("acme/neighbor").await, neighbor_before);
}

#[tokio::test]
async fn lifecycle_operations_replay_and_reject_changed_requests() {
    let harness = Harness::new();
    harness.populate("acme/bot").await;
    let archive_operation = uuid::Uuid::new_v4().to_string();
    let first = harness
        .lifecycle_call(
            &service(true),
            "POST",
            "/acme/bot/api/board/archive",
            &archive_operation,
        )
        .await
        .unwrap();
    harness.advance_days(3);
    let replay = harness
        .lifecycle_call(
            &service(true),
            "POST",
            "/acme/bot/api/board/archive",
            &archive_operation,
        )
        .await
        .unwrap();
    assert_eq!(replay.body, first.body);
    let conflict = error_of(
        harness
            .lifecycle_call(
                &other_service(),
                "POST",
                "/acme/bot/api/board/archive",
                &archive_operation,
            )
            .await,
    );
    assert_eq!((conflict.0, conflict.1), (409, "operation_conflict"));

    let restore_operation = uuid::Uuid::new_v4().to_string();
    assert_eq!(
        harness
            .lifecycle_call(
                &service(true),
                "POST",
                "/acme/bot/api/board/restore",
                &restore_operation
            )
            .await
            .unwrap()
            .body,
        json!({"restored":true})
    );
    assert_eq!(
        harness
            .lifecycle_call(
                &service(true),
                "POST",
                "/acme/bot/api/board/restore",
                &restore_operation
            )
            .await
            .unwrap()
            .body,
        json!({"restored":true})
    );
    assert_eq!(
        error_of(
            harness
                .lifecycle_call(
                    &other_service(),
                    "POST",
                    "/acme/bot/api/board/restore",
                    &restore_operation
                )
                .await
        )
        .1,
        "operation_conflict"
    );
    assert_eq!(
        harness
            .send(&member(), "GET", "/acme/bot/api/config", json!(null), None)
            .await
            .unwrap()
            .status,
        200
    );

    harness.archive("acme/bot").await;
    let purge_operation = uuid::Uuid::new_v4().to_string();
    assert_eq!(
        harness
            .lifecycle_call(
                &service(true),
                "DELETE",
                "/acme/bot/api/board",
                &purge_operation
            )
            .await
            .unwrap()
            .body,
        json!({"purged":true})
    );
    assert_eq!(
        harness
            .lifecycle_call(
                &service(true),
                "DELETE",
                "/acme/bot/api/board",
                &purge_operation
            )
            .await
            .unwrap()
            .body,
        json!({"purged":true})
    );
    assert_eq!(
        error_of(
            harness
                .lifecycle_call(
                    &other_service(),
                    "DELETE",
                    "/acme/bot/api/board",
                    &purge_operation
                )
                .await
        )
        .1,
        "operation_conflict"
    );
    harness.provision("acme/bot").await;
    assert_eq!(
        harness
            .lifecycle_call(
                &service(true),
                "DELETE",
                "/acme/bot/api/board",
                &purge_operation
            )
            .await
            .unwrap()
            .body,
        json!({"purged":true})
    );
    assert_eq!(
        harness
            .send(&member(), "GET", "/acme/bot/api/config", json!(null), None)
            .await
            .unwrap()
            .status,
        200
    );
}

#[tokio::test]
async fn only_provisioning_services_change_a_board_lifecycle() {
    let harness = Harness::new();
    harness.populate("acme/bot").await;
    harness.archive("acme/bot").await;
    let ungranted = error_of(
        harness
            .send(
                &service(true),
                "POST",
                "/other/bot/api/board/archive",
                json!(null),
                None,
            )
            .await,
    );
    assert_eq!(ungranted.0, 403);
    for principal in [member(), service(false)] {
        for (method, path) in [
            ("POST", "/acme/bot/api/board/archive"),
            ("POST", "/acme/bot/api/board/restore"),
            ("DELETE", "/acme/bot/api/board"),
        ] {
            let refused = error_of(
                harness
                    .send(&principal, method, path, json!(null), None)
                    .await,
            );
            assert_eq!(refused.0, 403, "{method} {path}");
            assert_eq!(refused.2, ungranted.2);
        }
    }
    assert_eq!(
        harness
            .send(
                &service(true),
                "GET",
                "/acme/bot/api/config",
                json!(null),
                None
            )
            .await
            .unwrap()
            .status,
        200
    );
}

#[tokio::test]
async fn tenant_names_beginning_with_an_underscore_are_reserved() {
    let harness = Harness::new();
    let mut everything = service(true);
    everything.grants = vec![
        Grant {
            tenant: "_kanbus".into(),
            project: ProjectGrant::AllInTenant,
        },
        Grant {
            tenant: "_other".into(),
            project: ProjectGrant::AllInTenant,
        },
    ];
    for (method, path) in [
        ("GET", "/_kanbus/archives/api/config"),
        ("PUT", "/_other/bot/api/config"),
        ("POST", "/_kanbus/archives/api/board/archive"),
        ("GET", "/_other/api/issues"),
    ] {
        let mut request = ApiRequest {
            method: method.into(),
            path: path.into(),
            query: BTreeMap::from([("projects".to_string(), "bot".to_string())]),
            headers: BTreeMap::from([(
                "x-operation-id".to_string(),
                uuid::Uuid::new_v4().to_string(),
            )]),
            body: json!(null),
            principal: everything.clone(),
        };
        request.principal.provision = true;
        let rejected = harness.api.handle(request).await.err().unwrap();
        assert_eq!(
            (rejected.status, rejected.code),
            (400, "invalid_request"),
            "{path}"
        );
    }
}

#[tokio::test]
async fn the_sweeper_purges_only_expired_archives_and_is_idempotent() {
    let harness = Harness::new();
    for board in ["acme/old", "acme/recent", "acme/never"] {
        harness.populate(board).await;
    }
    harness.archive("acme/old").await;
    harness.advance_days(26);
    harness.archive("acme/recent").await;
    harness.advance_days(5);
    let now = harness.now();
    let recent_before = harness.snapshot("acme/recent").await;
    let never_before = harness.snapshot("acme/never").await;

    let report = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(
        report,
        kanbus_api::SweepReport {
            purged: 1,
            stale_removed: 0,
            failed: 0
        }
    );
    let old = harness.snapshot("acme/old").await;
    assert!(old.canonical.is_empty() && old.catalog.is_empty());
    assert_eq!(harness.snapshot("acme/recent").await, recent_before);
    assert_eq!(harness.snapshot("acme/never").await, never_before);
    assert_eq!(
        harness
            .send(
                &service(true),
                "GET",
                "/acme/recent/api/config",
                json!(null),
                None
            )
            .await
            .unwrap()
            .status,
        200
    );
    assert_eq!(
        error_of(
            harness
                .send(
                    &service(true),
                    "GET",
                    "/acme/old/api/config",
                    json!(null),
                    None
                )
                .await
        )
        .1,
        "not_found"
    );

    let again = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(again, kanbus_api::SweepReport::default());

    harness.advance_days(30);
    let later = harness
        .api
        .sweep_expired_archives(harness.now())
        .await
        .unwrap();
    assert_eq!(later.purged, 1);
    assert!(harness.snapshot("acme/recent").await.canonical.is_empty());
    assert_eq!(harness.snapshot("acme/never").await, never_before);
}

#[tokio::test]
async fn the_sweeper_resumes_an_interrupted_api_purge_and_survives_a_failing_board() {
    let harness = Harness::new();
    harness.populate("acme/bot").await;
    harness.archive("acme/bot").await;
    harness.objects.permit_deletes_then_fail(1);
    assert_eq!(error_of(harness.purge("acme/bot").await).0, 503);
    harness.advance_days(31);
    let now = harness.now();

    let failed = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(
        failed,
        kanbus_api::SweepReport {
            purged: 0,
            stale_removed: 0,
            failed: 1
        }
    );

    harness.objects.stop_failing();
    let resumed = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(
        resumed,
        kanbus_api::SweepReport {
            purged: 1,
            stale_removed: 0,
            failed: 0
        }
    );
    let after = harness.snapshot("acme/bot").await;
    assert!(after.canonical.is_empty() && after.catalog.is_empty());
}

#[tokio::test]
async fn the_sweeper_is_bounded_per_run_and_removes_stale_entries_without_purging() {
    let harness = Harness::new();
    let boards = SWEEP_BATCH_LIMIT + 2;
    for index in 0..boards {
        let board = format!("acme/b{index:03}");
        harness.provision(&board).await;
        harness.archive(&board).await;
    }
    harness.advance_days(31);
    let now = harness.now();

    let restored_board = "acme/b000";
    harness
        .send(
            &service(true),
            "POST",
            &format!("/{restored_board}/api/board/restore"),
            json!(null),
            None,
        )
        .await
        .unwrap();
    let archive_scope = Scope::new("_kanbus", "archives").unwrap();
    let stale_path = format!(
        "index/{}/acme/a-ghost.json",
        (now - chrono::Duration::days(1)).format("%Y%m%dT%H%M%SZ")
    );
    harness
        .objects
        .put(
            &archive_scope,
            &stale_path,
            json!({"tenant":"acme","project":"a-ghost"})
                .to_string()
                .as_bytes(),
            "application/json",
            WriteCondition::Absent,
            None,
        )
        .await
        .unwrap();

    let first = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(first.stale_removed, 1);
    assert_eq!(
        first.purged + first.stale_removed + first.failed,
        SWEEP_BATCH_LIMIT
    );
    let second = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(first.purged + second.purged, boards - 1);
    assert_eq!(second.stale_removed, 0);
    let third = harness.api.sweep_expired_archives(now).await.unwrap();
    assert_eq!(third, kanbus_api::SweepReport::default());
    assert_eq!(
        harness
            .send(
                &service(true),
                "GET",
                &format!("/{restored_board}/api/config"),
                json!(null),
                None
            )
            .await
            .unwrap()
            .status,
        200
    );
}

#[test]
fn the_retention_setting_is_required_and_must_be_a_positive_integer() {
    for value in [
        None,
        Some(""),
        Some("0"),
        Some("-3"),
        Some("soon"),
        Some("1.5"),
    ] {
        let message = BoardLifecycle::parse_retention_days(value).unwrap_err();
        assert!(
            message.contains("KANBUS_ARCHIVE_RETENTION_DAYS"),
            "{value:?}"
        );
    }
    assert_eq!(
        BoardLifecycle::parse_retention_days(Some("30")).unwrap(),
        30
    );
    let objects = Arc::new(FileStore::new(tempfile::tempdir().unwrap().path()).unwrap());
    assert!(BoardLifecycle::new(0, objects).is_err());
}
