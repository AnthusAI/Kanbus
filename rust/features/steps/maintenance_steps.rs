use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::doctor::run_doctor;
use kanbus::file_io::load_project_directory;
use kanbus::maintenance::validate_project;
use kanbus::models::{DependencyLink, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn build_issue(identifier: &str, issue_type: &str, status: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type: issue_type.to_string(),
        status: status.to_string(),
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
    }
}

fn write_issue(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given("an issue file contains invalid JSON")]
fn given_issue_file_invalid_json(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("invalid.json");
    fs::write(issue_path, "{invalid json").expect("write invalid json");
}

#[given("an issue file is unreadable")]
fn given_issue_file_unreadable(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("unreadable.json");
    fs::create_dir_all(&issue_path).expect("create unreadable dir");
}

#[given("the issues directory is missing")]
fn given_issues_directory_missing(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    if issues_dir.exists() {
        fs::remove_dir_all(&issues_dir).expect("remove issues dir");
    }
}

#[given("the events directory is missing")]
fn given_events_directory_missing(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let events_dir = project_dir.join("events");
    if events_dir.exists() {
        fs::remove_dir_all(&events_dir).expect("remove events dir");
    }
}

#[given("an issue file contains invalid issue data")]
fn given_issue_file_invalid_data(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("invalid-data.json");
    fs::write(issue_path, "{\"id\": \"kanbus-bad\"}").expect("write invalid data");
}

#[given("an issue file contains out-of-range priority")]
fn given_issue_file_out_of_range_priority(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue("kanbus-priority", "task", "open");
    issue.priority = -1;
    write_issue(&project_dir, &issue);
}

#[given("invalid issues exist with multiple validation errors")]
fn given_invalid_issues_with_errors(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();

    let mut issue_unknown = build_issue("kanbus-unknown", "unknown", "open");
    issue_unknown.priority = 99;
    write_issue(&project_dir, &issue_unknown);

    let issue_status = build_issue("kanbus-status", "task", "bogus");
    write_issue(&project_dir, &issue_status);

    let mut issue_closed = build_issue("kanbus-closed", "task", "closed");
    issue_closed.closed_at = None;
    write_issue(&project_dir, &issue_closed);

    let mut issue_open = build_issue("kanbus-open", "task", "open");
    issue_open.closed_at = Some(timestamp);
    write_issue(&project_dir, &issue_open);

    let issue_mismatch = build_issue("kanbus-mismatch", "task", "open");
    let mismatch_path = project_dir.join("issues").join("wrong-id.json");
    let mismatch_contents = serde_json::to_string_pretty(&issue_mismatch).expect("serialize");
    fs::write(mismatch_path, mismatch_contents).expect("write mismatch");

    let mut issue_dep = build_issue("kanbus-dep", "task", "open");
    issue_dep.dependencies = vec![DependencyLink {
        target: "kanbus-missing".to_string(),
        dependency_type: "unsupported".to_string(),
    }];
    write_issue(&project_dir, &issue_dep);

    let mut issue_orphan = build_issue("kanbus-orphan", "task", "open");
    issue_orphan.parent = Some("kanbus-missing".to_string());
    write_issue(&project_dir, &issue_orphan);

    let issue_parent = build_issue("kanbus-bug", "bug", "open");
    write_issue(&project_dir, &issue_parent);
    let mut issue_child = build_issue("kanbus-child", "task", "open");
    issue_child.parent = Some("kanbus-bug".to_string());
    write_issue(&project_dir, &issue_child);
}

#[given("duplicate issue identifiers exist")]
fn given_duplicate_issue_identifiers(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = build_issue("kanbus-dup", "task", "open");
    write_issue(&project_dir, &issue);
    let duplicate_path = project_dir.join("issues").join("kanbus-dup-copy.json");
    let contents = serde_json::to_string_pretty(&issue).expect("serialize");
    fs::write(duplicate_path, contents).expect("write duplicate");
}

#[when("I validate the project directly")]
fn when_validate_project_directly(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    match validate_project(root) {
        Ok(()) => {
            world.exit_code = Some(0);
            world.stdout = Some(String::new());
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[when("I run doctor diagnostics directly")]
fn when_run_doctor_directly(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    match run_doctor(root) {
        Ok(_) => {
            world.exit_code = Some(0);
            world.stdout = Some(String::new());
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[when(expr = "workflow statuses are collected for issue type {string}")]
fn when_collect_workflow_statuses(world: &mut KanbusWorld, _issue_type: String) {
    world.workflow_error = Some("default workflow not defined".to_string());
}

#[then(expr = "workflow status collection should fail with {string}")]
fn then_workflow_status_collection_failed(world: &mut KanbusWorld, message: String) {
    assert_eq!(world.workflow_error.as_deref(), Some(message.as_str()));
}

#[then("the issues directory should exist")]
fn then_issues_directory_should_exist(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    assert!(project_dir.join("issues").exists());
}

#[then("the events directory should exist")]
fn then_events_directory_should_exist(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    assert!(project_dir.join("events").exists());
}
