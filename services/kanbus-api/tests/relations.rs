//! Executable examples for the relation scenarios of features/writable_api.feature.

use kanbus_api::{Api, ApiRequest, Grant, Principal, ProjectGrant, RELATION_LEASE};
use serde_json::{json, Value};
use std::{collections::BTreeMap, sync::Arc};
use tempfile::TempDir;
use virtuus_store::{FileStore, JournaledStore, MemoryCatalog, Scope};

mod support;
use support::{PausePoint, PauseStore};

type TestClock = Arc<std::sync::Mutex<chrono::DateTime<chrono::Utc>>>;

struct Board {
    directory: TempDir,
    api: Api,
    objects: Arc<PauseStore>,
    clock: TestClock,
}

impl Board {
    fn advance(&self, by: std::time::Duration) {
        let mut now = self.clock.lock().unwrap();
        *now += chrono::Duration::from_std(by).unwrap();
    }

    fn past_lease(&self) {
        self.advance(RELATION_LEASE + std::time::Duration::from_secs(1));
    }
}

fn board() -> Board {
    let directory = tempfile::tempdir().unwrap();
    let mut configuration = kanbus::config::default_project_configuration();
    configuration.project_key = "crm".into();
    std::fs::write(
        directory.path().join(".kanbus.yml"),
        serde_yaml::to_string(&configuration).unwrap(),
    )
    .unwrap();
    let scope = Scope::new("tenant", "project").unwrap();
    let objects = PauseStore::new(FileStore::for_project(directory.path(), scope).unwrap());
    let store = JournaledStore::new(objects.clone(), Arc::new(MemoryCatalog::default()));
    let clock: TestClock = Arc::new(std::sync::Mutex::new(chrono::Utc::now()));
    let reader = clock.clone();
    let api = Api::with_clock(
        store,
        objects.clone(),
        support::lifecycle_beside(directory.path()),
        Arc::new(move || *reader.lock().unwrap()),
    )
    .unwrap();
    Board {
        directory,
        api,
        objects,
        clock,
    }
}

fn call(method: &str, path: &str, body: Value, revision: Option<&str>) -> ApiRequest {
    let mut headers = BTreeMap::from([("x-operation-id".into(), uuid::Uuid::new_v4().to_string())]);
    if let Some(revision) = revision {
        headers.insert("if-match".into(), revision.into());
    }
    ApiRequest {
        method: method.into(),
        path: format!("/tenant/project{path}"),
        query: BTreeMap::new(),
        headers,
        body,
        principal: Principal {
            actor: "member-1".into(),
            grants: vec![Grant {
                tenant: "tenant".into(),
                project: ProjectGrant::One("project".into()),
            }],
            provision: false,
            delegate_actor: false,
        },
    }
}

async fn create(api: &Api, body: Value) -> Value {
    api.handle(call("POST", "/api/issues", body, None))
        .await
        .unwrap()
        .body
}

async fn create_error(api: &Api, body: Value) -> (u16, &'static str) {
    let error = api
        .handle(call("POST", "/api/issues", body, None))
        .await
        .err()
        .unwrap();
    (error.status, error.code)
}

fn id_of(issue: &Value) -> String {
    issue["issue"]["id"].as_str().unwrap().to_string()
}

async fn fetch(api: &Api, identifier: &str) -> Value {
    api.handle(call(
        "GET",
        &format!("/api/issues/{identifier}"),
        json!(null),
        None,
    ))
    .await
    .unwrap()
    .body
}

async fn patch(api: &Api, identifier: &str, body: Value) -> Result<Value, (u16, &'static str)> {
    let current = fetch(api, identifier).await;
    patch_at(api, identifier, body, current["revision"].as_str().unwrap()).await
}

async fn patch_at(
    api: &Api,
    identifier: &str,
    body: Value,
    revision: &str,
) -> Result<Value, (u16, &'static str)> {
    api.handle(call(
        "PATCH",
        &format!("/api/issues/{identifier}"),
        body,
        Some(revision),
    ))
    .await
    .map(|response| response.body)
    .map_err(|error| (error.status, error.code))
}

async fn delete(api: &Api, identifier: &str) -> Result<Value, (u16, &'static str)> {
    let current = fetch(api, identifier).await;
    api.handle(call(
        "DELETE",
        &format!("/api/issues/{identifier}"),
        json!(null),
        current["revision"].as_str(),
    ))
    .await
    .map(|response| response.body)
    .map_err(|error| (error.status, error.code))
}

fn read_issues(directory: &TempDir) -> BTreeMap<String, Value> {
    let mut issues = BTreeMap::new();
    let Ok(entries) = std::fs::read_dir(directory.path().join("project/issues")) else {
        return issues;
    };
    for entry in entries {
        let raw: Value =
            serde_json::from_slice(&std::fs::read(entry.unwrap().path()).unwrap()).unwrap();
        issues.insert(raw["id"].as_str().unwrap().to_string(), raw);
    }
    issues
}

async fn assert_global_invariants(board: &Board) {
    let issues = read_issues(&board.directory);
    let mut parents_with_live_children = std::collections::BTreeSet::new();
    for (identifier, issue) in &issues {
        if let Some(parent) = issue["parent"].as_str() {
            assert!(
                issues.contains_key(parent),
                "{identifier} has missing parent {parent}"
            );
            parents_with_live_children.insert(parent.to_string());
        }
        for link in issue["dependencies"].as_array().unwrap() {
            let target = link["target"].as_str().unwrap();
            assert!(
                issues.contains_key(target),
                "{identifier} has missing dependency target {target}"
            );
        }
    }
    for parent in parents_with_live_children {
        let error = delete(&board.api, &parent).await.err().unwrap();
        assert_eq!(
            error,
            (409, "issue_has_children"),
            "parent {parent} with live children must not be deletable"
        );
    }
}

fn spawn_create(
    api: &Api,
    body: Value,
) -> tokio::task::JoinHandle<Result<Value, (u16, &'static str)>> {
    let api = api.clone();
    tokio::spawn(async move {
        api.handle(call("POST", "/api/issues", body, None))
            .await
            .map(|response| response.body)
            .map_err(|error| (error.status, error.code))
    })
}

fn spawn_patch(
    api: &Api,
    identifier: &str,
    body: Value,
    revision: &str,
) -> tokio::task::JoinHandle<Result<Value, (u16, &'static str)>> {
    let api = api.clone();
    let identifier = identifier.to_string();
    let revision = revision.to_string();
    tokio::spawn(async move { patch_at(&api, &identifier, body, &revision).await })
}

fn spawn_delete(
    api: &Api,
    identifier: &str,
    revision: &str,
) -> tokio::task::JoinHandle<Result<Value, (u16, &'static str)>> {
    let api = api.clone();
    let identifier = identifier.to_string();
    let revision = revision.to_string();
    tokio::spawn(async move {
        api.handle(call(
            "DELETE",
            &format!("/api/issues/{identifier}"),
            json!(null),
            Some(&revision),
        ))
        .await
        .map(|response| response.body)
        .map_err(|error| (error.status, error.code))
    })
}

#[tokio::test]
async fn a_task_is_created_under_an_epic_and_blocks_deleting_it() {
    let board = board();
    let epic = create(&board.api, json!({"title":"Epic","type":"epic"})).await;
    let epic_id = id_of(&epic);
    let task = create(
        &board.api,
        json!({"title":"Task","type":"task","parent":epic_id}),
    )
    .await;
    assert_eq!(task["issue"]["parent"], json!(epic_id));
    assert_eq!(
        delete(&board.api, &epic_id).await.err().unwrap(),
        (409, "issue_has_children")
    );
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn creating_under_a_missing_parent_is_rejected() {
    let board = board();
    let missing = create_error(
        &board.api,
        json!({"title":"Task","type":"task","parent":"crm-missing"}),
    )
    .await;
    assert_eq!(missing, (409, "relation_target_missing"));
    assert!(read_issues(&board.directory).is_empty());
}

#[tokio::test]
async fn creating_a_type_the_hierarchy_forbids_is_rejected() {
    let board = board();
    let task = create(&board.api, json!({"title":"Task","type":"task"})).await;
    let forbidden = create_error(
        &board.api,
        json!({"title":"Epic","type":"epic","parent":id_of(&task)}),
    )
    .await;
    assert_eq!(forbidden, (409, "hierarchy_violation"));
    assert_eq!(read_issues(&board.directory).len(), 1);
}

#[tokio::test]
async fn reparenting_moves_the_reference_between_both_parents() {
    let board = board();
    let first = id_of(&create(&board.api, json!({"title":"A","type":"epic"})).await);
    let second = id_of(&create(&board.api, json!({"title":"B","type":"epic"})).await);
    let task = id_of(
        &create(
            &board.api,
            json!({"title":"Task","type":"task","parent":first}),
        )
        .await,
    );
    patch(&board.api, &task, json!({"parent":second}))
        .await
        .unwrap();
    assert_eq!(
        delete(&board.api, &second).await.err().unwrap(),
        (409, "issue_has_children")
    );
    delete(&board.api, &first).await.unwrap();
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn dependencies_can_be_added_and_removed() {
    let board = board();
    let target = id_of(&create(&board.api, json!({"title":"Target","type":"bug"})).await);
    let source = id_of(&create(&board.api, json!({"title":"Source","type":"bug"})).await);
    patch(
        &board.api,
        &source,
        json!({"dependencies":[{"target":target,"type":"blocked-by"}]}),
    )
    .await
    .unwrap();
    assert_eq!(
        delete(&board.api, &target).await.err().unwrap(),
        (409, "issue_has_dependents")
    );
    assert_global_invariants(&board).await;
    patch(&board.api, &source, json!({"dependencies":[]}))
        .await
        .unwrap();
    delete(&board.api, &target).await.unwrap();
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn invalid_dependencies_are_rejected() {
    let board = board();
    let source = id_of(&create(&board.api, json!({"title":"Source","type":"bug"})).await);
    assert_eq!(
        patch(
            &board.api,
            &source,
            json!({"dependencies":[{"target":"crm-missing","type":"blocked-by"}]})
        )
        .await
        .err()
        .unwrap(),
        (409, "relation_target_missing")
    );
    assert_eq!(
        patch(
            &board.api,
            &source,
            json!({"dependencies":[{"target":source,"type":"blocked-by"}]})
        )
        .await
        .err()
        .unwrap(),
        (400, "invalid_request")
    );
    assert_eq!(
        patch(
            &board.api,
            &source,
            json!({"dependencies":[{"target":source,"type":"mystery"}]})
        )
        .await
        .err()
        .unwrap(),
        (400, "invalid_request")
    );
}

#[tokio::test]
async fn deleting_a_hierarchical_issue_without_children_succeeds() {
    let board = board();
    let task = id_of(&create(&board.api, json!({"title":"Task","type":"task"})).await);
    delete(&board.api, &task).await.unwrap();
    assert!(read_issues(&board.directory).is_empty());
}

#[tokio::test]
async fn a_stale_entry_blocks_deletion_inside_the_lease_and_is_pruned_after_it() {
    let board = board();
    let epic = id_of(&create(&board.api, json!({"title":"Epic","type":"epic"})).await);
    let task = id_of(
        &create(
            &board.api,
            json!({"title":"Task","type":"task","parent":epic}),
        )
        .await,
    );
    let file = board
        .directory
        .path()
        .join(format!("project/issues/{task}.json"));
    let mut raw: Value = serde_json::from_slice(&std::fs::read(&file).unwrap()).unwrap();
    raw["parent"] = Value::Null;
    std::fs::write(&file, serde_json::to_vec(&raw).unwrap()).unwrap();
    assert_eq!(
        delete(&board.api, &epic).await.err().unwrap(),
        (409, "issue_has_children")
    );
    board.past_lease();
    delete(&board.api, &epic).await.unwrap();
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn replayed_writes_are_idempotent() {
    let board = board();
    let epic = id_of(&create(&board.api, json!({"title":"Epic","type":"epic"})).await);
    let operation = uuid::Uuid::new_v4().to_string();
    let mut first = call(
        "POST",
        "/api/issues",
        json!({"title":"Task","type":"task","parent":epic}),
        None,
    );
    first
        .headers
        .insert("x-operation-id".into(), operation.clone());
    let original = board.api.handle(first).await.unwrap().body;
    let mut replay = call(
        "POST",
        "/api/issues",
        json!({"title":"Task","type":"task","parent":epic}),
        None,
    );
    replay.headers.insert("x-operation-id".into(), operation);
    assert_eq!(
        board.api.handle(replay).await.unwrap().body["issue"],
        original["issue"]
    );
    assert_eq!(read_issues(&board.directory).len(), 2);

    let task = id_of(&original);
    let other = id_of(&create(&board.api, json!({"title":"Other","type":"epic"})).await);
    let current = fetch(&board.api, &task).await;
    let operation = uuid::Uuid::new_v4().to_string();
    let reparent = |operation: &str| {
        let mut request = call(
            "PATCH",
            &format!("/api/issues/{task}"),
            json!({"parent":other}),
            current["revision"].as_str(),
        );
        request
            .headers
            .insert("x-operation-id".into(), operation.into());
        request
    };
    let applied = board.api.handle(reparent(&operation)).await.unwrap().body;
    let replayed = board.api.handle(reparent(&operation)).await.unwrap().body;
    assert_eq!(applied["issue"], replayed["issue"]);
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn type_changes_to_or_from_hierarchy_types_are_unsupported() {
    let board = board();
    let task = id_of(&create(&board.api, json!({"title":"Task","type":"task"})).await);
    assert_eq!(
        patch(&board.api, &task, json!({"type":"bug"}))
            .await
            .err()
            .unwrap(),
        (409, "type_change_unsupported")
    );
}

#[tokio::test]
async fn attach_in_flight_while_parent_is_deleted_never_leaves_an_orphan() {
    let board = board();
    let epic = create(&board.api, json!({"title":"Epic","type":"epic"})).await;
    let epic_id = id_of(&epic);
    let mut held = board.objects.arm(PausePoint::BeforePut, "project/issues/");
    let attaching = spawn_create(
        &board.api,
        json!({"title":"Task","type":"task","parent":epic_id}),
    );
    held.held().await;
    let deletion = delete(&board.api, &epic_id).await;
    held.release();
    let attached = attaching.await.unwrap();
    assert_eq!(deletion.err().unwrap(), (409, "issue_has_children"));
    attached.unwrap();
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn delete_in_flight_while_a_child_attaches_leaves_no_orphan() {
    let board = board();
    let epic = create(&board.api, json!({"title":"Epic","type":"epic"})).await;
    let epic_id = id_of(&epic);
    let mut held = board.objects.arm(PausePoint::AfterPut, "relations/");
    let deleting = spawn_delete(&board.api, &epic_id, epic["revision"].as_str().unwrap());
    held.held().await;
    let attach = create_error(
        &board.api,
        json!({"title":"Task","type":"task","parent":epic_id}),
    )
    .await;
    held.release();
    deleting.await.unwrap().unwrap();
    assert_eq!(attach, (409, "relation_target_missing"));
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn two_reparents_of_one_child_leave_exactly_one_parent() {
    let board = board();
    let first = id_of(&create(&board.api, json!({"title":"A","type":"epic"})).await);
    let second = id_of(&create(&board.api, json!({"title":"B","type":"epic"})).await);
    let third = id_of(&create(&board.api, json!({"title":"C","type":"epic"})).await);
    let task = id_of(
        &create(
            &board.api,
            json!({"title":"Task","type":"task","parent":first}),
        )
        .await,
    );
    let revision = fetch(&board.api, &task).await["revision"]
        .as_str()
        .unwrap()
        .to_string();
    let mut held = board
        .objects
        .arm(PausePoint::AfterPut, &format!("relations/{second}.json"));
    let slower = spawn_patch(&board.api, &task, json!({"parent":second}), &revision);
    held.held().await;
    patch_at(&board.api, &task, json!({"parent":third}), &revision)
        .await
        .unwrap();
    held.release();
    assert_eq!(
        slower.await.unwrap().err().unwrap(),
        (409, "revision_conflict")
    );
    assert_eq!(read_issues(&board.directory)[&task]["parent"], json!(third));
    assert_global_invariants(&board).await;
    delete(&board.api, &first).await.unwrap();
    assert_eq!(
        delete(&board.api, &second).await.err().unwrap(),
        (409, "issue_has_children")
    );
    board.past_lease();
    delete(&board.api, &second).await.unwrap();
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn a_crashed_attach_blocks_deletion_until_the_lease_expires() {
    let board = board();
    let epic = id_of(&create(&board.api, json!({"title":"Epic","type":"epic"})).await);
    let mut held = board.objects.arm(PausePoint::BeforePut, "project/issues/");
    let crashing = spawn_create(
        &board.api,
        json!({"title":"Task","type":"task","parent":epic}),
    );
    held.held().await;
    crashing.abort();
    assert!(crashing.await.unwrap_err().is_cancelled());
    assert_eq!(
        delete(&board.api, &epic).await.err().unwrap(),
        (409, "issue_has_children")
    );
    board.past_lease();
    delete(&board.api, &epic).await.unwrap();
    assert_global_invariants(&board).await;
}

#[tokio::test]
async fn a_crashed_delete_flag_is_cleared_by_an_attach_after_the_lease() {
    let board = board();
    let epic = create(&board.api, json!({"title":"Epic","type":"epic"})).await;
    let epic_id = id_of(&epic);
    let mut held = board.objects.arm(PausePoint::AfterPut, "relations/");
    let crashing = spawn_delete(&board.api, &epic_id, epic["revision"].as_str().unwrap());
    held.held().await;
    crashing.abort();
    assert!(crashing.await.unwrap_err().is_cancelled());
    assert_eq!(
        create_error(
            &board.api,
            json!({"title":"Task","type":"task","parent":epic_id})
        )
        .await,
        (409, "relation_target_missing")
    );
    board.past_lease();
    let task = create(
        &board.api,
        json!({"title":"Task","type":"task","parent":epic_id}),
    )
    .await;
    assert_eq!(task["issue"]["parent"], json!(epic_id));
    assert_global_invariants(&board).await;
}
