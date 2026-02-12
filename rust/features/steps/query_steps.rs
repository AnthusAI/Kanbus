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

fn build_issue(identifier: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
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
    }
}

#[given(expr = "issues {string} and {string} exist")]
fn given_issues_exist(world: &mut TaskulusWorld, first: String, second: String) {
    let project_dir = load_project_dir(world);
    let issue_first = build_issue(&first);
    let issue_second = build_issue(&second);
    write_issue_file(&project_dir, &issue_first);
    write_issue_file(&project_dir, &issue_second);
}

#[given(expr = "issues {string} exist")]
fn given_single_issue_exists(world: &mut TaskulusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = build_issue(&identifier);
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has status {string}")]
fn given_issue_has_status(world: &mut TaskulusWorld, identifier: String, status: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.status = status;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has type {string}")]
fn given_issue_has_type(world: &mut TaskulusWorld, identifier: String, issue_type: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.issue_type = issue_type;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has assignee {string}")]
fn given_issue_has_assignee(world: &mut TaskulusWorld, identifier: String, assignee: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.assignee = Some(assignee);
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has labels {string}")]
fn given_issue_has_labels(world: &mut TaskulusWorld, identifier: String, label_text: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.labels = label_text
        .split(',')
        .map(|label| label.trim())
        .filter(|label| !label.is_empty())
        .map(str::to_string)
        .collect();
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has priority {int}")]
fn given_issue_has_priority(world: &mut TaskulusWorld, identifier: String, priority: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    let parsed = priority.parse::<i32>().expect("priority int");
    issue.priority = parsed;
    write_issue_file(&project_dir, &issue);
}

#[when("I run \"tsk --help\"")]
fn when_run_help(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --help");
}

#[when("I run \"tsk --unknown\"")]
fn when_run_unknown(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --unknown");
}

#[given(expr = "issue {string} has title {string}")]
fn given_issue_has_title(world: &mut TaskulusWorld, identifier: String, title: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.title = title;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has description {string}")]
fn given_issue_has_description(world: &mut TaskulusWorld, identifier: String, description: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.description = description;
    write_issue_file(&project_dir, &issue);
}

#[when("I run \"tsk list --status open\"")]
fn when_run_list_status(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --status open");
}

#[when("I run \"tsk list --type task\"")]
fn when_run_list_type(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --type task");
}

#[when("I run \"tsk list --assignee dev@example.com\"")]
fn when_run_list_assignee(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --assignee dev@example.com");
}

#[when("I run \"tsk list --label auth\"")]
fn when_run_list_label(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --label auth");
}

#[when("I run \"tsk list --sort priority\"")]
fn when_run_list_sort(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --sort priority");
}

#[when("I run \"tsk list --search login\"")]
fn when_run_list_search(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --search login");
}

#[when("I run \"tsk list --search Searchable\"")]
fn when_run_list_search_comment(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --search Searchable");
}

#[when("I run \"tsk list --search Dup\"")]
fn when_run_list_search_dup(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --search Dup");
}

#[when("I run \"tsk list --sort invalid\"")]
fn when_run_list_invalid_sort(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --sort invalid");
}

#[when("I run \"tsk list --no-local\"")]
fn when_run_list_no_local(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --no-local");
}

#[when("I run \"tsk list --local-only\"")]
fn when_run_list_local_only(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --local-only");
}

#[when("I run \"tsk list --local-only --no-local\"")]
fn when_run_list_local_conflict(world: &mut TaskulusWorld) {
    run_cli(world, "tsk list --local-only --no-local");
}

#[then("stdout should list \"tsk-high\" before \"tsk-low\"")]
fn then_stdout_lists_high_before_low(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let high_index = stdout.find("tsk-high").expect("find tsk-high");
    let low_index = stdout.find("tsk-low").expect("find tsk-low");
    assert!(high_index < low_index);
}

#[given("the daemon list request will fail")]
fn given_daemon_list_fails(world: &mut TaskulusWorld) {
    world.daemon_list_error = true;
}

#[given("local listing will fail")]
fn given_local_listing_fails(world: &mut TaskulusWorld) {
    world.local_listing_error = true;
}

#[when("shared issues are listed without local issues")]
fn when_shared_only_listed(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let mut identifiers = Vec::new();
    for entry in fs::read_dir(&issues_dir).expect("read issues") {
        let entry = entry.expect("entry");
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let contents = fs::read_to_string(&path).expect("read issue");
        let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
        identifiers.push(issue.identifier);
    }
    world.shared_only_results = Some(identifiers);
}

#[then(expr = "the shared-only list should contain {string}")]
fn then_shared_only_contains(world: &mut TaskulusWorld, identifier: String) {
    let list = world.shared_only_results.as_ref().expect("shared list");
    assert!(list.iter().any(|item| item == &identifier));
}

#[then(expr = "the shared-only list should not contain {string}")]
fn then_shared_only_not_contains(world: &mut TaskulusWorld, identifier: String) {
    let list = world.shared_only_results.as_ref().expect("shared list");
    assert!(!list.iter().any(|item| item == &identifier));
}
