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

fn build_issue(identifier: &str, status: &str, issue_type: &str) -> IssueData {
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

#[given("issues \"tsk-open\" and \"tsk-closed\" exist")]
fn given_issues_exist(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_open = build_issue("tsk-open", "open", "task");
    let issue_closed = build_issue("tsk-closed", "open", "task");
    write_issue_file(&project_dir, &issue_open);
    write_issue_file(&project_dir, &issue_closed);
}

#[given("issue \"tsk-closed\" has status \"closed\"")]
fn given_issue_closed_status(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_closed = build_issue("tsk-closed", "closed", "task");
    write_issue_file(&project_dir, &issue_closed);
}

#[given("issues \"tsk-task\" and \"tsk-bug\" exist")]
fn given_task_and_bug_exist(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_task = build_issue("tsk-task", "open", "task");
    let issue_bug = build_issue("tsk-bug", "open", "bug");
    write_issue_file(&project_dir, &issue_task);
    write_issue_file(&project_dir, &issue_bug);
}

#[given("issue \"tsk-bug\" has type \"bug\"")]
fn given_issue_bug_type(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_bug = build_issue("tsk-bug", "open", "bug");
    write_issue_file(&project_dir, &issue_bug);
}

#[when("I run \"tsk validate\"")]
fn when_run_validate(world: &mut TaskulusWorld) {
    run_cli(world, "tsk validate");
}

#[when("I run \"tsk stats\"")]
fn when_run_stats(world: &mut TaskulusWorld) {
    run_cli(world, "tsk stats");
}

#[then("stdout should contain \"total issues\"")]
fn then_stdout_contains_total(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("total issues"));
}

#[then("stdout should contain \"open issues\"")]
fn then_stdout_contains_open(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("open issues"));
}

#[then("stdout should contain \"closed issues\"")]
fn then_stdout_contains_closed(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("closed issues"));
}

#[then("stdout should contain \"task\"")]
fn then_stdout_contains_task(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("task"));
}

#[then("stdout should contain \"bug\"")]
fn then_stdout_contains_bug(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("bug"));
}
