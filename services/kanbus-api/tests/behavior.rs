//! Executable examples for features/writable_api.feature.

use kanbus_api::{authenticate_cloud, authenticate_local};
use serde_json::json;

#[test]
fn cloud_requires_verified_gateway_group_membership() {
    assert!(authenticate_cloud(
        &json!({"headers":{"authorization":"Bearer forged"}}),
        "members"
    )
    .is_err());
    let claims = |groups| json!({"requestContext":{"authorizer":{"jwt":{"claims":{"sub":"member-1","cognito:groups":groups}}}}});
    assert!(authenticate_cloud(&claims("other-members"), "members").is_err());
    assert_eq!(
        authenticate_cloud(&claims("[members]"), "members").unwrap(),
        "member-1"
    );
}

#[test]
fn multiple_gateway_groups_preserve_exact_membership() {
    let event = |groups| json!({"requestContext":{"authorizer":{"jwt":{"claims":{"sub":"member-1","cognito:groups":groups}}}}});
    for groups in [
        json!(["admin", "prospectus-members"]),
        json!("[\"admin\",\"prospectus-members\"]"),
        json!("[admin, prospectus-members]"),
        json!("[admin prospectus-members]"),
        json!("admin prospectus-members"),
    ] {
        assert_eq!(
            authenticate_cloud(&event(groups), "prospectus-members").unwrap(),
            "member-1"
        );
    }
    for groups in [
        json!(["admin"]),
        json!("[admin other-prospectus-members prospectus-members-extra]"),
        json!("[admin]"),
        json!(null),
        json!(42),
    ] {
        assert_eq!(
            authenticate_cloud(&event(groups), "prospectus-members")
                .unwrap_err()
                .status,
            403
        );
    }
}

#[test]
fn local_requires_explicit_secret() {
    assert!(authenticate_local(None, "secret").is_err());
    assert!(authenticate_local(Some("Bearer wrong"), "secret").is_err());
    assert!(authenticate_local(Some("Bearer "), "").is_err());
    assert_eq!(
        authenticate_local(Some("Bearer secret"), "secret").unwrap(),
        "local-member"
    );
}

use kanbus_api::{Api, ApiRequest};
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
    (directory, Api::new(store, "tenant/project").unwrap())
}

fn request(
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
        actor: "member-1".into(),
    }
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
async fn trusted_project_allowlist_merges_selected_boards_and_rejects_unknown_scopes() {
    let directory = tempfile::tempdir().unwrap();
    for project in ["one", "two"] {
        let root = directory.path().join("tenant").join(project);
        std::fs::create_dir_all(&root).unwrap();
        let mut configuration = kanbus::config::default_project_configuration();
        configuration.project_key = project.into();
        std::fs::write(
            root.join(".kanbus.yml"),
            serde_yaml::to_string(&configuration).unwrap(),
        )
        .unwrap();
    }
    let store = JournaledStore::new(
        Arc::new(FileStore::new(directory.path()).unwrap()),
        Arc::new(MemoryCatalog::default()),
    );
    let api = Api::with_projects(store, "tenant", "one", &["one".into(), "two".into()]).unwrap();
    for project in ["one", "two"] {
        let mut create = request(
            "POST",
            "/api/issues",
            json!({"type":"task","title":project}),
            None,
        );
        create.query.insert("project".into(), project.into());
        api.handle(create).await.unwrap();
    }
    let mut list = request("GET", "/api/issues", json!(null), None);
    list.query.insert("projects".into(), "one,two".into());
    list.query.insert("types".into(), "task,bug".into());
    let response = api.handle(list).await.unwrap();
    let issues = response.body["issues"].as_array().unwrap();
    assert_eq!(issues.len(), 2);
    assert!(issues.iter().any(|entry| entry["project"] == "one"));
    assert!(issues.iter().any(|entry| entry["project"] == "two"));
    for method in ["GET", "POST"] {
        let mut denied = request(
            method,
            "/api/issues",
            json!({"type":"task","title":"denied"}),
            None,
        );
        denied.query.insert("project".into(), "other-tenant".into());
        assert_eq!(api.handle(denied).await.err().unwrap().status, 403);
    }
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
    (
        directory,
        Api::new(store.clone(), "tenant/project").unwrap(),
        store,
        objects,
    )
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
    let directory = tempfile::tempdir().unwrap();
    let store = JournaledStore::new(
        Arc::new(FileStore::new(directory.path()).unwrap()),
        Arc::new(MemoryCatalog::default()),
    );
    let projects: Vec<String> = (0..9).map(|index| format!("p{index}")).collect();
    assert!(Api::with_projects(store.clone(), "tenant", "p0", &projects).is_err());
    let api = Api::with_projects(store, "tenant", "p0", &projects[..8]).unwrap();
    let mut excessive = request("GET", "/api/issues", json!(null), None);
    excessive.query.insert("projects".into(), "*".into());
    excessive.query.insert("types".into(), "a,b,c,d,e".into());
    assert_eq!(
        api.handle(excessive).await.err().unwrap().code,
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
