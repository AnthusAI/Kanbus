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

fn load_issue(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given("an issue \"tsk-aaa\" exists")]
fn given_issue_exists(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier: "tsk-aaa".to_string(),
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

#[when("I run \"tsk close tsk-aaa\"")]
fn when_run_close(world: &mut TaskulusWorld) {
    run_cli(world, "tsk close tsk-aaa");
}

#[when("I run \"tsk close tsk-missing\"")]
fn when_run_close_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk close tsk-missing");
}

#[when("I run \"tsk delete tsk-aaa\"")]
fn when_run_delete(world: &mut TaskulusWorld) {
    run_cli(world, "tsk delete tsk-aaa");
}

#[when("I run \"tsk delete tsk-missing\"")]
fn when_run_delete_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk delete tsk-missing");
}

#[then("issue \"tsk-aaa\" should have status \"closed\"")]
fn then_issue_status_closed(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "tsk-aaa");
    assert_eq!(issue.status, "closed");
}

#[then("issue \"tsk-aaa\" should have a closed_at timestamp")]
fn then_issue_closed_at(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "tsk-aaa");
    assert!(issue.closed_at.is_some());
}

#[then("issue \"tsk-aaa\" should not exist")]
fn then_issue_not_exists(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("tsk-aaa.json");
    assert!(!issue_path.exists());
}
