//! Executable examples for the relation scenarios of features/writable_api.feature.

use kanbus_api::{Api, ApiRequest, Grant, Principal, ProjectGrant};
use serde_json::{json, Value};
use std::{collections::BTreeMap, sync::Arc};
use tempfile::TempDir;
use virtuus_store::{FileStore, JournaledStore, MemoryCatalog, Scope};

mod support;
use support::{PausePoint, PauseStore};

fn board() -> (TempDir, Api, Arc<PauseStore>) {
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
    let api = Api::new(store, objects.clone()).unwrap();
    (directory, api, objects)
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

fn assert_global_invariants(directory: &TempDir) {
    let mut issues: BTreeMap<String, Value> = BTreeMap::new();
    for entry in std::fs::read_dir(directory.path().join("project/issues")).unwrap() {
        let raw: Value =
            serde_json::from_slice(&std::fs::read(entry.unwrap().path()).unwrap()).unwrap();
        issues.insert(raw["id"].as_str().unwrap().to_string(), raw);
    }
    for (identifier, issue) in &issues {
        if let Some(parent) = issue["parent"].as_str() {
            assert!(
                issues.contains_key(parent),
                "{identifier} has missing parent {parent}"
            );
        }
        for link in issue["dependencies"].as_array().unwrap() {
            let target = link["target"].as_str().unwrap();
            assert!(
                issues.contains_key(target),
                "{identifier} has missing dependency target {target}"
            );
        }
    }
}

#[tokio::test]
async fn attach_in_flight_while_parent_is_deleted_never_leaves_an_orphan() {
    let (directory, api, objects) = board();
    let epic = create(&api, json!({"title":"Epic","type":"epic"})).await;
    let epic_id = epic["issue"]["id"].as_str().unwrap().to_string();
    let mut held = objects.arm(PausePoint::BeforePut, "project/issues/");
    let attaching = {
        let api = api.clone();
        let epic_id = epic_id.clone();
        tokio::spawn(async move {
            api.handle(call(
                "POST",
                "/api/issues",
                json!({"title":"Task","type":"task","parent":epic_id}),
                None,
            ))
            .await
        })
    };
    held.held().await;
    let deletion = api
        .handle(call(
            "DELETE",
            &format!("/api/issues/{epic_id}"),
            json!(null),
            epic["revision"].as_str(),
        ))
        .await;
    held.release();
    let attached = attaching.await.unwrap();
    assert_global_invariants(&directory);
    assert!(
        deletion.is_ok() != attached.is_ok(),
        "exactly one of delete and attach must win: delete={:?} attach={:?}",
        deletion.as_ref().map(|r| r.status),
        attached.as_ref().map(|r| r.status)
    );
    assert_global_invariants(&directory);
}
