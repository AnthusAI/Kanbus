use chrono::Utc;
use kanbus::config_loader::load_project_configuration;
use kanbus::doctor::run_doctor;
use kanbus::error::KanbusError;
use kanbus::hierarchy::{get_allowed_child_types, validate_parent_child_relationship};
use kanbus::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use kanbus::models::{IssueData, ProjectConfiguration};
use kanbus::users::get_current_user;
use kanbus::workflows::{
    apply_transition_side_effects, get_workflow_for_issue_type, validate_status_transition,
    validate_status_value,
};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;

fn write_base_config(root: &Path) {
    let contents = "project_key: kanbus\n";
    fs::write(root.join(".kanbus.yml"), contents).expect("write config");
    fs::create_dir_all(root.join("project/issues")).expect("create issues dir");
}

fn load_cfg(root: &Path) -> ProjectConfiguration {
    load_project_configuration(&root.join(".kanbus.yml")).expect("load config")
}

fn sample_issue(id: &str, status: &str) -> IssueData {
    IssueData {
        identifier: id.to_string(),
        title: "Title".to_string(),
        description: "Desc".to_string(),
        issue_type: "task".to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: vec!["x".to_string()],
        dependencies: vec![],
        comments: vec![],
        created_at: Utc::now(),
        updated_at: Utc::now(),
        closed_at: None,
        custom: BTreeMap::new(),
    }
}

#[test]
fn users_prefers_override_then_user_then_unknown() {
    env::set_var("KANBUS_USER", "agent");
    env::set_var("USER", "fallback");
    assert_eq!(get_current_user(), "agent");

    env::remove_var("KANBUS_USER");
    env::set_var("USER", "fallback");
    assert_eq!(get_current_user(), "fallback");

    env::remove_var("KANBUS_USER");
    env::remove_var("USER");
    assert_eq!(get_current_user(), "unknown");
}

#[test]
fn issue_files_roundtrip_and_listing() {
    let tmp = tempfile::tempdir().expect("tempdir");
    let issues = tmp.path().join("issues");
    fs::create_dir_all(&issues).expect("mkdir");

    let issue = sample_issue("kanbus-1", "open");
    let path = issue_path_for_identifier(&issues, "kanbus-1");
    write_issue_to_file(&issue, &path).expect("write issue");

    let loaded = read_issue_from_file(&path).expect("read issue");
    assert_eq!(loaded.identifier, "kanbus-1");

    fs::write(issues.join("kanbus-2.json"), "{}").expect("write second json");
    fs::write(issues.join("ignore.txt"), "x").expect("write non-json");
    let ids = list_issue_identifiers(&issues).expect("list ids");
    assert!(ids.contains("kanbus-1"));
    assert!(ids.contains("kanbus-2"));
}

#[test]
fn issue_files_errors_for_missing_or_bad_json() {
    let tmp = tempfile::tempdir().expect("tempdir");
    let missing = tmp.path().join("missing");
    match list_issue_identifiers(&missing) {
        Err(KanbusError::Io(_)) => {}
        other => panic!("expected io error, got {other:?}"),
    }

    let bad = tmp.path().join("bad.json");
    fs::write(&bad, "{not json").expect("write bad json");
    match read_issue_from_file(&bad) {
        Err(KanbusError::Io(_)) => {}
        other => panic!("expected io error, got {other:?}"),
    }
}

#[test]
fn hierarchy_allows_known_children_and_rejects_invalid() {
    let tmp = tempfile::tempdir().expect("tempdir");
    write_base_config(tmp.path());
    let cfg = load_cfg(tmp.path());

    let allowed = get_allowed_child_types(&cfg, "epic");
    assert!(allowed.iter().any(|t| t == "task"));
    assert!(allowed.iter().any(|t| t == "bug"));
    assert!(get_allowed_child_types(&cfg, "sub-task").is_empty());
    assert!(get_allowed_child_types(&cfg, "unknown").is_empty());

    match validate_parent_child_relationship(&cfg, "epic", "initiative") {
        Err(KanbusError::InvalidHierarchy(_)) => {}
        other => panic!("expected invalid hierarchy error, got {other:?}"),
    }
}

#[test]
fn workflows_validate_transitions_and_status_values() {
    let tmp = tempfile::tempdir().expect("tempdir");
    write_base_config(tmp.path());
    let mut cfg = load_cfg(tmp.path());

    let default_workflow = get_workflow_for_issue_type(&cfg, "task").expect("default workflow");
    assert!(default_workflow.contains_key("open"));

    validate_status_transition(&cfg, "task", "open", "in_progress").expect("valid transition");
    match validate_status_transition(&cfg, "task", "open", "made_up") {
        Err(KanbusError::InvalidTransition(_)) => {}
        other => panic!("expected invalid transition, got {other:?}"),
    }

    validate_status_value(&cfg, "task", "open").expect("known status");
    match validate_status_value(&cfg, "task", "nope") {
        Err(KanbusError::InvalidTransition(_)) => {}
        other => panic!("expected invalid status, got {other:?}"),
    }

    env::set_var("KANBUS_TEST_INVALID_STATUS", "1");
    match validate_status_value(&cfg, "task", "open") {
        Err(KanbusError::InvalidTransition(msg)) => assert_eq!(msg, "unknown status"),
        other => panic!("expected forced invalid status, got {other:?}"),
    }
    env::remove_var("KANBUS_TEST_INVALID_STATUS");

    cfg.workflows.clear();
    match get_workflow_for_issue_type(&cfg, "task") {
        Err(KanbusError::Configuration(msg)) => {
            assert!(msg.contains("default workflow not defined"))
        }
        other => panic!("expected configuration error, got {other:?}"),
    }
}

#[test]
fn workflow_side_effects_set_and_clear_closed_at() {
    let now = Utc::now();
    let open_issue = sample_issue("kanbus-1", "open");
    let closed_issue = sample_issue("kanbus-2", "closed");

    let closed = apply_transition_side_effects(&open_issue, "closed", now);
    assert_eq!(closed.closed_at, Some(now));

    let reopened = apply_transition_side_effects(&closed_issue, "open", now);
    assert_eq!(reopened.closed_at, None);
}

#[test]
fn doctor_fails_without_git_and_succeeds_with_git_and_config() {
    let no_git = tempfile::tempdir().expect("tempdir");
    match run_doctor(no_git.path()) {
        Err(KanbusError::Initialization(_)) => {}
        other => panic!("expected initialization error, got {other:?}"),
    }

    let repo = tempfile::tempdir().expect("tempdir");
    let status = Command::new("git")
        .arg("init")
        .current_dir(repo.path())
        .status()
        .expect("git init");
    assert!(status.success());
    write_base_config(repo.path());

    let result = run_doctor(repo.path()).expect("doctor success");
    assert_eq!(
        result.project_dir.canonicalize().expect("canonical result"),
        repo.path()
            .join("project")
            .canonicalize()
            .expect("canonical expected")
    );
}
