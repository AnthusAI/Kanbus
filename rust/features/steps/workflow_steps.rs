use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use serde_json::Value;

use kanbus::file_io::load_project_directory;
use kanbus::models::{IssueData, PriorityDefinition, ProjectConfiguration};
use kanbus::workflows::get_workflow_for_issue_type;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn read_issue_json(project_dir: &PathBuf, identifier: &str) -> Value {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given(expr = "an issue {string} of type {string} with status {string}")]
fn given_issue_with_type_and_status(
    world: &mut KanbusWorld,
    identifier: String,
    issue_type: String,
    status: String,
) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let closed_at = if status == "closed" {
        Some(timestamp)
    } else {
        None
    };
    let issue = IssueData {
        identifier,
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type,
        status,
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at,
        custom: std::collections::BTreeMap::new(),
    };
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists")]
fn given_issue_exists(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier,
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
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
        custom: std::collections::BTreeMap::new(),
    };
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists with status {string}")]
fn given_issue_exists_with_status(world: &mut KanbusWorld, identifier: String, status: String) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let closed_at = if status == "closed" {
        Some(timestamp)
    } else {
        None
    };
    let issue = IssueData {
        identifier,
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type: "task".to_string(),
        status,
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at,
        custom: std::collections::BTreeMap::new(),
    };
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "a {string} issue {string} exists")]
fn given_typed_issue_exists(world: &mut KanbusWorld, issue_type: String, identifier: String) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier,
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type,
        status: "open".to_string(),
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
        custom: std::collections::BTreeMap::new(),
    };
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "an {string} issue {string} exists")]
fn given_typed_issue_exists_an(world: &mut KanbusWorld, issue_type: String, identifier: String) {
    given_typed_issue_exists(world, issue_type, identifier);
}

#[given(expr = "issue {string} has no closed_at timestamp")]
fn given_issue_no_closed_at(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_json(&project_dir, &identifier);
    issue["closed_at"] = Value::Null;
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    fs::write(
        issue_path,
        serde_json::to_string_pretty(&issue).expect("serialize"),
    )
    .expect("write issue");
}

#[given(expr = "issue {string} has a closed_at timestamp")]
fn given_issue_has_closed_at(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_json(&project_dir, &identifier);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    issue["closed_at"] = Value::String(timestamp.to_rfc3339());
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    fs::write(
        issue_path,
        serde_json::to_string_pretty(&issue).expect("serialize"),
    )
    .expect("write issue");
}

#[then(expr = "issue {string} should have status {string}")]
fn then_issue_status_matches(world: &mut KanbusWorld, identifier: String, status: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_json(&project_dir, &identifier);
    assert_eq!(issue["status"], status);
}

#[then(expr = "issue {string} should have assignee {string}")]
fn then_issue_assignee_matches(world: &mut KanbusWorld, identifier: String, assignee: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_json(&project_dir, &identifier);
    assert_eq!(issue["assignee"], assignee);
}

#[then(expr = "issue {string} should have a closed_at timestamp")]
fn then_issue_has_closed_at(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_json(&project_dir, &identifier);
    assert!(!issue["closed_at"].is_null());
}

#[then(expr = "issue {string} should have no closed_at timestamp")]
fn then_issue_no_closed_at(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_json(&project_dir, &identifier);
    assert!(issue["closed_at"].is_null());
}

#[given("a configuration without a default workflow")]
fn given_config_without_default_workflow(world: &mut KanbusWorld) {
    world.workflow_error = None;
}

#[when(expr = "I look up the workflow for issue type {string}")]
fn when_lookup_workflow(world: &mut KanbusWorld, issue_type: String) {
    let workflows = BTreeMap::from([(
        "epic".to_string(),
        BTreeMap::from([("open".to_string(), vec!["in_progress".to_string()])]),
    )]);
    let configuration = ProjectConfiguration {
        project_directory: "project".to_string(),
        external_projects: Vec::new(),
        ignore_paths: Vec::new(),
        console_port: None,
        project_key: "kanbus".to_string(),
        project_management_template: None,
        hierarchy: vec!["initiative".to_string(), "epic".to_string()],
        types: vec!["bug".to_string()],
        workflows,
        initial_status: "open".to_string(),
        priorities: BTreeMap::from([(
            2,
            PriorityDefinition {
                name: "medium".to_string(),
                color: None,
            },
        )]),
        default_priority: 2,
        assignee: None,
        time_zone: None,
        statuses: Vec::new(),
        type_colors: BTreeMap::new(),
        beads_compatibility: false,
    };
    match get_workflow_for_issue_type(&configuration, &issue_type) {
        Ok(_) => world.workflow_error = None,
        Err(error) => world.workflow_error = Some(error.to_string()),
    }
}

#[then("workflow lookup should fail with \"default workflow not defined\"")]
fn then_workflow_lookup_failed(world: &mut KanbusWorld) {
    assert_eq!(
        world.workflow_error.as_deref(),
        Some("default workflow not defined")
    );
}
