//! Cucumber steps for the console issue write API: comments, status changes
//! and routing assignment editing.
//!
//! These exercise the real `kbsc` server over HTTP, mirroring the Python
//! steps. "the console is open" only sets up the simulated console state, so
//! these steps provision a real project and a running server on demand and
//! seed the real project with the simulated issues.

use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use reqwest::blocking::Client;
use serde_json::{json, Value};

use kanbus::event_history::{EventRecord, EventType};
use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::console_ui_state_steps::{
    allocate_port, start_kbsc, wait_for_server, write_console_port_to_config, write_issue_file,
};
use crate::step_definitions::initialization_steps::KanbusWorld;
use crate::step_definitions::issue_creation_steps::given_kanbus_project;

const ROUTING_LABEL_SEPARATOR: &str = " \u{b7} ";

fn ensure_real_console_server(world: &mut KanbusWorld) -> u16 {
    if world.console_server_child.is_some() {
        return world.console_port.expect("console port not set");
    }
    if world.working_directory.is_none() {
        given_kanbus_project(world);
    }
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let simulated = world
        .console_state
        .as_ref()
        .map(|state| state.issues.clone())
        .unwrap_or_default();
    for issue in simulated {
        let issue_data = IssueData {
            identifier: issue.identifier.clone().unwrap_or_default(),
            title: issue.title.clone(),
            description: String::new(),
            issue_type: issue.issue_type.clone(),
            status: issue.status.clone(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: timestamp,
            updated_at: timestamp,
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        };
        write_issue_file(&project_dir, &issue_data);
    }
    let port = allocate_port();
    write_console_port_to_config(world, port);
    let child = start_kbsc(world, port);
    assert!(
        wait_for_server(port),
        "kbsc did not become ready on port {port}"
    );
    world.console_port = Some(port);
    world.console_server_child = Some(child);
    port
}

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("working directory");
    load_project_directory(cwd).expect("project dir")
}

fn issue_write_request(world: &mut KanbusWorld, issue_id: &str, route: &str, body: Value) {
    let port = ensure_real_console_server(world);
    let url = format!("http://127.0.0.1:{port}/api/issues/{issue_id}/{route}");
    let (status, payload) = thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("build http client");
        let response = client
            .post(&url)
            .header("X-Kanbus-Console", "1")
            .json(&body)
            .send()
            .expect("send issue write request");
        let status = response.status().as_u16();
        let payload: Value = response.json().expect("parse issue write response");
        (status, payload)
    })
    .join()
    .expect("issue write request thread");
    world.issue_write_status = Some(status);
    world.issue_write_payload = Some(payload);
}

fn write_payload(world: &KanbusWorld) -> &Value {
    world
        .issue_write_payload
        .as_ref()
        .expect("issue write API response missing")
}

fn assert_write_succeeded(world: &KanbusWorld) {
    assert_eq!(
        world.issue_write_status,
        Some(200),
        "{:?}",
        world.issue_write_payload
    );
}

fn sorted_labels(payload: &Value) -> Vec<String> {
    let mut labels: Vec<String> = payload["issue"]["labels"]
        .as_array()
        .expect("issue labels")
        .iter()
        .map(|label| label.as_str().expect("label").to_string())
        .collect();
    labels.sort();
    labels
}

#[given(expr = "the issue {string} has a blocked router conversation")]
fn given_issue_has_blocked_router_conversation(world: &mut KanbusWorld, issue_id: String) {
    if world.working_directory.is_none() {
        given_kanbus_project(world);
    }
    let project_dir = load_project_dir(world);
    let events_dir = project_dir.join("events");
    fs::create_dir_all(&events_dir).expect("create events directory");
    let event = EventRecord::new(
        format!("router:{issue_id}"),
        EventType::RouterConversation,
        "router",
        json!({"lifecycle": "blocked", "action": "awaiting_reply"}),
        "2026-09-19T20:00:00Z".to_string(),
    );
    fs::write(
        events_dir.join("router-conversation-blocked.json"),
        serde_json::to_string(&event).expect("serialize event"),
    )
    .expect("write router conversation event");
}

#[when(expr = "I add a comment through the issue write API for {string} with text {string}")]
fn when_add_comment_through_api(world: &mut KanbusWorld, issue_id: String, text: String) {
    issue_write_request(world, &issue_id, "comments", json!({"text": text}));
}

#[when(expr = "I change status through the issue write API for {string} to {string}")]
fn when_change_status_through_api(world: &mut KanbusWorld, issue_id: String, status: String) {
    issue_write_request(world, &issue_id, "status", json!({"status": status}));
}

#[then(expr = "the issue write API response should be successful with comment {string}")]
fn then_write_api_successful_comment(world: &mut KanbusWorld, text: String) {
    assert_write_succeeded(world);
    let comments = write_payload(world)["issue"]["comments"]
        .as_array()
        .expect("issue comments");
    assert_eq!(comments.last().expect("a comment")["text"], text);
}

#[then(expr = "the issue write API response should be successful with status {string}")]
fn then_write_api_successful_status(world: &mut KanbusWorld, status: String) {
    assert_write_succeeded(world);
    assert_eq!(write_payload(world)["issue"]["status"], status);
}

#[then(
    expr = "the issue write API response should fail with status {int} and error containing {string}"
)]
fn then_write_api_failed(world: &mut KanbusWorld, status: u16, message: String) {
    assert_eq!(
        world.issue_write_status,
        Some(status),
        "{:?}",
        world.issue_write_payload
    );
    let error = write_payload(world)["error"]
        .as_str()
        .expect("error message")
        .to_lowercase();
    assert!(
        error.contains(&message.to_lowercase()),
        "error {error:?} does not contain {message:?}"
    );
}

#[then("the issue write API response should report the agent was resumed")]
fn then_write_api_reports_resumed(world: &mut KanbusWorld) {
    assert_eq!(write_payload(world)["resumed"], Value::Bool(true));
}

#[then(expr = "the issue write API response should include status {string}")]
fn then_write_api_includes_status(world: &mut KanbusWorld, status: String) {
    assert_eq!(write_payload(world)["issue"]["status"], status);
}

#[given(expr = "the Kanbus configuration has a router with class {string} using provider {string}")]
fn given_router_with_class_and_provider(
    world: &mut KanbusWorld,
    class_name: String,
    provider: String,
) {
    ensure_real_console_server(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory")
        .join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read configuration");
    let mut config: serde_yaml::Value =
        serde_yaml::from_str(&contents).expect("parse configuration");

    let to_yaml = |value: Value| serde_yaml::to_value(value).expect("convert to yaml");
    config["statuses"]
        .as_sequence_mut()
        .expect("statuses")
        .push(to_yaml(json!({
            "key": "review",
            "name": "Review",
            "category": "In progress",
            "semantic_category": "in_progress"
        })));
    let workflow = &mut config["workflows"]["default"];
    workflow["in_progress"]
        .as_sequence_mut()
        .expect("in_progress transitions")
        .push(to_yaml(json!("review")));
    workflow["review"] = to_yaml(json!(["in_progress", "blocked", "closed"]));
    let labels = &mut config["transition_labels"]["default"];
    labels["in_progress"]["review"] = to_yaml(json!("Ready for review"));
    labels["review"] = to_yaml(json!({
        "in_progress": "Request changes",
        "blocked": "Close without merge",
        "closed": "Merge"
    }));
    config["router"] = to_yaml(json!({
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"]
        },
        "limits": {"project_wip": 3, "review_wip": 2},
        "providers": {provider.clone(): {"adapter": "codex"}},
        "classes": {class_name: {"providers": [provider]}}
    }));
    fs::write(
        &config_path,
        serde_yaml::to_string(&config).expect("serialize configuration"),
    )
    .expect("write configuration");
}

#[given(expr = "the issue {string} has labels {string}")]
fn given_issue_has_labels(world: &mut KanbusWorld, issue_id: String, labels: String) {
    ensure_real_console_server(world);
    let issue_path = load_project_dir(world)
        .join("issues")
        .join(format!("{issue_id}.json"));
    let mut issue: Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).expect("read issue"))
            .expect("parse issue");
    let parsed: Vec<&str> = labels
        .split(',')
        .map(str::trim)
        .filter(|label| !label.is_empty())
        .collect();
    issue["labels"] = json!(parsed);
    fs::write(
        &issue_path,
        serde_json::to_string_pretty(&issue).expect("serialize issue"),
    )
    .expect("write issue");
}

#[when(
    expr = "I set the routing assignment through the issue write API for {string} to {word} {string}"
)]
fn when_set_routing_assignment(
    world: &mut KanbusWorld,
    issue_id: String,
    kind: String,
    name: String,
) {
    issue_write_request(
        world,
        &issue_id,
        "assignment",
        json!({"kind": kind, "name": name}),
    );
}

#[when(expr = "I clear the routing assignment through the issue write API for {string}")]
fn when_clear_routing_assignment(world: &mut KanbusWorld, issue_id: String) {
    issue_write_request(world, &issue_id, "assignment", json!({"clear": true}));
}

#[then(expr = "the issue write API response should be successful with labels {string}")]
fn then_write_api_labels(world: &mut KanbusWorld, labels: String) {
    assert_write_succeeded(world);
    let mut expected: Vec<String> = labels.split(',').map(str::to_string).collect();
    expected.sort();
    assert_eq!(sorted_labels(write_payload(world)), expected);
}

#[then(expr = "the issue write API response should show agent assignment {string} {string}")]
fn then_write_api_shows_assignment(world: &mut KanbusWorld, kind: String, name: String) {
    let assignment = &write_payload(world)["issue"]["custom"]["agent_assignment"];
    assert!(!assignment.is_null(), "{:?}", world.issue_write_payload);
    assert_eq!(assignment["kind"], kind);
    assert_eq!(assignment["name"], name);
}

#[then("the issue write API response should show no agent assignment")]
fn then_write_api_shows_no_assignment(world: &mut KanbusWorld) {
    let custom = &write_payload(world)["issue"]["custom"];
    assert!(custom.get("agent_assignment").is_none(), "{custom:?}");
}

#[given("the console page is reloaded")]
fn given_console_page_reloaded(world: &mut KanbusWorld) {
    world.routing_choice = None;
}

#[when(expr = "I choose the routing assignment {string}")]
fn when_choose_routing_assignment(world: &mut KanbusWorld, label: String) {
    if label == "Unassigned" {
        world.routing_choice = Some(json!({"clear": true}));
        return;
    }
    let (prefix, name) = label
        .split_once(ROUTING_LABEL_SEPARATOR)
        .unwrap_or_else(|| panic!("unrecognized routing assignment label: {label}"));
    world.routing_choice = Some(json!({"kind": prefix.to_lowercase(), "name": name}));
}

#[when("I save the routing assignment")]
fn when_save_routing_assignment(world: &mut KanbusWorld) {
    let running_selected = world
        .console_state
        .as_ref()
        .and_then(|state| state.selected_task_title.as_deref())
        == Some("Running issue");
    let issue_id = if running_selected {
        "kbs-running"
    } else {
        "kbs-assign"
    };
    let choice = world
        .routing_choice
        .clone()
        .expect("no routing assignment chosen");
    issue_write_request(world, issue_id, "assignment", choice);
    assert_write_succeeded(world);
}

#[then("the routing assignment should be saved")]
fn then_routing_assignment_saved(world: &mut KanbusWorld) {
    assert_write_succeeded(world);
}

#[then(expr = "the routing assignment should read {string}")]
fn then_routing_assignment_reads(world: &mut KanbusWorld, text: String) {
    let assignment = &write_payload(world)["issue"]["custom"]["agent_assignment"];
    let actual = if assignment.is_null() {
        "Unassigned".to_string()
    } else {
        let kind = assignment["kind"].as_str().expect("assignment kind");
        let mut title_cased = kind.to_string();
        title_cased[..1].make_ascii_uppercase();
        format!(
            "{title_cased}{ROUTING_LABEL_SEPARATOR}{}",
            assignment["name"].as_str().expect("assignment name")
        )
    };
    assert_eq!(actual, text);
}

#[then("the routing assignment editor should be locked")]
fn then_routing_assignment_editor_locked(world: &mut KanbusWorld) {
    issue_write_request(
        world,
        "kbs-running",
        "assignment",
        json!({"kind": "class", "name": "implementation"}),
    );
    assert_eq!(
        world.issue_write_status,
        Some(400),
        "{:?}",
        world.issue_write_payload
    );
}
