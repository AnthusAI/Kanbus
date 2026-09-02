use std::fs;
use std::path::PathBuf;

use chrono::{DateTime, Utc};
use cucumber::{given, then, when};

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;
use kanbus::right_now::get_right_now_summary;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn read_issue_file(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given(expr = "issue {string} has right now summary {string}")]
fn given_issue_has_right_now_summary(world: &mut KanbusWorld, identifier: String, summary: String) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_file(&project_dir, &identifier);
    issue.right_now_summary = Some(summary);
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has right now updated at {string}")]
fn given_issue_has_right_now_updated_at(
    world: &mut KanbusWorld,
    identifier: String,
    timestamp: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_file(&project_dir, &identifier);
    let parsed: DateTime<Utc> = timestamp.parse().expect("parse timestamp");
    issue.right_now_updated_at = Some(parsed);
    write_issue_file(&project_dir, &issue);
}

#[when(expr = "issue {string} is saved and reloaded from disk")]
fn when_issue_saved_and_reloaded(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    write_issue_file(&project_dir, &issue);
    world.reloaded_issue = Some(read_issue_file(&project_dir, &identifier));
}

#[when(expr = "issue {string} is loaded from disk")]
fn when_issue_loaded_from_disk(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    world.reloaded_issue = Some(read_issue_file(&project_dir, &identifier));
}

#[when(expr = "I read the right now summary for issue {string}")]
fn when_read_right_now_summary(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    world.right_now_summary_result = Some(get_right_now_summary(&issue).map(str::to_string));
}

#[then(expr = "issue {string} should have right now summary {string}")]
fn then_issue_has_right_now_summary(world: &mut KanbusWorld, identifier: String, expected: String) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    assert_eq!(issue.right_now_summary.as_deref(), Some(expected.as_str()));
}

#[then(expr = "issue {string} should have right now updated at {string}")]
fn then_issue_has_right_now_updated_at(
    world: &mut KanbusWorld,
    identifier: String,
    expected: String,
) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    let expected_timestamp: DateTime<Utc> = expected.parse().expect("parse timestamp");
    assert_eq!(issue.right_now_updated_at, Some(expected_timestamp));
}

#[then(expr = "issue {string} should have no right now summary")]
fn then_issue_has_no_right_now_summary(world: &mut KanbusWorld, identifier: String) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    assert!(issue.right_now_summary.is_none());
}

#[then(expr = "issue {string} should have no right now updated at")]
fn then_issue_has_no_right_now_updated_at(world: &mut KanbusWorld, identifier: String) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    assert!(issue.right_now_updated_at.is_none());
}

#[then(expr = "the right now summary result should be {string}")]
fn then_right_now_summary_result(world: &mut KanbusWorld, expected: String) {
    let result = world
        .right_now_summary_result
        .as_ref()
        .expect("right now summary result not set");
    assert_eq!(result.as_deref(), Some(expected.as_str()));
}

#[then("the right now summary result should be unset")]
fn then_right_now_summary_result_unset(world: &mut KanbusWorld) {
    let result = world
        .right_now_summary_result
        .as_ref()
        .expect("right now summary result not set");
    assert!(result.is_none());
}
