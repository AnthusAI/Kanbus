use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::file_io::load_project_directory;
use taskulus::issue_display::format_issue_for_display;
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

fn build_issue(identifier: &str, title: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
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
    }
}

#[given("an issue \"tsk-aaa\" exists with title \"Implement OAuth2 flow\"")]
fn given_issue_exists(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = build_issue("tsk-aaa", "Implement OAuth2 flow");
    write_issue_file(&project_dir, &issue);
}

#[given("an issue \"tsk-desc\" exists with title \"Describe me\"")]
fn given_issue_desc_exists(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue = build_issue("tsk-desc", "Describe me");
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

#[when("I run \"tsk show tsk-desc\"")]
fn when_run_show_desc(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-desc");
}

#[when("I run \"tsk show tsk-aaa --json\"")]
fn when_run_show_json(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-aaa --json");
}

#[when("I run \"tsk show tsk-labels\"")]
fn when_run_show_labels(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-labels");
}

#[when("I run \"tsk show tsk-missing\"")]
fn when_run_show_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk show tsk-missing");
}

#[when("I format issue \"tsk-labels\" for display")]
fn when_format_issue_display(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("tsk-labels.json");
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    world.formatted_output = Some(format_issue_for_display(&issue));
}

#[then("the formatted output should contain \"Labels: auth, urgent\"")]
fn then_formatted_output_contains_labels(world: &mut TaskulusWorld) {
    let output = world.formatted_output.as_deref().unwrap_or("");
    assert!(output.contains("Labels: auth, urgent"));
}
