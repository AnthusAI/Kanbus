use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use serde::Deserialize;

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

#[given("an issue \"tsk-aaa\" exists with title \"Implement OAuth2 flow\"")]
fn given_issue_exists(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier: "tsk-aaa".to_string(),
        title: "Implement OAuth2 flow".to_string(),
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

#[given("issue \"tsk-aaa\" has status \"open\" and type \"task\"")]
fn given_issue_status_type(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("tsk-aaa.json");
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let mut payload: serde_json::Value = serde_json::from_str(&contents).expect("parse");
    payload["status"] = "open".into();
    payload["type"] = "task".into();
    let updated = serde_json::to_string_pretty(&payload).expect("serialize");
    fs::write(&issue_path, updated).expect("write issue");
}

#[when("I run \"tsk show tsk-aaa\"")]
fn when_run_show(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-aaa");
}

#[when("I run \"tsk show tsk-aaa --json\"")]
fn when_run_show_json(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-aaa --json");
}

#[when("I run \"tsk show tsk-missing\"")]
fn when_run_show_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-missing");
}

#[then("stdout should contain \"Implement OAuth2 flow\"")]
fn then_stdout_contains_title(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Implement OAuth2 flow"));
}

#[then("stdout should contain \"open\"")]
fn then_stdout_contains_status(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("open"));
}

#[then("stdout should contain \"task\"")]
fn then_stdout_contains_type(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("task"));
}

#[then("stdout should contain \"\\\"id\\\": \\\"tsk-aaa\\\"\"")]
fn then_stdout_contains_json_id(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("\"id\": \"tsk-aaa\""));
}

#[then("stdout should contain \"\\\"title\\\": \\\"Implement OAuth2 flow\\\"\"")]
fn then_stdout_contains_json_title(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("\"title\": \"Implement OAuth2 flow\""));
}
