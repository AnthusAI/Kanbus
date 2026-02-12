use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::file_io::load_project_directory;
use taskulus::models::IssueData;

use crate::step_definitions::initialization_steps::TaskulusWorld;

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
    load_project_directory(cwd).expect("project dir")
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn load_issue(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given("an issue \"tsk-aaa\" exists with title \"Old Title\"")]
fn given_issue_with_title(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier: "tsk-aaa".to_string(),
        title: "Old Title".to_string(),
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

#[when("I run \"tsk update tsk-aaa --title \\\"New Title\\\" --description \\\"Updated description\\\"\"")]
fn when_run_update_title(world: &mut TaskulusWorld) {
    run_cli(
        world,
        "tsk update tsk-aaa --title \"New Title\" --description \"Updated description\"",
    );
}

#[when("I run \"tsk update tsk-aaa --status in_progress\"")]
fn when_run_update_status(world: &mut TaskulusWorld) {
    run_cli(world, "tsk update tsk-aaa --status in_progress");
}

#[when("I run \"tsk update tsk-aaa --status blocked\"")]
fn when_run_update_invalid_status(world: &mut TaskulusWorld) {
    run_cli(world, "tsk update tsk-aaa --status blocked");
}

#[when(expr = "I run \"tsk update tsk-test01 --status {word}\"")]
fn when_run_update_status_test01(world: &mut TaskulusWorld, status: String) {
    run_cli(world, &format!("tsk update tsk-test01 --status {status}"));
}

#[when("I run \"tsk update tsk-epic01 --status deferred\"")]
fn when_run_update_status_epic01(world: &mut TaskulusWorld) {
    run_cli(world, "tsk update tsk-epic01 --status deferred");
}

#[when("I run \"tsk update tsk-test01 --claim\"")]
fn when_run_update_claim_test01(world: &mut TaskulusWorld) {
    run_cli(world, "tsk update tsk-test01 --claim");
}

#[when("I run \"tsk update tsk-missing --title \\\"New Title\\\"\"")]
fn when_run_update_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk update tsk-missing --title \"New Title\"");
}

#[when("I run \"tsk update tsk-aaa --title \\\"New Title\\\"\"")]
fn when_run_update_title_only(world: &mut TaskulusWorld) {
    run_cli(world, "tsk update tsk-aaa --title \"New Title\"");
}

#[then("issue \"tsk-aaa\" should have title \"New Title\"")]
fn then_issue_has_title(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "tsk-aaa");
    assert_eq!(issue.title, "New Title");
}

#[then("issue \"tsk-aaa\" should have description \"Updated description\"")]
fn then_issue_has_description(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "tsk-aaa");
    assert_eq!(issue.description, "Updated description");
}

#[then("issue \"tsk-aaa\" should have an updated_at timestamp")]
fn then_issue_has_updated_at(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "tsk-aaa");
    assert!(issue.updated_at.timestamp() > 0);
}
