//! Explicit ignored proof of API CRUD against the authorized real AWS fixture.
#![cfg(feature = "aws")]

use kanbus_api::{grants_from_groups, Api, ApiRequest, Principal};
use serde_json::{json, Value};
use std::{collections::BTreeMap, sync::Arc};
use virtuus_store::{
    aws::{DynamoCatalog, S3Store},
    JournaledStore, ObjectStore, Scope, WriteCondition,
};

fn request(method: &str, path: &str, body: Value, revision: Option<&str>) -> ApiRequest {
    let mut headers = BTreeMap::from([("x-operation-id".into(), uuid::Uuid::new_v4().to_string())]);
    if let Some(revision) = revision {
        headers.insert("if-match".into(), revision.into());
    }
    let run = std::env::var("VIRTUUS_TEST_RUN").expect("unique run required");
    let board_path = match path.strip_prefix("/api/") {
        Some(rest) => format!("/proof-api/{run}/api/{rest}"),
        None => path.to_string(),
    };
    ApiRequest {
        method: method.into(),
        path: board_path,
        query: BTreeMap::new(),
        headers,
        body,
        principal: Principal {
            actor: "proof-api-member".into(),
            grants: grants_from_groups(&json!("kanbus:proof-api/*")),
            provision: false,
            delegate_actor: false,
        },
    }
}

#[tokio::test]
#[ignore = "Requires explicit authorized AWS fixture environment"]
async fn real_s3_api_quoted_revision_crud_and_audit() {
    let run = std::env::var("VIRTUUS_TEST_RUN").expect("unique run required");
    assert!(run.starts_with("proof-api-"));
    let credentials = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let objects = Arc::new(S3Store::new(
        aws_sdk_s3::Client::new(&credentials),
        std::env::var("VIRTUUS_TEST_BUCKET").unwrap(),
    ));
    let catalog = Arc::new(DynamoCatalog::new(
        aws_sdk_dynamodb::Client::new(&credentials),
        std::env::var("VIRTUUS_TEST_TABLE").unwrap(),
    ));
    let scope = Scope::new("proof-api", &run).unwrap();
    let mut configuration = kanbus::config::default_project_configuration();
    configuration.types.push("prospect".into());
    objects
        .put(
            &scope,
            ".kanbus.yml",
            serde_yaml::to_string(&configuration).unwrap().as_bytes(),
            "application/yaml",
            WriteCondition::Absent,
            None,
        )
        .await
        .unwrap();
    let api = Api::new(
        JournaledStore::new(objects.clone(), catalog),
        objects.clone(),
    )
    .unwrap();
    let config = api
        .handle(request("GET", "/api/config", json!(null), None))
        .await
        .unwrap();
    assert_eq!(config.body["actor_id"], "proof-api-member");
    let create_request = request(
        "POST",
        "/api/issues",
        json!({"title":"Real S3 API proof","type":"prospect","custom":{"contact":"proof@example.test","unknown_nested":{"preserved":true}}}),
        None,
    );
    let create_operation = create_request.headers["x-operation-id"].clone();
    let created = api.handle(create_request).await.unwrap();
    let id = created.body["issue"]["id"].as_str().unwrap();
    let path = format!("/api/issues/{id}");
    let native = created.body["revision"].as_str().unwrap();
    assert!(native.starts_with('"') && native.ends_with('"'));
    let mut replay_create = request(
        "POST",
        "/api/issues",
        json!({"title":"Real S3 API proof","type":"prospect","custom":{"contact":"proof@example.test","unknown_nested":{"preserved":true}}}),
        None,
    );
    replay_create
        .headers
        .insert("x-operation-id".into(), create_operation);
    assert_eq!(
        api.handle(replay_create).await.unwrap().body["revision"],
        created.body["revision"]
    );
    let read = api
        .handle(request("GET", &path, json!(null), None))
        .await
        .unwrap();
    assert_eq!(read.body["revision"], created.body["revision"]);
    let patched = api
        .handle(request(
            "PATCH",
            &path,
            json!({"status":"in_progress","custom":{"follow_up":"2026-10-15"}}),
            Some(native),
        ))
        .await
        .unwrap();
    assert_ne!(patched.body["revision"], created.body["revision"]);
    assert_eq!(
        patched.body["issue"]["custom"]["unknown_nested"]["preserved"],
        true
    );
    assert_eq!(
        api.handle(request(
            "PATCH",
            &path,
            json!({"title":"Stale"}),
            Some(native)
        ))
        .await
        .err()
        .unwrap()
        .status,
        409
    );
    let commented = api
        .handle(request(
            "POST",
            &format!("{path}/comments"),
            json!({"text":"Live cloud comment"}),
            patched.body["revision"].as_str(),
        ))
        .await
        .unwrap();
    assert_eq!(
        commented.body["issue"]["comments"][0]["author"],
        "proof-api-member"
    );
    let history = api
        .handle(request("GET", &format!("{path}/events"), json!(null), None))
        .await
        .unwrap();
    assert!(history.body["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|event| event["event_type"] == "comment_added"));
    let mut indexed = false;
    for _ in 0..10 {
        let list = api
            .handle(request("GET", "/api/issues", json!(null), None))
            .await
            .unwrap();
        if list.body["issues"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["issue"]["id"] == id)
        {
            indexed = true;
            break;
        }
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    }
    assert!(indexed, "catalog must converge for board query");
    let deletion = request(
        "DELETE",
        &path,
        json!(null),
        commented.body["revision"].as_str(),
    );
    let deletion_operation = deletion.headers["x-operation-id"].clone();
    let deleted = api.handle(deletion).await.unwrap();
    assert_eq!(deleted.body["deleted"], true);
    let mut replay = request(
        "DELETE",
        &path,
        json!(null),
        commented.body["revision"].as_str(),
    );
    replay
        .headers
        .insert("x-operation-id".into(), deletion_operation);
    assert_eq!(api.handle(replay).await.unwrap().body, deleted.body);
    assert_eq!(
        api.handle(request("GET", &path, json!(null), None))
            .await
            .err()
            .unwrap()
            .status,
        404
    );
    assert!(objects
        .get(&scope, &format!("project/issues/{id}.json"))
        .await
        .unwrap()
        .is_none());
    let history = api
        .handle(request("GET", &format!("{path}/events"), json!(null), None))
        .await
        .unwrap();
    assert!(history.body["events"]
        .as_array()
        .unwrap()
        .iter()
        .any(|event| event["event_type"] == "issue_deleted"));
    let paths = objects
        .list(&scope, "project/events/", None, 100)
        .await
        .unwrap();
    assert!(paths
        .paths
        .iter()
        .all(|path| path.contains("__") && path.ends_with(".json")));
    let restore_create = request(
        "POST",
        "/api/issues",
        json!({"title":"Recovery restore proof","type":"prospect"}),
        None,
    );
    let restore_operation = restore_create.headers["x-operation-id"].clone();
    let restore_created = api.handle(restore_create).await.unwrap();
    let restored_id = restore_created.body["issue"]["id"].as_str().unwrap();
    api.handle(request(
        "DELETE",
        &format!("/api/issues/{restored_id}"),
        json!(null),
        restore_created.body["revision"].as_str(),
    ))
    .await
    .unwrap();
    let mut restored = restore_created.body["issue"].clone();
    restored["future_extension"] = json!("x".repeat(2 * 1024 * 1024));
    objects
        .put(
            &scope,
            &format!("project/issues/{restored_id}.json"),
            &serde_json::to_vec(&restored).unwrap(),
            "application/json",
            WriteCondition::Absent,
            None,
        )
        .await
        .unwrap();
    let mut restore_retry = request(
        "POST",
        "/api/issues",
        json!({"title":"Recovery restore proof","type":"prospect"}),
        None,
    );
    restore_retry
        .headers
        .insert("x-operation-id".into(), restore_operation);
    let restored_replay = api.handle(restore_retry).await.unwrap();
    assert_eq!(restored_replay.body["issue"], restore_created.body["issue"]);
    assert_eq!(restored_replay.body["catalog_pending"], true);
    let mut oversized = created.body["issue"].clone();
    oversized["id"] = json!("imported-oversized");
    oversized["future_extension"] = json!("x".repeat(2 * 1024 * 1024));
    objects
        .put(
            &scope,
            "project/issues/imported-oversized.json",
            &serde_json::to_vec(&oversized).unwrap(),
            "application/json",
            WriteCondition::Absent,
            None,
        )
        .await
        .unwrap();
    let bounded = api
        .handle(request(
            "GET",
            "/api/issues/imported-oversized",
            json!(null),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(bounded.code, "query_budget_exceeded");
    assert_eq!(bounded.body()["cost"]["limit"], "object_bytes");
    for _ in 0..6 {
        let event_id = uuid::Uuid::new_v4().to_string();
        let large_event = json!({"schema_version":1,"event_id":event_id,"issue_id":id,"event_type":"field_updated","actor_id":"proof-api-member","occurred_at":"2026-10-14T00:00:00.000Z","payload":{"text":"x".repeat(450_000)}});
        objects
            .put(
                &scope,
                &format!("project/events/2026-10-14T00-00-00.000Z__{event_id}.json"),
                &serde_json::to_vec(&large_event).unwrap(),
                "application/json",
                WriteCondition::Absent,
                None,
            )
            .await
            .unwrap();
    }
    let history_response_error = api
        .handle(request("GET", &format!("{path}/events"), json!(null), None))
        .await
        .err()
        .unwrap();
    assert_eq!(
        history_response_error.body()["cost"]["limit"],
        "response_bytes"
    );
    let envelope = kanbus_api::api_gateway_response(
        history_response_error.status,
        history_response_error.body(),
    );
    assert!(serde_json::to_vec(&envelope).unwrap().len() < 6 * 1024 * 1024);
    let issues_before = objects
        .list(&scope, "project/issues/", None, 100)
        .await
        .unwrap()
        .paths;
    let invalid = api
        .handle(request(
            "POST",
            "/api/issues",
            json!({"title":"Rejected","type":"prospect","priority":"\\".repeat(1_000_000)}),
            None,
        ))
        .await
        .err()
        .unwrap();
    assert_eq!(invalid.status, 400);
    assert!(
        serde_json::to_vec(&kanbus_api::api_gateway_response(
            invalid.status,
            invalid.body()
        ))
        .unwrap()
        .len()
            < 4096
    );
    assert_eq!(
        objects
            .list(&scope, "project/issues/", None, 100)
            .await
            .unwrap()
            .paths,
        issues_before
    );
    let retained = objects
        .list(&scope, "project/events/", None, 100)
        .await
        .unwrap()
        .paths
        .len();
    println!(
        "API_PROOF {}",
        json!({"namespace":scope.namespace(),"issue_id":id,"create_patch_comment_delete":true,"quoted_native_revisions":true,"stale_conflict":true,"durable_retries":true,"canonical_deleted":true,"retained_events":retained,"base_audit_events":paths.paths.len(),"matching_history_response_bounded":true,"invalid_diagnostic_response_bounded":true,"oversized_import_rejected":true,"oversized_restore_replay_bounded":true,"restored_fixture_issue_id":restored_id,"history_cost":history.body["cost"]})
    );
}
