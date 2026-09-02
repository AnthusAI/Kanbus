use std::fs;
use std::path::PathBuf;

use chrono::{DateTime, TimeZone, Utc};
use cucumber::{given, then};

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn local_project_dir(world: &KanbusWorld) -> PathBuf {
    let project_dir = load_project_dir(world);
    let local_dir = project_dir
        .parent()
        .expect("project parent")
        .join("project-local");
    fs::create_dir_all(local_dir.join("issues")).expect("create local issues");
    local_dir
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn read_issue_file(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
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
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

fn parse_timestamp(timestamp: &str) -> DateTime<Utc> {
    DateTime::parse_from_rfc3339(&timestamp.replace('Z', "+00:00"))
        .expect("timestamp")
        .with_timezone(&Utc)
}

fn read_issue_from_any_location(world: &KanbusWorld, identifier: &str) -> IssueData {
    let project_dir = load_project_dir(world);
    let shared_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    if shared_path.exists() {
        return read_issue_file(&project_dir, identifier);
    }
    let local_dir = local_project_dir(world);
    read_issue_file(&local_dir, identifier)
}

#[given(expr = "an issue {string} exists with updated_at {string}")]
fn given_issue_exists_with_updated_at(
    world: &mut KanbusWorld,
    identifier: String,
    updated_at: String,
) {
    let project_dir = load_project_dir(world);
    let timestamp = parse_timestamp(&updated_at);
    let mut issue = build_issue(&identifier, "Title");
    issue.created_at = timestamp;
    issue.updated_at = timestamp;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "a local issue {string} exists with updated_at {string}")]
fn given_local_issue_exists_with_updated_at(
    world: &mut KanbusWorld,
    identifier: String,
    updated_at: String,
) {
    let local_dir = local_project_dir(world);
    let timestamp = parse_timestamp(&updated_at);
    let mut issue = build_issue(&identifier, "Local");
    issue.created_at = timestamp;
    issue.updated_at = timestamp;
    write_issue_file(&local_dir, &issue);
}

#[given(expr = "issue {string} has updated_at {string}")]
fn given_issue_has_updated_at(world: &mut KanbusWorld, identifier: String, updated_at: String) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_file(&project_dir, &identifier);
    issue.updated_at = parse_timestamp(&updated_at);
    write_issue_file(&project_dir, &issue);
}

#[then(expr = "issue {string} updated_at should be after {string}")]
fn then_issue_updated_at_after(world: &mut KanbusWorld, identifier: String, updated_at: String) {
    let issue = read_issue_from_any_location(world, &identifier);
    let threshold = parse_timestamp(&updated_at);
    assert!(
        issue.updated_at > threshold,
        "expected updated_at after {updated_at}, got {}",
        issue
            .updated_at
            .to_rfc3339_opts(chrono::SecondsFormat::Millis, true)
    );
}
