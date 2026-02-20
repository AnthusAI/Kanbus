use std::collections::BTreeMap;
use std::net::TcpListener;
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use axum::extract::Query;
use axum::response::IntoResponse;
use axum::routing::get;
use axum::Json;
use axum::Router;
use cucumber::{given, then};
use serde_json::{json, Value};
use tokio::sync::oneshot;

use crate::step_definitions::initialization_steps::KanbusWorld;

/// Allocate a free TCP port by binding to port 0 and reading the assigned port.
fn allocate_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("bind ephemeral port")
        .local_addr()
        .expect("read local addr")
        .port()
}

/// Build a minimal Jira issue JSON value.
fn build_jira_issue(
    key: &str,
    summary: &str,
    issue_type: &str,
    status: &str,
    priority: &str,
    parent_key: Option<&str>,
) -> Value {
    let mut fields = json!({
        "summary": summary,
        "description": null,
        "issuetype": {"name": issue_type},
        "status": {"name": status},
        "priority": {"name": priority},
        "assignee": null,
        "reporter": {"displayName": "test-reporter"},
        "labels": [],
        "comment": {"comments": []},
        "created": "2026-01-01T00:00:00.000+0000",
        "updated": "2026-01-01T00:00:00.000+0000",
        "resolutiondate": null,
    });
    if let Some(parent) = parent_key {
        fields["parent"] = json!({"key": parent});
    }
    json!({"key": key, "fields": fields})
}

#[given("a fake Jira server is running with issues:")]
async fn given_fake_jira_server(world: &mut KanbusWorld, step: &cucumber::gherkin::Step) {
    let issues: Vec<Value> = step
        .table
        .as_ref()
        .map(|table| {
            let headers: Vec<&str> = table.rows[0].iter().map(|s| s.as_str()).collect();
            table.rows[1..]
                .iter()
                .map(|row_cells| {
                    let mut map: BTreeMap<String, String> = BTreeMap::new();
                    for (header, cell) in headers.iter().zip(row_cells.iter()) {
                        map.insert(header.to_string(), cell.clone());
                    }
                    let key = map.get("key").map(String::as_str).unwrap_or("");
                    let summary = map.get("summary").map(String::as_str).unwrap_or("");
                    let issue_type = map.get("type").map(String::as_str).unwrap_or("Task");
                    let status = map.get("status").map(String::as_str).unwrap_or("To Do");
                    let priority = map.get("priority").map(String::as_str).unwrap_or("Medium");
                    let parent = map
                        .get("parent")
                        .filter(|s| !s.is_empty())
                        .map(String::as_str);
                    build_jira_issue(key, summary, issue_type, status, priority, parent)
                })
                .collect()
        })
        .unwrap_or_default();

    let port = allocate_port();
    let issues = Arc::new(issues);
    let issues_clone = Arc::clone(&issues);

    let app = Router::new().route(
        "/rest/api/3/search/jql",
        get(move |Query(params): Query<BTreeMap<String, String>>| {
            let issues = Arc::clone(&issues_clone);
            async move {
                let start_at: usize = params
                    .get("startAt")
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(0);
                let max_results: usize = params
                    .get("maxResults")
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(100);
                let total = issues.len();
                let page: Vec<Value> = issues
                    .iter()
                    .skip(start_at)
                    .take(max_results)
                    .cloned()
                    .collect();
                Json(json!({
                    "issues": page,
                    "total": total,
                    "startAt": start_at,
                    "maxResults": max_results,
                }))
                .into_response()
            }
        }),
    );

    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();

    thread::spawn(move || {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("tokio runtime");
        rt.block_on(async move {
            let listener = tokio::net::TcpListener::bind(format!("127.0.0.1:{port}"))
                .await
                .expect("bind fake jira");
            axum::serve(listener, app)
                .with_graceful_shutdown(async move {
                    let _ = shutdown_rx.await;
                })
                .await
                .expect("serve fake jira");
        });
    });

    // Give the server a moment to start accepting connections.
    thread::sleep(Duration::from_millis(50));

    world.fake_jira_port = Some(port);
    world.fake_jira_shutdown_tx = Some(shutdown_tx);
    world.fake_jira_issues = issues.as_ref().clone();
}

#[given("the Kanbus configuration includes Jira settings pointing at the fake server")]
fn given_jira_config(world: &mut KanbusWorld) {
    let port = world.fake_jira_port.expect("fake jira port not set");
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    let existing = std::fs::read_to_string(&config_path).expect("read .kanbus.yml");
    let jira_block = format!(
        "\njira:\n  url: http://127.0.0.1:{port}\n  project_key: AQ\n  sync_direction: pull\n  type_mappings:\n    Task: task\n    Bug: bug\n    Workstream: epic\n"
    );
    std::fs::write(&config_path, existing + &jira_block).expect("write .kanbus.yml");
    std::env::set_var("JIRA_API_TOKEN", "test-token");
    std::env::set_var("JIRA_USER_EMAIL", "test@example.com");
    world.jira_env_set = true;
}

#[given(expr = "the environment variable {string} is unset")]
fn given_env_var_unset(world: &mut KanbusWorld, name: String) {
    let original = std::env::var(&name).ok();
    std::env::remove_var(&name);
    world.jira_unset_env_vars.push((name, original));
}

#[then(expr = "{int} issue files should exist in the issues directory")]
fn then_issue_file_count(world: &mut KanbusWorld, count: usize) {
    let issues_dir = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join("project")
        .join("issues");
    let actual = if issues_dir.exists() {
        std::fs::read_dir(&issues_dir)
            .expect("read issues dir")
            .filter_map(|e| e.ok())
            .filter(|e| {
                e.path()
                    .extension()
                    .and_then(|ext| ext.to_str())
                    .map(|ext| ext == "json")
                    .unwrap_or(false)
            })
            .count()
    } else {
        0
    };
    assert_eq!(
        actual, count,
        "Expected {count} issue files, found {actual}"
    );
}

#[then(expr = "an issue file with jira_key {string} should exist with title {string}")]
fn then_issue_exists_with_title(world: &mut KanbusWorld, jira_key: String, title: String) {
    let issue = find_issue_by_jira_key(world, &jira_key)
        .unwrap_or_else(|| panic!("No issue found with jira_key {jira_key:?}"));
    let actual_title = issue["title"].as_str().unwrap_or("");
    assert_eq!(
        actual_title, title,
        "Expected title {title:?}, got {actual_title:?}"
    );
}

#[then(expr = "an issue file with jira_key {string} should have type {string}")]
fn then_issue_has_type(world: &mut KanbusWorld, jira_key: String, issue_type: String) {
    let issue = find_issue_by_jira_key(world, &jira_key)
        .unwrap_or_else(|| panic!("No issue found with jira_key {jira_key:?}"));
    let actual = issue["type"].as_str().unwrap_or("");
    assert_eq!(
        actual, issue_type,
        "Expected type {issue_type:?}, got {actual:?}"
    );
}

#[then(
    expr = "the issue with jira_key {string} should have a parent matching the issue with jira_key {string}"
)]
fn then_issue_parent_matches(world: &mut KanbusWorld, child_key: String, parent_key: String) {
    let parent_issue = find_issue_by_jira_key(world, &parent_key)
        .unwrap_or_else(|| panic!("No issue found with jira_key {parent_key:?}"));
    let child_issue = find_issue_by_jira_key(world, &child_key)
        .unwrap_or_else(|| panic!("No issue found with jira_key {child_key:?}"));
    let expected_parent_id = parent_issue["id"].as_str().unwrap_or("");
    let actual_parent = child_issue["parent"].as_str().unwrap_or("");
    assert_eq!(
        actual_parent, expected_parent_id,
        "Expected parent {expected_parent_id:?}, got {actual_parent:?}"
    );
}

fn find_issue_by_jira_key(world: &KanbusWorld, jira_key: &str) -> Option<Value> {
    let issues_dir = world
        .working_directory
        .as_ref()?
        .join("project")
        .join("issues");
    if !issues_dir.exists() {
        return None;
    }
    for entry in std::fs::read_dir(&issues_dir).ok()?.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        if let Ok(content) = std::fs::read_to_string(&path) {
            if let Ok(data) = serde_json::from_str::<Value>(&content) {
                if data["custom"]["jira_key"].as_str() == Some(jira_key) {
                    return Some(data);
                }
            }
        }
    }
    None
}
