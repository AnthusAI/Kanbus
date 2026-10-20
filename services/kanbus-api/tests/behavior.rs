//! Executable examples for features/writable_api.feature.

use kanbus_api::{
    authenticate_cloud, authenticate_local, Grant, Principal, ProjectGrant, ServicePrincipals,
};
use serde_json::json;

use kanbus_api::{grants_from_groups, Api, ApiRequest};
use std::{collections::BTreeMap, sync::Arc};
use tempfile::TempDir;
use virtuus_store::{FileStore, JournaledStore, MemoryCatalog, Scope};

fn setup() -> (TempDir, Api) {
    let directory = tempfile::tempdir().unwrap();
    let mut configuration = kanbus::config::default_project_configuration();
    configuration.project_key = "crm".into();
    configuration.types.push("prospect".into());
    std::fs::write(
        directory.path().join(".kanbus.yml"),
        serde_yaml::to_string(&configuration).unwrap(),
    )
    .unwrap();
    let scope = Scope::new("tenant", "project").unwrap();
    let objects = FileStore::for_project(directory.path(), scope).unwrap();
    let store = JournaledStore::new(Arc::new(objects), Arc::new(MemoryCatalog::default()));
    (directory, Api::new(store).unwrap())
}

fn principal_for(tenant: &str, project: &str) -> Principal {
    Principal {
        provision: false,
        delegate_actor: false,
        actor: "member-1".into(),
        grants: vec![Grant {
            tenant: tenant.into(),
            project: ProjectGrant::One(project.into()),
        }],
    }
}

fn request_as(
    principal: Principal,
    method: &str,
    path: &str,
    body: serde_json::Value,
    revision: Option<&str>,
) -> ApiRequest {
    let mut headers = BTreeMap::from([("x-operation-id".into(), uuid::Uuid::new_v4().to_string())]);
    if let Some(revision) = revision {
        headers.insert("if-match".into(), revision.into());
    }
    ApiRequest {
        method: method.into(),
        path: path.into(),
        query: BTreeMap::new(),
        headers,
        body,
        principal,
    }
}

fn request(
    method: &str,
    path: &str,
    body: serde_json::Value,
    revision: Option<&str>,
) -> ApiRequest {
    let board_path = match path.strip_prefix("/api/") {
        Some(rest) => format!("/tenant/project/api/{rest}"),
        None => path.to_string(),
    };
    request_as(
        principal_for("tenant", "project"),
        method,
        &board_path,
        body,
        revision,
    )
}

#[tokio::test]
async fn configured_issue_mutation_preserves_unknown_fields_and_normal_history_paths() {
    let (directory, api) = setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"type":"prospect","title":"Example","custom":{"source":"demo"}}),
            None,
        ))
        .await
        .unwrap();
    let identifier = created.body["issue"]["id"].as_str().unwrap();
    let path = format!("/api/issues/{identifier}");
    let issue_file = directory
        .path()
        .join(format!("project/issues/{identifier}.json"));
    assert!(issue_file.exists());
    let mut raw: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&issue_file).unwrap()).unwrap();
    raw["future_extension"] = json!({"unknown":[null,1,"keep"]});
    std::fs::write(&issue_file, serde_json::to_vec_pretty(&raw).unwrap()).unwrap();
    let current = api
        .handle(request("GET", &path, json!(null), None))
        .await
        .unwrap();
    let revision = current.body["revision"].as_str().unwrap();
    let updated = api
        .handle(request(
            "PATCH",
            &path,
            json!({"status":"in_progress","custom":{"next_follow_up_at":"2026-10-15"}}),
            Some(revision),
        ))
        .await
        .unwrap();
    assert_eq!(
        updated.body["issue"]["future_extension"],
        raw["future_extension"]
    );
    assert_eq!(updated.body["issue"]["custom"]["source"], "demo");
    assert_eq!(updated.body["issue"]["status"], "in_progress");
    assert_ne!(updated.body["revision"], current.body["revision"]);
    assert!(!updated.body["catalog_pending"].as_bool().unwrap());
    let conflict = api
        .handle(request(
            "PATCH",
            &path,
            json!({"title":"overwrite"}),
            Some(revision),
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(conflict.status, 409);
    let commented = api
        .handle(request(
            "POST",
            &format!("{path}/comments"),
            json!({"text":"Call scheduled"}),
            updated.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    assert_eq!(commented.body["issue"]["comments"][0]["author"], "member-1");
    let history = api
        .handle(request("GET", &format!("{path}/events"), json!(null), None))
        .await
        .unwrap();
    let events = history.body["events"].as_array().unwrap();
    assert!(events
        .iter()
        .any(|event| event["event_type"] == "state_transition"));
    assert!(events
        .iter()
        .any(|event| event["event_type"] == "comment_added"));
    assert!(
        std::fs::read_dir(directory.path().join("project/events"))
            .unwrap()
            .count()
            >= 3
    );
}

#[tokio::test]
async fn invalid_workflow_type_and_protected_fields_do_not_change_canonical_issue() {
    let (directory, api) = setup();
    assert_eq!(
        api.handle(request(
            "POST",
            "/api/issues",
            json!({"type":"invented","title":"No"}),
            None
        ))
        .await
        .err()
        .unwrap()
        .status,
        400
    );
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"type":"prospect","title":"Valid"}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    let path = format!("/api/issues/{id}");
    let file = directory.path().join(format!("project/issues/{id}.json"));
    let bytes = std::fs::read(&file).unwrap();
    for body in [
        json!({"status":"blocked"}),
        json!({"creator":"other"}),
        json!({"comments":[]}),
        json!({"priority":99}),
    ] {
        let error = api
            .handle(request(
                "PATCH",
                &path,
                body,
                created.body["revision"].as_str(),
            ))
            .await
            .err()
            .unwrap();
        assert_eq!(error.status, 400);
        assert_eq!(std::fs::read(&file).unwrap(), bytes);
    }
    assert_eq!(
        api.handle(request(
            "PATCH",
            &path,
            json!({"title":"No revision"}),
            None
        ))
        .await
        .err()
        .unwrap()
        .status,
        428
    );
    assert_eq!(
        api.handle(request("GET", "/api/issues/..", json!(null), None))
            .await
            .err()
            .unwrap()
            .status,
        400
    );
}

#[tokio::test]
async fn generic_filters_and_paging_are_scope_and_query_bound() {
    let (_directory, api) = setup();
    for (title, assignee, date, priority) in [
        ("first", "member-1", "2026-10-13", 1),
        ("second", "member-1", "2026-10-14", 2),
        ("later", "member-2", "2026-11-01", 0),
    ] {
        api.handle(request("POST","/api/issues",json!({"type":"prospect","title":title,"assignee":assignee,"priority":priority,"custom":{"next_follow_up_at":date}}),None)).await.unwrap();
    }
    let mut query = request("GET", "/api/issues", json!(null), None);
    query.query = BTreeMap::from([
        ("type".into(), "prospect".into()),
        ("assignee".into(), "member-1".into()),
        (
            "fields".into(),
            json!([{"field":"custom.next_follow_up_at","operator":"lte","value":"2026-10-14"}])
                .to_string(),
        ),
        ("sort".into(), "priority".into()),
        ("limit".into(), "1".into()),
    ]);
    let parameters = query.query.clone();
    let page = api.handle(query).await.unwrap();
    assert_eq!(page.body["issues"][0]["issue"]["title"], "first");
    let cursor = page.body["next_cursor"].as_str().unwrap();
    let mut next = request("GET", "/api/issues", json!(null), None);
    next.query = parameters.clone();
    next.query.insert("cursor".into(), cursor.into());
    let second = api.handle(next).await.unwrap();
    assert_eq!(second.body["issues"][0]["issue"]["title"], "second");
    assert!(second.body["next_cursor"].is_null());
    let mut changed = request("GET", "/api/issues", json!(null), None);
    changed.query = parameters;
    changed.query.insert("cursor".into(), cursor.into());
    changed.query.insert("assignee".into(), "member-2".into());
    assert_eq!(api.handle(changed).await.err().unwrap().status, 400);
}

#[tokio::test]
async fn retry_receipts_replay_original_create_and_reject_changed_requests() {
    let (_directory, api) = setup();
    let mut create = request(
        "POST",
        "/api/issues",
        json!({"type":"prospect","title":"One only"}),
        None,
    );
    let operation_id = create.headers["x-operation-id"].clone();
    let created = api.handle(create).await.unwrap();
    create = request(
        "POST",
        "/api/issues",
        json!({"type":"prospect","title":"One only"}),
        None,
    );
    create
        .headers
        .insert("x-operation-id".into(), operation_id.clone());
    let replay = api.handle(create).await.unwrap();
    assert_eq!(created.body["issue"], replay.body["issue"]);
    assert_eq!(created.body["revision"], replay.body["revision"]);
    let mut changed = request(
        "POST",
        "/api/issues",
        json!({"type":"prospect","title":"Different"}),
        None,
    );
    changed
        .headers
        .insert("x-operation-id".into(), operation_id);
    assert_eq!(api.handle(changed).await.err().unwrap().status, 409);
    let listed = api
        .handle(request("GET", "/api/issues", json!(null), None))
        .await
        .unwrap();
    assert_eq!(listed.body["issues"].as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn policies_and_hooks_reject_every_mutation_and_configuration_omits_secrets() {
    for policy in [true, false] {
        let (directory, api) = setup();
        let created = api
            .handle(request(
                "POST",
                "/api/issues",
                json!({"title":"Existing","type":"task"}),
                None,
            ))
            .await
            .unwrap();
        let identifier = created.body["issue"]["id"].as_str().unwrap();
        let path = format!("/api/issues/{identifier}");
        let file = directory
            .path()
            .join(format!("project/issues/{identifier}.json"));
        let before = std::fs::read(&file).unwrap();
        let events_before = std::fs::read_dir(directory.path().join("project/events"))
            .unwrap()
            .count();
        let configuration_file = directory.path().join(".kanbus.yml");
        let mut configuration: kanbus::models::ProjectConfiguration =
            serde_yaml::from_slice(&std::fs::read(&configuration_file).unwrap()).unwrap();
        configuration.coordination.mutex_api.bearer_token = Some("private-token".into());
        configuration.hooks.before.insert(
            "issue.create".into(),
            vec![kanbus::models::HookDefinition {
                id: "private-hook".into(),
                command: vec!["private-command".into()],
                blocking: None,
                timeout_ms: None,
                cwd: None,
                env: BTreeMap::from([("SECRET".into(), "private-env".into())]),
            }],
        );
        configuration.hooks.enabled = !policy;
        std::fs::write(
            &configuration_file,
            serde_yaml::to_string(&configuration).unwrap(),
        )
        .unwrap();
        if policy {
            std::fs::create_dir_all(directory.path().join("project/policies/nested")).unwrap();
            std::fs::write(
                directory
                    .path()
                    .join("project/policies/nested/guard.policy"),
                "policy",
            )
            .unwrap();
        }
        let public = api
            .handle(request("GET", "/api/config", json!(null), None))
            .await
            .unwrap();
        assert_eq!(public.body["actor_id"], "member-1");
        assert!(public.body.get("hooks").is_none());
        assert!(public.body.get("coordination").is_none());
        assert!(!public.body.to_string().contains("private-"));
        for (method, target, body) in [
            (
                "POST",
                "/api/issues".to_string(),
                json!({"title":"Blocked","type":"task"}),
            ),
            ("PATCH", path.clone(), json!({"title":"Blocked"})),
            ("DELETE", path.clone(), json!(null)),
            (
                "POST",
                format!("{path}/comments"),
                json!({"text":"Blocked"}),
            ),
        ] {
            let error = api
                .handle(request(
                    method,
                    &target,
                    body,
                    created.body["revision"].as_str(),
                ))
                .await
                .err()
                .unwrap();
            assert_eq!(error.status, 409);
            assert_eq!(
                error.code,
                if policy {
                    "unsupported_project_policy"
                } else {
                    "unsupported_project_hooks"
                }
            );
            assert_eq!(std::fs::read(&file).unwrap(), before);
            assert_eq!(
                std::fs::read_dir(directory.path().join("project/events"))
                    .unwrap()
                    .count(),
                events_before
            );
        }
    }
}

#[tokio::test]
async fn changing_parent_type_rejects_invalid_existing_child() {
    let (directory, api) = setup();
    let parent = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Parent","type":"task"}),
            None,
        ))
        .await
        .unwrap();
    let id = parent.body["issue"]["id"].as_str().unwrap();
    let mut child = parent.body["issue"].clone();
    child["id"] = json!("crm-imported-child");
    child["type"] = json!("sub-task");
    child["parent"] = json!(id);
    std::fs::write(
        directory
            .path()
            .join("project/issues/crm-imported-child.json"),
        serde_json::to_vec(&child).unwrap(),
    )
    .unwrap();
    let file = directory.path().join(format!("project/issues/{id}.json"));
    let before = std::fs::read(&file).unwrap();
    let error = api
        .handle(request(
            "PATCH",
            &format!("/api/issues/{id}"),
            json!({"type":"bug"}),
            parent.body["revision"].as_str(),
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.status, 409);
    assert_eq!(error.code, "unsupported_relation_mutation");
    assert_eq!(std::fs::read(file).unwrap(), before);
}

#[tokio::test]
async fn imported_dotted_identifier_can_be_read_and_patched() {
    let (directory, api) = setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Imported","type":"task"}),
            None,
        ))
        .await
        .unwrap();
    let mut raw = created.body["issue"].clone();
    raw["id"] = json!("crm-parent.1");
    let file = directory.path().join("project/issues/crm-parent.1.json");
    std::fs::write(&file, serde_json::to_vec(&raw).unwrap()).unwrap();
    let current = api
        .handle(request(
            "GET",
            "/api/issues/crm-parent.1",
            json!(null),
            None,
        ))
        .await
        .unwrap();
    let updated = api
        .handle(request(
            "PATCH",
            "/api/issues/crm-parent.1",
            json!({"title":"Updated"}),
            current.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    assert_eq!(updated.body["issue"]["id"], "crm-parent.1");
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&std::fs::read(file).unwrap()).unwrap()
            ["title"],
        "Updated"
    );
}

#[tokio::test]
async fn custom_numeric_filter_distinguishes_large_adjacent_integers() {
    let (_directory, api) = setup();
    for (title, value) in [("lower", "9007199254740992"), ("upper", "9007199254740993")] {
        let value: serde_json::Value = serde_json::from_str(value).unwrap();
        api.handle(request(
            "POST",
            "/api/issues",
            json!({"title":title,"type":"task","custom":{"amount":value}}),
            None,
        ))
        .await
        .unwrap();
    }
    let mut query = request("GET", "/api/issues", json!(null), None);
    query.query.insert(
        "fields".into(),
        r#"[{"field":"custom.amount","operator":"gt","value":9007199254740992}]"#.into(),
    );
    let result = api.handle(query).await.unwrap();
    assert_eq!(result.body["issues"].as_array().unwrap().len(), 1);
    assert_eq!(result.body["issues"][0]["issue"]["title"], "upper");
}

#[tokio::test]
async fn revision_checked_delete_retains_history_and_replays_after_record_is_gone() {
    let (directory, api) = setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Delete me","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    let path = format!("/api/issues/{id}");
    let revision = created.body["revision"].as_str().unwrap();
    assert_eq!(
        api.handle(request("DELETE", &path, json!(null), None))
            .await
            .err()
            .unwrap()
            .status,
        428
    );
    assert_eq!(
        api.handle(request("DELETE", &path, json!(null), Some("stale")))
            .await
            .err()
            .unwrap()
            .status,
        409
    );
    let deletion = request("DELETE", &path, json!(null), Some(revision));
    let operation = deletion.headers["x-operation-id"].clone();
    let deleted = api.handle(deletion).await.unwrap();
    assert_eq!(deleted.body["deleted"], true);
    assert_eq!(deleted.body["issue_id"], id);
    assert!(!directory
        .path()
        .join(format!("project/issues/{id}.json"))
        .exists());
    assert_eq!(
        api.handle(request("GET", &path, json!(null), None))
            .await
            .err()
            .unwrap()
            .status,
        404
    );
    let list = api
        .handle(request("GET", "/api/issues", json!(null), None))
        .await
        .unwrap();
    assert!(list.body["issues"].as_array().unwrap().is_empty());
    let events = api
        .handle(request("GET", &format!("{path}/events"), json!(null), None))
        .await
        .unwrap();
    assert_eq!(events.body["issue_id"], id);
    assert!(events.body["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|event| event["event_type"] == "issue_deleted"));
    let mut retry = request("DELETE", &path, json!(null), Some(revision));
    retry
        .headers
        .insert("x-operation-id".into(), operation.clone());
    assert_eq!(api.handle(retry).await.unwrap().body, deleted.body);
    let mut changed = request("DELETE", &path, json!(null), Some("different"));
    changed.headers.insert("x-operation-id".into(), operation);
    assert_eq!(api.handle(changed).await.err().unwrap().status, 409);
}

#[tokio::test]
async fn deleting_parent_with_child_is_rejected() {
    let (directory, api) = setup();
    let parent = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Parent","type":"task"}),
            None,
        ))
        .await
        .unwrap();
    let id = parent.body["issue"]["id"].as_str().unwrap();
    let mut child = parent.body["issue"].clone();
    child["id"] = json!("crm-imported-child");
    child["type"] = json!("sub-task");
    child["parent"] = json!(id);
    std::fs::write(
        directory
            .path()
            .join("project/issues/crm-imported-child.json"),
        serde_json::to_vec(&child).unwrap(),
    )
    .unwrap();
    let error = api
        .handle(request(
            "DELETE",
            &format!("/api/issues/{id}"),
            json!(null),
            parent.body["revision"].as_str(),
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.status, 409);
    assert_eq!(error.code, "unsupported_relation_mutation");
    assert!(directory
        .path()
        .join(format!("project/issues/{id}.json"))
        .exists());
}

#[tokio::test]
async fn creation_in_closed_status_applies_closure_timestamp() {
    let (_directory, api) = setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Already done","type":"task","status":"closed"}),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(
        created.body["issue"]["closed_at"],
        created.body["issue"]["created_at"]
    );
    assert!(!created.body["issue"]["closed_at"].is_null());
}

#[tokio::test]
async fn deleting_issue_with_imported_incoming_dependency_is_rejected() {
    let (directory, api) = setup();
    let target = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Target","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    let dependent = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Dependent","type":"task"}),
            None,
        ))
        .await
        .unwrap();
    let id = target.body["issue"]["id"].as_str().unwrap();
    let mut raw = dependent.body["issue"].clone();
    raw["dependencies"] = json!([{"target":id,"type":"blocked-by"}]);
    std::fs::write(
        directory.path().join(format!(
            "project/issues/{}.json",
            raw["id"].as_str().unwrap()
        )),
        serde_json::to_vec(&raw).unwrap(),
    )
    .unwrap();
    let error = api
        .handle(request(
            "DELETE",
            &format!("/api/issues/{id}"),
            json!(null),
            target.body["revision"].as_str(),
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.status, 409);
    assert_eq!(error.code, "issue_referenced");
}

#[tokio::test]
async fn relationship_mutations_fail_closed_but_imported_links_survive_status_and_comments() {
    let (directory, api) = setup();
    let parent = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Parent","type":"task"}),
            None,
        ))
        .await
        .unwrap();
    let parent_id = parent.body["issue"]["id"].as_str().unwrap();
    for body in [
        json!({"title":"Child","type":"sub-task","parent":parent_id}),
        json!({"title":"Dependent","type":"prospect","dependencies":[{"target":parent_id,"type":"blocked-by"}]}),
    ] {
        assert_eq!(
            api.handle(request("POST", "/api/issues", body, None))
                .await
                .err()
                .unwrap()
                .code,
            "unsupported_relation_mutation"
        );
    }
    let mut imported = parent.body["issue"].clone();
    imported["id"] = json!("crm-imported-child");
    imported["type"] = json!("sub-task");
    imported["parent"] = json!(parent_id);
    imported["dependencies"] = json!([{"target":parent_id,"type":"blocked-by"}]);
    imported["future_extension"] = json!({"preserved":true});
    let file = directory
        .path()
        .join("project/issues/crm-imported-child.json");
    std::fs::write(&file, serde_json::to_vec(&imported).unwrap()).unwrap();
    let path = "/api/issues/crm-imported-child";
    let current = api
        .handle(request("GET", path, json!(null), None))
        .await
        .unwrap();
    let original_bytes = std::fs::read(&file).unwrap();
    for body in [
        json!({"parent":null}),
        json!({"dependencies":[]}),
        json!({"type":"bug"}),
    ] {
        assert_eq!(
            api.handle(request(
                "PATCH",
                path,
                body,
                current.body["revision"].as_str()
            ))
            .await
            .err()
            .unwrap()
            .code,
            "unsupported_relation_mutation"
        );
        assert_eq!(std::fs::read(&file).unwrap(), original_bytes);
    }
    let updated = api
        .handle(request(
            "PATCH",
            path,
            json!({"status":"in_progress"}),
            current.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    let commented = api
        .handle(request(
            "POST",
            &format!("{path}/comments"),
            json!({"text":"Preserved"}),
            updated.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    for key in ["parent", "dependencies", "future_extension"] {
        assert_eq!(commented.body["issue"][key], imported[key]);
    }
}

#[tokio::test]
async fn nonhierarchical_type_change_remains_available() {
    let (directory, api) = setup();
    let file = directory.path().join(".kanbus.yml");
    let mut configuration: kanbus::models::ProjectConfiguration =
        serde_yaml::from_slice(&std::fs::read(&file).unwrap()).unwrap();
    configuration.types.push("customer".into());
    std::fs::write(file, serde_yaml::to_string(&configuration).unwrap()).unwrap();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Handoff","type":"prospect","custom":{"sales_history":"preserved"}}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    let changed = api
        .handle(request(
            "PATCH",
            &format!("/api/issues/{id}"),
            json!({"type":"customer","status":"in_progress"}),
            created.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    assert_eq!(changed.body["issue"]["type"], "customer");
    assert_eq!(
        changed.body["issue"]["custom"]["sales_history"],
        "preserved"
    );
}

mod support;

fn inspected_setup() -> (TempDir, Api, JournaledStore, Arc<support::InspectStore>) {
    let directory = tempfile::tempdir().unwrap();
    let mut configuration = kanbus::config::default_project_configuration();
    configuration.types.push("prospect".into());
    std::fs::write(
        directory.path().join(".kanbus.yml"),
        serde_yaml::to_string(&configuration).unwrap(),
    )
    .unwrap();
    let objects = support::InspectStore::new(
        FileStore::for_project(directory.path(), Scope::new("tenant", "project").unwrap()).unwrap(),
    );
    let store = JournaledStore::new(objects.clone(), Arc::new(MemoryCatalog::default()));
    (directory, Api::new(store.clone()).unwrap(), store, objects)
}

#[tokio::test]
async fn quoted_native_revisions_work_for_patch_comment_delete_and_stale_rejection() {
    let (_directory, api, _store, _objects) = inspected_setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Quoted","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    let path = format!(
        "/api/issues/{}",
        created.body["issue"]["id"].as_str().unwrap()
    );
    assert!(created.body["revision"].as_str().unwrap().starts_with('"'));
    let patched = api
        .handle(request(
            "PATCH",
            &path,
            json!({"title":"Patched"}),
            created.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    assert_eq!(
        api.handle(request(
            "PATCH",
            &path,
            json!({"title":"Stale"}),
            created.body["revision"].as_str()
        ))
        .await
        .err()
        .unwrap()
        .status,
        409
    );
    let comment = api
        .handle(request(
            "POST",
            &format!("{path}/comments"),
            json!({"text":"Quoted CAS"}),
            patched.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    assert_eq!(
        api.handle(request(
            "DELETE",
            &path,
            json!(null),
            comment.body["revision"].as_str()
        ))
        .await
        .unwrap()
        .body["deleted"],
        true
    );
}

#[tokio::test]
async fn limit_one_budgets_all_candidates_before_any_card_hydration_and_blocks_delete_scan() {
    use std::sync::atomic::Ordering;
    let (directory, api, store, objects) = inspected_setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Template","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    for index in 0..1001 {
        let mut raw = created.body["issue"].clone();
        raw["id"] = json!(format!("crm-budget-{index}"));
        std::fs::write(
            directory
                .path()
                .join(format!("project/issues/crm-budget-{index}.json")),
            serde_json::to_vec(&raw).unwrap(),
        )
        .unwrap();
    }
    store
        .rebuild_catalog(&Scope::new("tenant", "project").unwrap(), "project/issues/")
        .await
        .unwrap();
    objects.issue_reads.store(0, Ordering::Relaxed);
    let mut list = request("GET", "/api/issues", json!(null), None);
    list.query.insert("limit".into(), "1".into());
    let error = api.handle(list).await.err().unwrap();
    assert_eq!(error.code, "query_budget_exceeded");
    assert_eq!(error.body()["cost"]["limit"], "collected_summaries");
    assert_eq!(objects.issue_reads.load(Ordering::Relaxed), 0);
    println!("API_BUDGET_PROOF board_limit_one {}", error.body());
    let path = format!(
        "/api/issues/{}",
        created.body["issue"]["id"].as_str().unwrap()
    );
    let file = directory.path().join(format!(
        "project/issues/{}.json",
        created.body["issue"]["id"].as_str().unwrap()
    ));
    let before = std::fs::read(&file).unwrap();
    assert_eq!(
        api.handle(request(
            "DELETE",
            &path,
            json!(null),
            created.body["revision"].as_str()
        ))
        .await
        .err()
        .unwrap()
        .code,
        "query_budget_exceeded"
    );
    assert_eq!(std::fs::read(file).unwrap(), before);
}

#[tokio::test]
async fn unrelated_large_events_exceed_accepted_byte_budget() {
    use std::sync::atomic::Ordering;
    let (directory, api, _store, objects) = inspected_setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"History","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    for index in 0..40 {
        let raw = json!({"issue_id":"unrelated","event_id":format!("other-{index}"),"payload":{"text":"x".repeat(450_000)}});
        std::fs::write(
            directory
                .path()
                .join(format!("project/events/unrelated-{index:04}.json")),
            serde_json::to_vec(&raw).unwrap(),
        )
        .unwrap();
    }
    objects.event_reads.store(0, Ordering::Relaxed);
    let error = api
        .handle(request(
            "GET",
            &format!(
                "/api/issues/{}/events",
                created.body["issue"]["id"].as_str().unwrap()
            ),
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.code, "query_budget_exceeded");
    assert_eq!(error.body()["cost"]["limit"], "canonical_bytes");
    assert!(objects.event_reads.load(Ordering::Relaxed) < 40);
    println!("API_BUDGET_PROOF unrelated_history {}", error.body());
}

#[tokio::test]
async fn accepted_queries_expose_cost_and_reject_excess_streams_and_predicates() {
    let (_directory, api) = setup();
    api.handle(request(
        "POST",
        "/api/issues",
        json!({"title":"Bounded","type":"prospect"}),
        None,
    ))
    .await
    .unwrap();
    let mut list = request("GET", "/api/issues", json!(null), None);
    list.query.insert("limit".into(), "1".into());
    let accepted = api.handle(list).await.unwrap();
    assert_eq!(accepted.body["cost"]["collected_summaries"], 1);
    assert_eq!(accepted.body["cost"]["canonical_objects"], 1);
    assert!(accepted.body["cost"]["canonical_bytes"].as_u64().unwrap() > 0);
    let mut excessive = request("GET", "/api/issues", json!(null), None);
    excessive.query.insert(
        "fields".into(),
        serde_json::to_string(&vec![
            json!({"field":"priority","operator":"eq","value":2});
            17
        ])
        .unwrap(),
    );
    assert_eq!(
        api.handle(excessive).await.err().unwrap().code,
        "query_budget_exceeded"
    );
    let tenant_principal = Principal {
        provision: false,
        delegate_actor: false,
        actor: "member-1".into(),
        grants: vec![Grant {
            tenant: "tenant".into(),
            project: ProjectGrant::AllInTenant,
        }],
    };
    let tenant_list = |projects: String, types: Option<&str>| {
        let mut list = request_as(
            tenant_principal.clone(),
            "GET",
            "/tenant/api/issues",
            json!(null),
            None,
        );
        list.query.insert("projects".into(), projects);
        if let Some(types) = types {
            list.query.insert("types".into(), types.into());
        }
        list
    };
    let nine: Vec<String> = (0..9).map(|index| format!("p{index}")).collect();
    assert_eq!(
        api.handle(tenant_list(nine.join(","), None))
            .await
            .err()
            .unwrap()
            .code,
        "query_budget_exceeded"
    );
    assert_eq!(
        api.handle(tenant_list(nine[..8].join(","), Some("a,b,c,d,e")))
            .await
            .err()
            .unwrap()
            .code,
        "query_budget_exceeded"
    );
}

#[tokio::test]
async fn oversized_imported_issue_uses_bounded_backend_accessor() {
    use std::sync::atomic::Ordering;
    let (directory, api, _store, objects) = inspected_setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Imported","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    let mut imported = created.body["issue"].clone();
    imported["future_extension"] = json!("x".repeat(2 * 1024 * 1024));
    let id = imported["id"].as_str().unwrap();
    std::fs::write(
        directory.path().join(format!("project/issues/{id}.json")),
        serde_json::to_vec(&imported).unwrap(),
    )
    .unwrap();
    objects.unbounded_reads.store(0, Ordering::Relaxed);
    let error = api
        .handle(request(
            "GET",
            &format!("/api/issues/{id}"),
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.code, "query_budget_exceeded");
    assert_eq!(error.body()["cost"]["limit"], "object_bytes");
    assert_eq!(objects.unbounded_reads.load(Ordering::Relaxed), 0);
}

#[tokio::test]
async fn durable_replay_after_oversized_restore_never_uses_unbounded_canonical_reads() {
    use std::sync::atomic::Ordering;
    let (directory, api, _store, objects) = inspected_setup();
    let create = request(
        "POST",
        "/api/issues",
        json!({"title":"Restored","type":"prospect"}),
        None,
    );
    let operation = create.headers["x-operation-id"].clone();
    let created = api.handle(create).await.unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    api.handle(request(
        "DELETE",
        &format!("/api/issues/{id}"),
        json!(null),
        created.body["revision"].as_str(),
    ))
    .await
    .unwrap();
    let mut imported = created.body["issue"].clone();
    imported["future_extension"] = json!("x".repeat(2 * 1024 * 1024));
    let file = directory.path().join(format!("project/issues/{id}.json"));
    assert!(!file.exists());
    std::fs::write(&file, serde_json::to_vec(&imported).unwrap()).unwrap();
    objects.unbounded_reads.store(0, Ordering::Relaxed);
    let mut replay = request(
        "POST",
        "/api/issues",
        json!({"title":"Restored","type":"prospect"}),
        None,
    );
    replay.headers.insert("x-operation-id".into(), operation);
    let result = api.handle(replay).await.unwrap();
    assert_eq!(result.body["issue"], created.body["issue"]);
    assert_eq!(result.body["catalog_pending"], true);
    assert_eq!(objects.unbounded_reads.load(Ordering::Relaxed), 0);
    assert!(std::fs::metadata(file).unwrap().len() > 2 * 1024 * 1024);
}

#[tokio::test]
async fn mismatched_import_identity_cannot_redirect_mutation_to_identical_record() {
    let (directory, api, store, _objects) = inspected_setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Canonical","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    let canonical_file = directory.path().join(format!("project/issues/{id}.json"));
    let alias_file = directory.path().join("project/issues/crm-alias.json");
    let bytes = std::fs::read(&canonical_file).unwrap();
    std::fs::write(&alias_file, &bytes).unwrap();
    let events_before = std::fs::read_dir(directory.path().join("project/events"))
        .unwrap()
        .count();
    for (method, path, body) in [
        ("GET", "/api/issues/crm-alias", json!(null)),
        (
            "PATCH",
            "/api/issues/crm-alias",
            json!({"title":"Redirected"}),
        ),
        (
            "POST",
            "/api/issues/crm-alias/comments",
            json!({"text":"Redirected"}),
        ),
        ("DELETE", "/api/issues/crm-alias", json!(null)),
    ] {
        assert_eq!(
            api.handle(request(
                method,
                path,
                body,
                created.body["revision"].as_str()
            ))
            .await
            .err()
            .unwrap()
            .code,
            "invalid_issue"
        );
        assert_eq!(std::fs::read(&canonical_file).unwrap(), bytes);
        assert_eq!(std::fs::read(&alias_file).unwrap(), bytes);
        assert_eq!(
            std::fs::read_dir(directory.path().join("project/events"))
                .unwrap()
                .count(),
            events_before
        );
    }
    store
        .rebuild_catalog(&Scope::new("tenant", "project").unwrap(), "project/issues/")
        .await
        .unwrap();
    assert_eq!(
        api.handle(request("GET", "/api/issues", json!(null), None))
            .await
            .err()
            .unwrap()
            .code,
        "invalid_issue"
    );
}

#[tokio::test]
async fn oversized_generated_audit_event_is_rejected_before_publication() {
    let (directory, api) = setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Large audit","type":"prospect","description":"a".repeat(1_100_000)}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    let file = directory.path().join(format!("project/issues/{id}.json"));
    let before = std::fs::read(&file).unwrap();
    let history_before = std::fs::read_dir(directory.path().join("project/events"))
        .unwrap()
        .count();
    let error = api
        .handle(request(
            "PATCH",
            &format!("/api/issues/{id}"),
            json!({"description":"b".repeat(1_100_000)}),
            created.body["revision"].as_str(),
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.code, "query_budget_exceeded");
    assert_eq!(error.body()["cost"]["limit"], "event_bytes");
    assert_eq!(std::fs::read(file).unwrap(), before);
    assert_eq!(
        std::fs::read_dir(directory.path().join("project/events"))
            .unwrap()
            .count(),
        history_before
    );
}

#[tokio::test]
async fn matching_large_history_hits_response_budget_before_gateway_serialization() {
    let (directory, api) = setup();
    let created = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Matching history","type":"prospect"}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    for _ in 0..6 {
        let event_id = uuid::Uuid::new_v4().to_string();
        let event = json!({"schema_version":1,"event_id":event_id,"issue_id":id,"event_type":"field_updated","actor_id":"member-1","occurred_at":"2026-10-14T00:00:00.000Z","payload":{"text":"x".repeat(450_000)}});
        std::fs::write(
            directory.path().join(format!(
                "project/events/2026-10-14T00-00-00.000Z__{event_id}.json"
            )),
            serde_json::to_vec(&event).unwrap(),
        )
        .unwrap();
    }
    let error = api
        .handle(request(
            "GET",
            &format!("/api/issues/{id}/events"),
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.body()["cost"]["limit"], "response_bytes");
    assert!(
        serde_json::to_vec(&kanbus_api::api_gateway_response(
            error.status,
            error.body()
        ))
        .unwrap()
        .len()
            < 6 * 1024 * 1024
    );
}

#[test]
fn quote_heavy_proxy_response_is_bounded_after_actual_gateway_string_escaping() {
    let response = kanbus_api::api_gateway_response(
        200,
        json!({"payload":"\\\"".repeat(kanbus_api::MAX_RESPONSE_BODY_BYTES / 4 - 64)}),
    );
    assert_eq!(response["statusCode"], 200);
    let encoded = serde_json::to_vec(&response).unwrap();
    assert!(encoded.len() > 5_000_000);
    assert!(encoded.len() < 6 * 1024 * 1024);
    let oversized = kanbus_api::api_gateway_response(
        200,
        json!({"payload":"\\\"".repeat(kanbus_api::MAX_RESPONSE_BODY_BYTES / 4 + 64)}),
    );
    assert_eq!(oversized["statusCode"], 422);
    let body: serde_json::Value =
        serde_json::from_str(oversized["body"].as_str().unwrap()).unwrap();
    assert_eq!(body["cost"]["limit"], "response_bytes");
}

#[tokio::test]
async fn huge_invalid_priority_diagnostic_is_bounded_and_publishes_nothing() {
    let (directory, api) = setup();
    let body = json!({"title":"Rejected","type":"prospect","priority":"\\".repeat(1_000_000)});
    assert!(serde_json::to_vec(&body).unwrap().len() < 2 * 1024 * 1024);
    let error = api
        .handle(request("POST", "/api/issues", body, None))
        .await
        .err()
        .unwrap();
    assert_eq!(error.status, 400);
    let envelope = kanbus_api::api_gateway_response(error.status, error.body());
    assert!(serde_json::to_vec(&envelope).unwrap().len() < 4096);
    assert!(!directory.path().join("project/issues").exists());
    assert!(!directory.path().join("project/events").exists());
}

fn multi_board_api(boards: &[(&str, &str)]) -> (TempDir, Api) {
    let directory = tempfile::tempdir().unwrap();
    for (tenant, project) in boards {
        create_board(directory.path(), tenant, project);
    }
    let store = JournaledStore::new(
        Arc::new(FileStore::new(directory.path()).unwrap()),
        Arc::new(MemoryCatalog::default()),
    );
    (directory, Api::new(store).unwrap())
}

fn create_board(root: &std::path::Path, tenant: &str, project: &str) {
    let board_root = root.join(tenant).join(project);
    std::fs::create_dir_all(&board_root).unwrap();
    let mut configuration = kanbus::config::default_project_configuration();
    configuration.project_key = project.into();
    std::fs::write(
        board_root.join(".kanbus.yml"),
        serde_yaml::to_string(&configuration).unwrap(),
    )
    .unwrap();
}

fn grants_to(groups: &[&str]) -> Principal {
    Principal {
        provision: false,
        delegate_actor: false,
        actor: "member-1".into(),
        grants: grants_from_groups(&json!(groups)),
    }
}

#[test]
fn group_claims_parse_into_board_grants() {
    let one = |tenant: &str, project: &str| Grant {
        tenant: tenant.into(),
        project: ProjectGrant::One(project.into()),
    };
    let wildcard = |tenant: &str| Grant {
        tenant: tenant.into(),
        project: ProjectGrant::AllInTenant,
    };
    assert_eq!(
        grants_from_groups(&json!(["kanbus:acme/support", "kanbus:acme/*"])),
        vec![one("acme", "support"), wildcard("acme")]
    );
    assert_eq!(
        grants_from_groups(&json!("[kanbus:a/b kanbus:a/*]")),
        vec![one("a", "b"), wildcard("a")]
    );
    assert_eq!(
        grants_from_groups(&json!("kanbus:cyclotron/prospectus")),
        vec![one("cyclotron", "prospectus")]
    );
    assert_eq!(
        grants_from_groups(&json!("admin kanbus:a/b,editors")),
        vec![one("a", "b")]
    );
    assert!(grants_from_groups(&json!(["admins", "kanbus", "other:a/b"])).is_empty());
    for malformed in [
        "kanbus:",
        "kanbus:acme",
        "kanbus:/project",
        "kanbus:acme/",
        "kanbus:Acme/support",
        "kanbus:acme/sup port/x",
        "kanbus:acme/../x",
        "kanbus:../x",
        "kanbus:_virtuus/*",
        "kanbus:acme/a/b",
        "kanbus:*/support",
        "kanbus:acme/**",
    ] {
        assert!(
            grants_from_groups(&json!([malformed])).is_empty(),
            "{malformed} must grant nothing"
        );
    }
    assert!(grants_from_groups(&json!(42)).is_empty());
    assert!(grants_from_groups(&json!(null)).is_empty());
}

#[test]
fn cloud_authentication_grants_only_from_verified_group_claims() {
    let event = |groups: serde_json::Value| json!({"requestContext":{"authorizer":{"jwt":{"claims":{"sub":"member-1","cognito:groups":groups}}}}});
    assert_eq!(
        authenticate_cloud(
            &json!({"headers":{"authorization":"Bearer forged"}}),
            &ServicePrincipals::default()
        )
        .unwrap_err()
        .status,
        401
    );
    for groups in [json!(["admin"]), json!("other"), json!(null), json!(42)] {
        assert_eq!(
            authenticate_cloud(&event(groups), &ServicePrincipals::default())
                .unwrap_err()
                .status,
            403
        );
    }
    let principal =
        authenticate_cloud(&event(json!("kanbus:a/b")), &ServicePrincipals::default()).unwrap();
    assert_eq!(principal.actor, "member-1");
    assert!(principal.allows(&Scope::new("a", "b").unwrap()));
    assert!(!principal.allows(&Scope::new("a", "c").unwrap()));
    assert!(!principal.allows(&Scope::new("x", "b").unwrap()));
}

#[test]
fn local_requires_explicit_secret_and_grants_only_the_served_board() {
    let board = Scope::new("tenant", "project").unwrap();
    assert!(authenticate_local(None, "secret", &board, None).is_err());
    assert!(authenticate_local(Some("Bearer wrong"), "secret", &board, None).is_err());
    assert!(authenticate_local(Some("Bearer "), "", &board, None).is_err());
    let principal = authenticate_local(Some("Bearer secret"), "secret", &board, None).unwrap();
    assert_eq!(principal.actor, "local-member");
    assert!(principal.allows(&board));
    assert!(!principal.allows(&Scope::new("tenant", "other").unwrap()));
}

#[tokio::test]
async fn direct_invoke_event_routes_from_raw_path_only() {
    let (_directory, api) = multi_board_api(&[("cyclotron", "prospectus")]);
    let event = json!({
        "version":"2.0",
        "rawPath":"/cyclotron/prospectus/api/issues",
        "rawQueryString":"",
        "requestContext":{"http":{"method":"GET"},"authorizer":{"jwt":{"claims":{"sub":"prospectus-intake-evaluation","cognito:groups":"kanbus:cyclotron/prospectus"}}}}
    });
    let principal = authenticate_cloud(&event, &ServicePrincipals::default()).unwrap();
    assert_eq!(principal.actor, "prospectus-intake-evaluation");
    let mut direct = request_as(
        principal,
        "GET",
        event["rawPath"].as_str().unwrap(),
        json!(null),
        None,
    );
    direct.query.insert("limit".into(), "5".into());
    let response = api.handle(direct).await.unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.body["issues"].as_array().unwrap().len(), 0);
}

#[tokio::test]
async fn one_deployment_serves_many_boards_with_per_board_grants() {
    let (_directory, api) = multi_board_api(&[
        ("acme", "support"),
        ("acme", "sales"),
        ("globex", "support"),
    ]);
    let member = grants_to(&["kanbus:acme/support"]);
    let created = api
        .handle(request_as(
            member.clone(),
            "POST",
            "/acme/support/api/issues",
            json!({"type":"task","title":"Mine"}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap().to_string();
    let read = api
        .handle(request_as(
            member.clone(),
            "GET",
            &format!("/acme/support/api/issues/{id}"),
            json!(null),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(read.body["issue"]["title"], "Mine");

    let mut denials = Vec::new();
    for board in [
        "acme/sales",
        "globex/support",
        "globex/missing",
        "nobody/nothing",
    ] {
        for (method, suffix) in [
            ("GET", "api/issues"),
            ("POST", "api/issues"),
            ("GET", "api/config"),
        ] {
            let error = api
                .handle(request_as(
                    member.clone(),
                    method,
                    &format!("/{board}/{suffix}"),
                    json!({"type":"task","title":"Nope"}),
                    None,
                ))
                .await
                .err()
                .unwrap();
            assert_eq!(error.status, 403);
            denials.push(error.body());
        }
    }
    assert!(denials.windows(2).all(|pair| pair[0] == pair[1]));
}

#[tokio::test]
async fn tenant_wildcard_grants_every_board_of_that_tenant_only() {
    let (_directory, api) = multi_board_api(&[
        ("acme", "support"),
        ("acme", "sales"),
        ("globex", "support"),
    ]);
    let member = grants_to(&["kanbus:acme/*"]);
    for board in ["acme/support", "acme/sales"] {
        let response = api
            .handle(request_as(
                member.clone(),
                "GET",
                &format!("/{board}/api/config"),
                json!(null),
                None,
            ))
            .await
            .unwrap();
        assert_eq!(response.status, 200);
    }
    let error = api
        .handle(request_as(
            member,
            "GET",
            "/globex/support/api/config",
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(error.status, 403);
}

#[tokio::test]
async fn cross_board_list_merges_granted_boards_and_rejects_any_ungranted_board() {
    let (_directory, api) =
        multi_board_api(&[("acme", "support"), ("acme", "sales"), ("acme", "hr")]);
    let member = grants_to(&["kanbus:acme/support", "kanbus:acme/sales"]);
    for board in ["acme/support", "acme/sales"] {
        api.handle(request_as(
            member.clone(),
            "POST",
            &format!("/{board}/api/issues"),
            json!({"type":"task","title":board}),
            None,
        ))
        .await
        .unwrap();
    }
    let list = |projects: &str| {
        let mut list = request_as(member.clone(), "GET", "/acme/api/issues", json!(null), None);
        list.query.insert("projects".into(), projects.into());
        list
    };
    let response = api.handle(list("support,sales")).await.unwrap();
    let issues = response.body["issues"].as_array().unwrap();
    assert_eq!(issues.len(), 2);
    assert!(issues.iter().any(|entry| entry["project"] == "support"));
    assert!(issues.iter().any(|entry| entry["project"] == "sales"));
    let denied = api.handle(list("support,hr")).await.err().unwrap();
    assert_eq!(denied.status, 403);
    let missing = api.handle(list("support,ghost")).await.err().unwrap();
    assert_eq!(denied.body(), missing.body());
    assert_eq!(api.handle(list("*")).await.err().unwrap().status, 400);
    let mut without_names = list("support");
    without_names.query.clear();
    assert_eq!(api.handle(without_names).await.err().unwrap().status, 400);
    let mut single_board_with_projects = request_as(
        member.clone(),
        "GET",
        "/acme/support/api/issues",
        json!(null),
        None,
    );
    single_board_with_projects
        .query
        .insert("projects".into(), "support".into());
    assert_eq!(
        api.handle(single_board_with_projects)
            .await
            .err()
            .unwrap()
            .status,
        400
    );
}

#[tokio::test]
async fn invalid_tenant_and_project_names_are_rejected_before_storage_access() {
    let (_directory, api) = multi_board_api(&[("acme", "support")]);
    let everything = Principal {
        provision: false,
        delegate_actor: false,
        actor: "member-1".into(),
        grants: grants_from_groups(&json!("kanbus:acme/*")),
    };
    for path in [
        "/Acme/support/api/config",
        "/acme/Support/api/config",
        "/acme/sup%20port/api/config",
        "/acme/../api/config",
        "/../support/api/config",
        "/_virtuus/support/api/config",
        "/acme/a%2Fb/api/config",
    ] {
        let error = api
            .handle(request_as(
                everything.clone(),
                "GET",
                path,
                json!(null),
                None,
            ))
            .await
            .err()
            .unwrap();
        assert_eq!(error.status, 400, "{path}");
        assert_eq!(error.code, "invalid_request");
    }
    let mut bad_list = request_as(everything, "GET", "/acme/api/issues", json!(null), None);
    bad_list
        .query
        .insert("projects".into(), "support,Bad Name".into());
    assert_eq!(api.handle(bad_list).await.err().unwrap().status, 400);
}

#[tokio::test]
async fn granted_board_without_configuration_reports_configuration_missing() {
    let (directory, api) = multi_board_api(&[("acme", "support")]);
    std::fs::create_dir_all(directory.path().join("acme/empty")).unwrap();
    let member = grants_to(&["kanbus:acme/*"]);
    let error = api
        .handle(request_as(
            member,
            "GET",
            "/acme/empty/api/config",
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!((error.status, error.code), (503, "configuration_missing"));
}

#[tokio::test]
async fn new_board_in_storage_is_usable_without_restarting_the_service() {
    let (directory, api) = multi_board_api(&[("acme", "support")]);
    let member = grants_to(&["kanbus:acme/*"]);
    let before = api
        .handle(request_as(
            member.clone(),
            "GET",
            "/acme/newbot/api/config",
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(before.code, "configuration_missing");
    create_board(directory.path(), "acme", "newbot");
    let created = api
        .handle(request_as(
            member,
            "POST",
            "/acme/newbot/api/issues",
            json!({"type":"task","title":"First"}),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(created.status, 201);
}

#[tokio::test]
async fn operation_replay_is_scoped_per_board() {
    let (_directory, api) = multi_board_api(&[("acme", "support"), ("acme", "sales")]);
    let member = grants_to(&["kanbus:acme/*"]);
    let operation = uuid::Uuid::new_v4().to_string();
    let mut ids = Vec::new();
    for board in ["acme/support", "acme/sales"] {
        let mut create = request_as(
            member.clone(),
            "POST",
            &format!("/{board}/api/issues"),
            json!({"type":"task","title":"Same"}),
            None,
        );
        create
            .headers
            .insert("x-operation-id".into(), operation.clone());
        ids.push(api.handle(create).await.unwrap().body["issue"]["id"].clone());
    }
    let mut repeat = request_as(
        member.clone(),
        "POST",
        "/acme/support/api/issues",
        json!({"type":"task","title":"Same"}),
        None,
    );
    repeat.headers.insert("x-operation-id".into(), operation);
    let replayed = api.handle(repeat).await.unwrap();
    assert_eq!(replayed.body["issue"]["id"], ids[0]);
    for board in ["acme/support", "acme/sales"] {
        let mut list = request_as(
            member.clone(),
            "GET",
            &format!("/{board}/api/issues"),
            json!(null),
            None,
        );
        list.query.insert("limit".into(), "10".into());
        let response = api.handle(list).await.unwrap();
        assert_eq!(response.body["issues"].as_array().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn board_storage_keys_are_unchanged_and_requests_touch_only_their_board() {
    let (directory, api) = multi_board_api(&[
        ("acme", "support"),
        ("acme", "sales"),
        ("globex", "support"),
    ]);
    let member = grants_to(&["kanbus:acme/support"]);
    let snapshot = |board: &str| -> Vec<String> {
        let root = directory.path().join(board);
        let mut keys = Vec::new();
        let mut pending = vec![root.clone()];
        while let Some(current) = pending.pop() {
            for entry in std::fs::read_dir(current).unwrap() {
                let path = entry.unwrap().path();
                if path.is_dir() {
                    pending.push(path);
                } else {
                    keys.push(path.strip_prefix(&root).unwrap().to_string_lossy().into());
                }
            }
        }
        keys.sort();
        keys
    };
    let others_before = (snapshot("acme/sales"), snapshot("globex/support"));
    let created = api
        .handle(request_as(
            member.clone(),
            "POST",
            "/acme/support/api/issues",
            json!({"type":"task","title":"Keys"}),
            None,
        ))
        .await
        .unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    assert_eq!(
        Scope::new("acme", "support").unwrap().namespace(),
        "acme/support"
    );
    let keys = snapshot("acme/support");
    assert!(keys.contains(&".kanbus.yml".to_string()));
    assert!(keys.contains(&format!("project/issues/{id}.json")));
    assert_eq!(
        keys.iter()
            .filter(|key| key.starts_with("project/events/"))
            .count(),
        1
    );
    assert_eq!(
        others_before,
        (snapshot("acme/sales"), snapshot("globex/support"))
    );
}

#[tokio::test]
async fn per_board_query_semantics_match_the_single_board_contract() {
    let (_directory, api) = multi_board_api(&[("acme", "support")]);
    let member = grants_to(&["kanbus:acme/support"]);
    for (title, date, priority) in [
        ("a", "2026-10-13", 1),
        ("b", "2026-10-14", 2),
        ("c", "2026-11-01", 0),
    ] {
        api.handle(request_as(
            member.clone(),
            "POST",
            "/acme/support/api/issues",
            json!({"type":"task","title":title,"priority":priority,"custom":{"next_follow_up_at":date}}),
            None,
        ))
        .await
        .unwrap();
    }
    let mut query = request_as(
        member.clone(),
        "GET",
        "/acme/support/api/issues",
        json!(null),
        None,
    );
    query.query = BTreeMap::from([
        ("type".into(), "task".into()),
        (
            "fields".into(),
            json!([{"field":"custom.next_follow_up_at","operator":"lte","value":"2026-10-14"}])
                .to_string(),
        ),
        ("sort".into(), "priority".into()),
        ("limit".into(), "1".into()),
    ]);
    let parameters = query.query.clone();
    let page = api.handle(query).await.unwrap();
    assert_eq!(page.body["issues"][0]["issue"]["title"], "a");
    assert_eq!(
        page.body["issues"][0]["issue"]["custom"]["next_follow_up_at"],
        "2026-10-13"
    );
    let mut next = request_as(member, "GET", "/acme/support/api/issues", json!(null), None);
    next.query = parameters;
    next.query.insert(
        "cursor".into(),
        page.body["next_cursor"].as_str().unwrap().into(),
    );
    let second = api.handle(next).await.unwrap();
    assert_eq!(second.body["issues"][0]["issue"]["title"], "b");
}

const ACCOUNT: &str = "111122223333";

fn mapping(entries: serde_json::Value) -> ServicePrincipals {
    ServicePrincipals::from_json(&entries.to_string()).unwrap()
}

fn role_event(user_arn: &str, account: &str, actor: Option<&str>) -> serde_json::Value {
    let mut headers = serde_json::Map::new();
    if let Some(actor) = actor {
        headers.insert("x-kanbus-actor".into(), json!(actor));
    }
    json!({"headers":headers,"requestContext":{"authorizer":{"iam":{
        "accessKey":"ASIAEXAMPLE","accountId":account,"callerId":"AROAEXAMPLE:session",
        "userArn":user_arn,"userId":"AROAEXAMPLE:session"}}}})
}

fn assumed(name: &str, session: &str) -> String {
    format!("arn:aws:sts::{ACCOUNT}:assumed-role/{name}/{session}")
}

fn role_arn(name: &str) -> String {
    format!("arn:aws:iam::{ACCOUNT}:role/{name}")
}

fn authenticate_role(
    mapped: &ServicePrincipals,
    name: &str,
    actor: Option<&str>,
) -> Result<Principal, kanbus_api::ApiError> {
    authenticate_cloud(&role_event(&assumed(name, "s1"), ACCOUNT, actor), mapped)
}

#[tokio::test]
async fn service_role_with_all_tenants_reads_and_writes_two_tenants() {
    let (_directory, api) = multi_board_api(&[("acme", "support"), ("globex", "sales")]);
    let mapped = mapping(json!([{"role_arn":role_arn("control"),"tenants":"*"}]));
    let principal = authenticate_role(&mapped, "control", None).unwrap();
    assert_eq!(principal.actor, role_arn("control"));
    for board in ["acme/support", "globex/sales"] {
        let created = api
            .handle(request_as(
                principal.clone(),
                "POST",
                &format!("/{board}/api/issues"),
                json!({"type":"task","title":"From service"}),
                None,
            ))
            .await
            .unwrap();
        assert_eq!(created.body["issue"]["creator"], role_arn("control"));
        let id = created.body["issue"]["id"].as_str().unwrap();
        let read = api
            .handle(request_as(
                principal.clone(),
                "GET",
                &format!("/{board}/api/issues/{id}"),
                json!(null),
                None,
            ))
            .await
            .unwrap();
        assert_eq!(read.status, 200);
    }
}

#[tokio::test]
async fn tenant_limited_service_role_is_denied_with_identical_403() {
    let (_directory, api) = multi_board_api(&[("acme", "support"), ("globex", "sales")]);
    let mapped = mapping(json!([{"role_arn":role_arn("control"),"tenants":["acme"]}]));
    let principal = authenticate_role(&mapped, "control", None).unwrap();
    let allowed = api
        .handle(request_as(
            principal.clone(),
            "GET",
            "/acme/support/api/issues",
            json!(null),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(allowed.status, 200);
    let mut denials = Vec::new();
    for board in ["globex/sales", "globex/missing", "nobody/nothing"] {
        let error = api
            .handle(request_as(
                principal.clone(),
                "GET",
                &format!("/{board}/api/issues"),
                json!(null),
                None,
            ))
            .await
            .err()
            .unwrap();
        assert_eq!(error.status, 403);
        denials.push(error.body());
    }
    assert!(denials.windows(2).all(|pair| pair[0] == pair[1]));
}

#[test]
fn unknown_role_is_forbidden_and_empty_mapping_allows_no_service_callers() {
    let mapped = mapping(json!([{"role_arn":role_arn("control"),"tenants":"*"}]));
    assert_eq!(
        authenticate_role(&mapped, "other", None)
            .unwrap_err()
            .status,
        403
    );
    let none = ServicePrincipals::from_json("").unwrap();
    assert_eq!(
        authenticate_role(&none, "control", None)
            .unwrap_err()
            .status,
        403
    );
    assert_eq!(ServicePrincipals::from_json("[]").unwrap(), none);
}

#[test]
fn assumed_role_session_names_never_affect_matching() {
    let mapped = mapping(json!([{"role_arn":role_arn("control"),"tenants":"*"}]));
    for session in ["s1", "i-0abc", "a.b@c=d,e+f", "control", "Control"] {
        let event = role_event(&assumed("control", session), ACCOUNT, None);
        let principal = authenticate_cloud(&event, &mapped).unwrap();
        assert_eq!(principal.actor, role_arn("control"));
    }
    assert_eq!(
        kanbus_api::normalize_assumed_role_arn(&assumed("control", "x")),
        Some(role_arn("control"))
    );
}

#[test]
fn arn_normalization_rejects_lookalikes_other_accounts_and_malformed_arns() {
    let mapped = mapping(json!([{"role_arn":role_arn("control"),"tenants":"*"}]));
    let forbidden_arns = [
        assumed("control-admin", "s"),
        assumed("contro", "s"),
        assumed("Control", "s"),
        assumed("CONTROL", "s"),
        assumed("control ", "s"),
        assumed("control", ""),
        format!("arn:aws:sts::{ACCOUNT}:assumed-role/path/control/s"),
        format!("arn:aws:sts::{ACCOUNT}:assumed-role/control/s/extra"),
        "arn:aws:sts::999988887777:assumed-role/control/s".to_string(),
        format!("arn:aws:sts::{ACCOUNT}:federated-user/control"),
        format!("arn:aws:sts::{ACCOUNT}:assumed-role/control"),
        format!("arn:aws:iam::{ACCOUNT}:role/control"),
        format!("arn:aws:iam::{ACCOUNT}:user/control"),
        format!("arn:aws:iam::{ACCOUNT}:root"),
        format!("arn:aws:sts:us-east-1:{ACCOUNT}:assumed-role/control/s"),
        format!("arn:aws:sts::{ACCOUNT}:assumed-role/control/s:more"),
        format!("xarn:aws:sts::{ACCOUNT}:assumed-role/control/s"),
        format!("arn:aws:sts::{ACCOUNT}9:assumed-role/control/s"),
        String::new(),
    ];
    for arn in &forbidden_arns {
        let result = authenticate_cloud(&role_event(arn, ACCOUNT, None), &mapped);
        assert!(
            matches!(&result, Err(error) if error.status == 403 || error.status == 401),
            "{arn} must not authenticate"
        );
    }
    let mismatched_account = role_event(&assumed("control", "s"), "999988887777", None);
    assert_eq!(
        authenticate_cloud(&mismatched_account, &mapped)
            .unwrap_err()
            .status,
        403
    );
    let other_account_mapping =
        mapping(json!([{"role_arn":"arn:aws:iam::999988887777:role/control","tenants":"*"}]));
    assert_eq!(
        authenticate_role(&other_account_mapping, "control", None)
            .unwrap_err()
            .status,
        403
    );
    let mut missing_account = role_event(&assumed("control", "s"), ACCOUNT, None);
    missing_account["requestContext"]["authorizer"]["iam"]
        .as_object_mut()
        .unwrap()
        .remove("accountId");
    assert_eq!(
        authenticate_cloud(&missing_account, &mapped)
            .unwrap_err()
            .status,
        403
    );
    let mut missing_arn = role_event(&assumed("control", "s"), ACCOUNT, None);
    missing_arn["requestContext"]["authorizer"]["iam"]
        .as_object_mut()
        .unwrap()
        .remove("userArn");
    assert_eq!(
        authenticate_cloud(&missing_arn, &mapped)
            .unwrap_err()
            .status,
        401
    );
    assert_eq!(
        kanbus_api::normalize_assumed_role_arn("arn:aws:sts::1:assumed-role/a/b"),
        None
    );
}

#[tokio::test]
async fn delegating_service_records_header_actor_everywhere() {
    let (_directory, api) = multi_board_api(&[("acme", "support")]);
    let mapped =
        mapping(json!([{"role_arn":role_arn("control"),"tenants":"*","delegate_actor":true}]));
    for actor in [
        "chatticus:user:0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d",
        "chatticus:bot:0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d",
        "chatticus:system:task-migration",
    ] {
        let principal = authenticate_role(&mapped, "control", Some(actor)).unwrap();
        assert_eq!(principal.actor, actor);
        let created = api
            .handle(request_as(
                principal.clone(),
                "POST",
                "/acme/support/api/issues",
                json!({"type":"task","title":"Delegated"}),
                None,
            ))
            .await
            .unwrap();
        assert_eq!(created.body["issue"]["creator"], actor);
        let id = created.body["issue"]["id"].as_str().unwrap().to_string();
        let commented = api
            .handle(request_as(
                principal.clone(),
                "POST",
                &format!("/acme/support/api/issues/{id}/comments"),
                json!({"text":"Noted"}),
                created.body["revision"].as_str(),
            ))
            .await
            .unwrap();
        assert_eq!(commented.body["issue"]["comments"][0]["author"], actor);
        let history = api
            .handle(request_as(
                principal,
                "GET",
                &format!("/acme/support/api/issues/{id}/events"),
                json!(null),
                None,
            ))
            .await
            .unwrap();
        let events = history.body["events"].as_array().unwrap();
        assert!(!events.is_empty());
        assert!(events.iter().all(|event| event["actor_id"] == actor));
    }
}

#[test]
fn delegating_service_requires_a_well_formed_actor_header() {
    let mapped =
        mapping(json!([{"role_arn":role_arn("control"),"tenants":"*","delegate_actor":true}]));
    assert_eq!(
        authenticate_role(&mapped, "control", None)
            .unwrap_err()
            .status,
        400
    );
    let too_long = format!("chatticus:user:{}", "a".repeat(129));
    for malformed in [
        "",
        "chatticus",
        "chatticus:user",
        "chatticus:user:",
        "chatticus:user:a:b",
        "Chatticus:user:a",
        "chatticus:User:a",
        "chat_ticus:user:a",
        ":user:a",
        "chatticus::a",
        "chatticus:user:has space",
        "chatticus:user:a/b",
        "chatticus:user:a\nb",
        "chatticus:user:a,b",
        too_long.as_str(),
    ] {
        let error = authenticate_role(&mapped, "control", Some(malformed)).unwrap_err();
        assert_eq!(error.status, 400, "{malformed:?}");
        assert_eq!(error.code, "invalid_request");
    }
    let longest = format!("chatticus:user:{}", "a".repeat(128));
    assert!(authenticate_role(&mapped, "control", Some(&longest)).is_ok());
    assert!(authenticate_role(&mapped, "control", Some("a1:b-2:C_d.e-9")).is_ok());
}

#[test]
fn actor_header_is_forbidden_for_users_and_non_delegating_services() {
    let mapped = mapping(json!([{"role_arn":role_arn("plain"),"tenants":"*"}]));
    let service = authenticate_role(&mapped, "plain", Some("chatticus:user:x")).unwrap_err();
    assert_eq!(service.status, 403);
    let mut user = json!({"headers":{"X-Kanbus-Actor":"chatticus:user:x"},"requestContext":{"authorizer":{"jwt":{"claims":{"sub":"member-1","cognito:groups":"kanbus:a/b"}}}}});
    assert_eq!(authenticate_cloud(&user, &mapped).unwrap_err().status, 403);
    user["headers"] = json!({"x-kanbus-actor":""});
    assert_eq!(authenticate_cloud(&user, &mapped).unwrap_err().status, 403);
    user["headers"] = json!({});
    assert_eq!(
        authenticate_cloud(&user, &mapped).unwrap().actor,
        "member-1"
    );
    let board = Scope::new("tenant", "project").unwrap();
    assert_eq!(
        authenticate_local(
            Some("Bearer secret"),
            "secret",
            &board,
            Some("chatticus:user:x")
        )
        .unwrap_err()
        .status,
        403
    );
}

#[test]
fn two_roles_differing_only_in_capabilities_get_their_own_capabilities() {
    let mapped = mapping(json!([
        {"role_arn":role_arn("alpha"),"tenants":"*","provision":false,"delegate_actor":false},
        {"role_arn":role_arn("beta"),"tenants":"*","provision":true,"delegate_actor":true},
        {"role_arn":role_arn("gamma"),"tenants":"*","provision":true,"delegate_actor":false}
    ]));
    let alpha = authenticate_role(&mapped, "alpha", None).unwrap();
    assert!(!alpha.provision && !alpha.delegate_actor);
    assert_eq!(alpha.actor, role_arn("alpha"));
    let beta = authenticate_role(&mapped, "beta", Some("chatticus:user:u1")).unwrap();
    assert!(beta.provision && beta.delegate_actor);
    assert_eq!(beta.actor, "chatticus:user:u1");
    let gamma = authenticate_role(&mapped, "gamma", None).unwrap();
    assert!(gamma.provision && !gamma.delegate_actor);
    assert_eq!(
        authenticate_role(&mapped, "beta", None).unwrap_err().status,
        400
    );
    assert_eq!(
        authenticate_role(&mapped, "alpha", Some("chatticus:user:u1"))
            .unwrap_err()
            .status,
        403
    );
}

#[test]
fn authorizer_context_selects_exactly_one_authenticator() {
    let mapped = mapping(json!([{"role_arn":role_arn("control"),"tenants":"*"}]));
    let jwt = json!({"claims":{"sub":"member-1","cognito:groups":"kanbus:a/b"}});
    let iam = role_event(&assumed("control", "s"), ACCOUNT, None)["requestContext"]["authorizer"]
        ["iam"]
        .clone();
    let both = json!({"requestContext":{"authorizer":{"jwt":jwt,"iam":iam}}});
    assert_eq!(authenticate_cloud(&both, &mapped).unwrap_err().status, 401);
    for neither in [
        json!({}),
        json!({"requestContext":{}}),
        json!({"requestContext":{"authorizer":{}}}),
        json!({"requestContext":{"authorizer":{"lambda":{"sub":"x"}}}}),
        json!({"requestContext":{"authorizer":{"jwt":null,"iam":null}}}),
        json!({"headers":{"x-kanbus-actor":"a:b:c"}}),
    ] {
        assert_eq!(
            authenticate_cloud(&neither, &mapped).unwrap_err().status,
            401
        );
    }
    let only_jwt = json!({"requestContext":{"authorizer":{"jwt":jwt}}});
    assert_eq!(
        authenticate_cloud(&only_jwt, &mapped).unwrap().actor,
        "member-1"
    );
    let only_iam = json!({"requestContext":{"authorizer":{"iam":iam}}});
    assert_eq!(
        authenticate_cloud(&only_iam, &mapped).unwrap().actor,
        role_arn("control")
    );
    let forged_user_arn_in_jwt = json!({"requestContext":{"authorizer":{"jwt":{"claims":{"sub":assumed("control","s"),"cognito:groups":"admin"}}}}});
    assert_eq!(
        authenticate_cloud(&forged_user_arn_in_jwt, &mapped)
            .unwrap_err()
            .status,
        403
    );
}

#[test]
fn service_principal_configuration_is_validated() {
    let valid = |tenants: &str| {
        format!(
            r#"[{{"role_arn":"{}","tenants":{tenants}}}]"#,
            role_arn("control")
        )
    };
    assert!(ServicePrincipals::from_json(&valid(r#""*""#)).is_ok());
    assert!(ServicePrincipals::from_json(&valid(r#"["acme","globex-1"]"#)).is_ok());
    for invalid_tenants in [
        "[]",
        r#""acme""#,
        r#""**""#,
        r#"["Acme"]"#,
        r#"["a/b"]"#,
        "[1]",
        "null",
        r#"["_virtuus"]"#,
        "true",
    ] {
        assert!(
            ServicePrincipals::from_json(&valid(invalid_tenants)).is_err(),
            "{invalid_tenants}"
        );
    }
    let missing_tenants = format!(r#"[{{"role_arn":"{}"}}]"#, role_arn("control"));
    let error = ServicePrincipals::from_json(&missing_tenants).unwrap_err();
    assert!(error.contains("KANBUS_SERVICE_PRINCIPALS"), "{error}");
    let duplicated = format!(
        r#"[{{"role_arn":"{0}","tenants":"*"}},{{"role_arn":"{0}","tenants":["a"],"delegate_actor":true}}]"#,
        role_arn("control")
    );
    assert!(ServicePrincipals::from_json(&duplicated)
        .unwrap_err()
        .contains("more than once"));
    for bad_arn in [
        "arn:aws:iam::111122223333:role/path/name",
        "arn:aws:iam::111122223333:role/",
        "arn:aws:iam::111122223333:role/name/",
        "arn:aws:iam::111122223333:user/name",
        "arn:aws:iam::111122223333:role/na me",
        "arn:aws:iam::11112222333:role/name",
        "arn:aws:iam::111122223333:role/*",
        "arn:aws:sts::111122223333:assumed-role/name/s",
        "role/name",
        "*",
        "",
    ] {
        let text = format!(r#"[{{"role_arn":"{bad_arn}","tenants":"*"}}]"#);
        assert!(ServicePrincipals::from_json(&text).is_err(), "{bad_arn}");
    }
    for broken in [
        "{",
        "not json",
        r#"{"role_arn":"x"}"#,
        r#"[{"role_arn":1}]"#,
        r#"[1]"#,
    ] {
        assert!(ServicePrincipals::from_json(broken).is_err(), "{broken}");
    }
    let unknown_field = format!(
        r#"[{{"role_arn":"{}","tenants":"*","admin":true}}]"#,
        role_arn("control")
    );
    assert!(ServicePrincipals::from_json(&unknown_field).is_err());
    let parsed = ServicePrincipals::from_json(&valid(r#"["acme"]"#)).unwrap();
    let principal = authenticate_role(&parsed, "control", None).unwrap();
    assert!(principal.allows(&Scope::new("acme", "any").unwrap()));
    assert!(!principal.allows(&Scope::new("globex", "any").unwrap()));
    assert_eq!(
        ServicePrincipals::from_json("  ").unwrap(),
        ServicePrincipals::default()
    );
}
