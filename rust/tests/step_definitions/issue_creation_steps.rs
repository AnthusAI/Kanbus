use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use regex::Regex;
use serde::Deserialize;
use serde_json::Value;
use tempfile::TempDir;

use taskulus::cli::run_from_args_with_output;
use taskulus::models::IssueData;

use crate::step_definitions::initialization_steps::TaskulusWorld;

#[derive(Debug, Deserialize)]
struct ProjectMarker {
    project_dir: String,
}

fn run_cli(world: &mut TaskulusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn load_project_dir(world: &TaskulusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let contents = fs::read_to_string(cwd.join(".taskulus.yaml")).expect("read marker");
    let marker: ProjectMarker = serde_yaml::from_str(&contents).expect("parse marker");
    cwd.join(marker.project_dir)
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn capture_issue_identifier(world: &mut TaskulusWorld) -> String {
    let stdout = world.stdout.as_ref().expect("stdout");
    let regex = Regex::new(r"(tsk-[0-9a-f]{6})").expect("regex");
    let capture = regex
        .captures(stdout)
        .and_then(|matches| matches.get(1))
        .map(|match_value| match_value.as_str().to_string())
        .expect("issue id not found");
    world.stdout = Some(stdout.to_string());
    capture
}

fn load_issue_json(project_dir: &PathBuf, identifier: &str) -> Value {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given("a Taskulus project with default configuration")]
fn given_taskulus_project(world: &mut TaskulusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    run_cli(world, "tsk init");
    assert_eq!(world.exit_code, Some(0));
}

#[given("an \"epic\" issue \"tsk-epic01\" exists")]
fn given_epic_issue(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier: "tsk-epic01".to_string(),
        title: "Epic".to_string(),
        description: "".to_string(),
        issue_type: "epic".to_string(),
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

#[when("I run \"tsk create Implement OAuth2 flow\"")]
fn when_run_create_default(world: &mut TaskulusWorld) {
    run_cli(world, "tsk create Implement OAuth2 flow");
}

#[when("I run \"tsk create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent tsk-epic01 --label auth --label urgent --description \\\"Bug in login\\\"\"")]
fn when_run_create_full(world: &mut TaskulusWorld) {
    run_cli(world, "tsk create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent tsk-epic01 --label auth --label urgent --description \"Bug in login\"");
}

#[when("I run \"tsk create Bad Issue --type nonexistent\"")]
fn when_run_create_invalid_type(world: &mut TaskulusWorld) {
    run_cli(world, "tsk create Bad Issue --type nonexistent");
}

#[when("I run \"tsk create Orphan --parent tsk-nonexistent\"")]
fn when_run_create_missing_parent(world: &mut TaskulusWorld) {
    run_cli(world, "tsk create Orphan --parent tsk-nonexistent");
}

#[then("the command should succeed")]
fn then_command_succeeds(world: &mut TaskulusWorld) {
    assert_eq!(world.exit_code, Some(0));
}

#[then("stdout should contain a valid issue ID")]
fn then_stdout_contains_issue_id(world: &mut TaskulusWorld) {
    let _ = capture_issue_identifier(world);
}

#[then("an issue file should be created in the issues directory")]
fn then_issue_file_created(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let count = fs::read_dir(&issues_dir)
        .expect("read issues dir")
        .filter(|entry| {
            let Ok(item) = entry else {
                return false;
            };
            let path = item.path();
            path.extension()
                .and_then(|ext| ext.to_str())
                .map(|ext| ext == "json")
                .unwrap_or(false)
        })
        .count();
    assert_eq!(count, 1);
}

#[then("the created issue should have title \"Implement OAuth2 flow\"")]
fn then_created_issue_title(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["title"], "Implement OAuth2 flow");
}

#[then("the created issue should have type \"task\"")]
fn then_created_issue_type_task(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["type"], "task");
}

#[then("the created issue should have status \"open\"")]
fn then_created_issue_status(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["status"], "open");
}

#[then("the created issue should have priority 2")]
fn then_created_issue_priority(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["priority"], 2);
}

#[then("the created issue should have an empty labels list")]
fn then_created_issue_labels_empty(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["labels"].as_array().map(Vec::len), Some(0));
}

#[then("the created issue should have an empty dependencies list")]
fn then_created_issue_dependencies_empty(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["dependencies"].as_array().map(Vec::len), Some(0));
}

#[then("the created issue should have a created_at timestamp")]
fn then_created_issue_created_at(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert!(payload.get("created_at").is_some());
}

#[then("the created issue should have an updated_at timestamp")]
fn then_created_issue_updated_at(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert!(payload.get("updated_at").is_some());
}

#[then("the created issue should have type \"bug\"")]
fn then_created_issue_type_bug(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["type"], "bug");
}

#[then("the created issue should have priority 1")]
fn then_created_issue_priority_one(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["priority"], 1);
}

#[then("the created issue should have assignee \"dev@example.com\"")]
fn then_created_issue_assignee(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["assignee"], "dev@example.com");
}

#[then("the created issue should have parent \"tsk-epic01\"")]
fn then_created_issue_parent(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["parent"], "tsk-epic01");
}

#[then("the created issue should have labels \"auth, urgent\"")]
fn then_created_issue_labels(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    let labels = payload["labels"]
        .as_array()
        .expect("labels array")
        .iter()
        .filter_map(|value| value.as_str())
        .collect::<Vec<_>>();
    assert_eq!(labels, vec!["auth", "urgent"]);
}

#[then("the created issue should have description \"Bug in login\"")]
fn then_created_issue_description(world: &mut TaskulusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["description"], "Bug in login");
}

#[then("stderr should contain \"unknown issue type\"")]
fn then_stderr_contains_unknown_type(world: &mut TaskulusWorld) {
    let stderr = world.stderr.as_ref().expect("stderr");
    assert!(stderr.contains("unknown issue type"));
}

#[then("stderr should contain \"not found\"")]
fn then_stderr_contains_not_found(world: &mut TaskulusWorld) {
    let stderr = world.stderr.as_ref().expect("stderr");
    assert!(stderr.contains("not found"));
}
