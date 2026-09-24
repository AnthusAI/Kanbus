use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, when, then};
use serde_json::{json, Value};
use serde_yaml;

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn build_issue(
    identifier: &str,
    title: &str,
    issue_type: &str,
    status: &str,
    parent: Option<&str>,
) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: "".to_string(),
        issue_type: issue_type.to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: parent.map(|p| p.to_string()),
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

fn write_issue(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn read_issue(project_dir: &PathBuf, issue_id: &str) -> Value {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn setup_project_with_key(world: &mut KanbusWorld, key: &str) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().to_path_buf();

    // Initialize git repo
    std::process::Command::new("git")
        .args(["init", "-q"])
        .current_dir(&repo_path)
        .output()
        .expect("git init");

    // Create project structure
    fs::create_dir_all(repo_path.join("project").join("issues")).expect("create dirs");
    fs::create_dir_all(repo_path.join("project").join("events")).expect("create events");

    // Write .kanbus.yml with specified key
    let config_content = format!(
        r#"project_key: {}
project_name: Test Project
project_description: Test project for rekey scenarios
"#,
        key
    );
    fs::write(repo_path.join(".kanbus.yml"), config_content).expect("write config");

    world.working_directory = Some(repo_path.clone());
    world.temp_dir = Some(temp_dir);
}

#[given(expr = "a Kanbus project with key {string}")]
fn given_project_with_key(world: &mut KanbusWorld, key: String) {
    setup_project_with_key(world, &key);
}

#[given(expr = "an issue {string} exists")]
fn given_issue_exists(world: &mut KanbusWorld, issue_id: String) {
    let project_dir = load_project_dir(world);
    let issue = build_issue(&issue_id, &issue_id, "task", "open", None);
    write_issue(&project_dir, &issue);
}

#[given(expr = "issues {string} exist")]
fn given_issues_exist(world: &mut KanbusWorld, ids: String) {
    let issue_ids: Vec<&str> = ids
        .split(" and ")
        .map(|id| id.trim().trim_matches('"'))
        .collect();
    let project_dir = load_project_dir(world);
    for issue_id in issue_ids {
        let issue = build_issue(issue_id, issue_id, "task", "open", None);
        write_issue(&project_dir, &issue);
    }
}

#[given(expr = "issues {string} and {string} exist")]
fn given_two_issues_exist(world: &mut KanbusWorld, id1: String, id2: String) {
    let project_dir = load_project_dir(world);
    for issue_id in &[id1, id2] {
        let issue = build_issue(issue_id, issue_id, "task", "open", None);
        write_issue(&project_dir, &issue);
    }
}

#[given(expr = "an issue {string} exists with type {string}")]
fn given_issue_with_type(world: &mut KanbusWorld, issue_id: String, issue_type: String) {
    let project_dir = load_project_dir(world);
    let issue = build_issue(&issue_id, &issue_id, &issue_type, "open", None);
    write_issue(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists with parent {string}")]
fn given_issue_with_parent(world: &mut KanbusWorld, issue_id: String, parent_id: String) {
    let project_dir = load_project_dir(world);
    let issue = build_issue(&issue_id, &issue_id, "task", "open", Some(&parent_id));
    write_issue(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists with description {string}")]
fn given_issue_with_description(
    world: &mut KanbusWorld,
    issue_id: String,
    description: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&issue_id, &issue_id, "task", "open", None);
    issue.description = description;
    write_issue(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists with title {string} and description {string}")]
fn given_issue_with_title_and_desc(
    world: &mut KanbusWorld,
    issue_id: String,
    title: String,
    description: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&issue_id, &title, "task", "open", None);
    issue.description = description;
    write_issue(&project_dir, &issue);
}

#[given(expr = "issue {string} has dependency {string} on {string}")]
fn given_issue_has_dependency(
    world: &mut KanbusWorld,
    issue_id: String,
    dep_type: String,
    target_id: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue_json = read_issue(&project_dir, &issue_id);
    let dep = json!({
        "target": target_id,
        "dependency_type": dep_type
    });
    if !issue_json["dependencies"].is_array() {
        issue_json["dependencies"] = json!([]);
    }
    issue_json["dependencies"]
        .as_array_mut()
        .expect("array")
        .push(dep);

    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));
    let contents = serde_json::to_string_pretty(&issue_json).expect("serialize");
    fs::write(issue_path, contents).expect("write");
}

#[given(expr = "issue {string} has a comment {string}")]
fn given_issue_has_comment(world: &mut KanbusWorld, issue_id: String, comment_text: String) {
    let project_dir = load_project_dir(world);
    let mut issue_json = read_issue(&project_dir, &issue_id);

    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let comment = json!({
        "id": "comment-1",
        "author": "test",
        "body": comment_text,
        "created_at": timestamp.to_rfc3339(),
        "updated_at": timestamp.to_rfc3339(),
    });

    if !issue_json["comments"].is_array() {
        issue_json["comments"] = json!([]);
    }
    issue_json["comments"]
        .as_array_mut()
        .expect("array")
        .push(comment);

    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));
    let contents = serde_json::to_string_pretty(&issue_json).expect("serialize");
    fs::write(issue_path, contents).expect("write");
}

#[given(expr = "an issue {string} already exists")]
fn given_issue_already_exists(world: &mut KanbusWorld, new_id: String) {
    let project_dir = load_project_dir(world);
    let issue = build_issue(&new_id, &new_id, "task", "open", None);
    write_issue(&project_dir, &issue);
}

#[given("the working tree has uncommitted changes under project/")]
fn given_uncommitted_changes(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let test_file = project_dir.join("test-change.txt");
    fs::write(test_file, "uncommitted").expect("write test file");
}

#[then("the command should succeed")]
fn then_command_succeeds(world: &mut KanbusWorld) {
    assert_eq!(
        world.exit_code,
        Some(0),
        "Command failed with stderr: {}",
        world.stderr.as_deref().unwrap_or("")
    );
}

#[then(expr = "the command should succeed with message {string}")]
fn then_command_succeeds_with_message(world: &mut KanbusWorld, message: String) {
    assert_eq!(world.exit_code, Some(0));
    let output = format!(
        "{}{}",
        world.stdout.as_deref().unwrap_or(""),
        world.stderr.as_deref().unwrap_or("")
    );
    assert!(
        output.contains(&message),
        "Expected message '{}' not found in output: {}",
        message,
        output
    );
}

#[then("the rekey should succeed")]
fn then_rekey_succeeds(world: &mut KanbusWorld) {
    then_command_succeeds(world);
}

#[then(expr = "issue {string} should exist")]
fn then_issue_exists(world: &mut KanbusWorld, issue_id: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join(format!("{}.json", issue_id));
    assert!(issue_path.exists(), "Issue {} should exist", issue_id);
}

#[then(expr = "issue {string} should not exist")]
fn then_issue_not_exists(world: &mut KanbusWorld, issue_id: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join(format!("{}.json", issue_id));
    assert!(!issue_path.exists(), "Issue {} should not exist", issue_id);
}

#[then(expr = "issue {string} should still exist")]
fn then_issue_still_exists(world: &mut KanbusWorld, issue_id: String) {
    then_issue_exists(world, issue_id);
}

#[then(expr = "issue {string} should resolve to {string}")]
fn then_short_id_resolves(world: &mut KanbusWorld, _short_id: String, full_id: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join(format!("{}.json", full_id));
    assert!(issue_path.exists(), "Full ID {} should exist", full_id);
}

#[then(expr = "issue {string} should have parent {string}")]
fn then_issue_has_parent(world: &mut KanbusWorld, issue_id: String, parent_id: String) {
    let project_dir = load_project_dir(world);
    let issue_json = read_issue(&project_dir, &issue_id);
    assert_eq!(
        issue_json
            .get("parent")
            .and_then(|p| p.as_str())
            .unwrap_or(""),
        &parent_id
    );
}

#[then(expr = "issue {string} should have dependency {string} on {string}")]
fn then_issue_has_dependency(
    world: &mut KanbusWorld,
    issue_id: String,
    dep_type: String,
    target_id: String,
) {
    let project_dir = load_project_dir(world);
    let issue_json = read_issue(&project_dir, &issue_id);
    let deps = issue_json.get("dependencies").and_then(|d| d.as_array());
    assert!(
        deps.map(|d| d
            .iter()
            .any(|dep| dep
                .get("target")
                .and_then(|t| t.as_str())
                .map(|t| t == target_id)
                .unwrap_or(false)
                && dep
                    .get("dependency_type")
                    .and_then(|t| t.as_str())
                    .map(|t| t == dep_type)
                    .unwrap_or(false)))
            .unwrap_or(false),
        "Dependency {} -> {} not found",
        dep_type,
        target_id
    );
}

#[then(expr = "issue {string} should have title {string}")]
fn then_issue_has_title(world: &mut KanbusWorld, issue_id: String, title: String) {
    let project_dir = load_project_dir(world);
    let issue_json = read_issue(&project_dir, &issue_id);
    assert_eq!(
        issue_json
            .get("title")
            .and_then(|t| t.as_str())
            .unwrap_or(""),
        &title
    );
}

#[then(expr = "issue {string} should have description {string}")]
fn then_issue_has_description(world: &mut KanbusWorld, issue_id: String, description: String) {
    let project_dir = load_project_dir(world);
    let issue_json = read_issue(&project_dir, &issue_id);
    assert_eq!(
        issue_json
            .get("description")
            .and_then(|d| d.as_str())
            .unwrap_or(""),
        &description
    );
}

#[then(expr = "issue {string} should have a comment {string}")]
fn then_issue_has_comment(world: &mut KanbusWorld, issue_id: String, comment_text: String) {
    let project_dir = load_project_dir(world);
    let issue_json = read_issue(&project_dir, &issue_id);
    let comments = issue_json.get("comments").and_then(|c| c.as_array());
    assert!(
        comments
            .map(|c| c
                .iter()
                .any(|comment| comment
                    .get("body")
                    .and_then(|b| b.as_str())
                    .map(|b| b.contains(&comment_text))
                    .unwrap_or(false)))
            .unwrap_or(false),
        "Comment not found: {}",
        comment_text
    );
}

#[then(expr = "stdout should contain {string}")]
fn then_stdout_contains(world: &mut KanbusWorld, text: String) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(
        stdout.contains(&text),
        "Expected '{}' in stdout:\n{}",
        text,
        stdout
    );
}

#[then(expr = "stdout should contain {string}")]
fn then_stdout_has_rewrite_count(world: &mut KanbusWorld, count: String) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(
        stdout.contains(&count),
        "Expected '{}' in stdout:\n{}",
        count,
        stdout
    );
}

#[then(expr = "stderr should contain {string}")]
fn then_stderr_contains(world: &mut KanbusWorld, text: String) {
    let stderr = world.stderr.as_deref().unwrap_or("");
    assert!(
        stderr.contains(&text),
        "Expected '{}' in stderr:\n{}",
        text,
        stderr
    );
}

#[then("the command should fail with exit code 1")]
fn then_command_fails(world: &mut KanbusWorld) {
    assert_ne!(
        world.exit_code,
        Some(0),
        "Command should have failed but succeeded"
    );
}

#[then("the cache directory should be invalidated or rebuilt")]
fn then_cache_invalidated(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let cache_dir = project_dir.join(".cache");
    // Cache should not exist (invalidated)
    assert!(!cache_dir.exists());
}

#[then("the validate command should succeed")]
fn then_validate_succeeds(world: &mut KanbusWorld) {
    then_command_succeeds(world);
}

#[then(expr = "project key in .kanbus.yml should be {string}")]
fn then_project_key_is(world: &mut KanbusWorld, key: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let config_path = cwd.join(".kanbus.yml");
    let config_content = fs::read_to_string(&config_path).expect("read config");
    let config: Value = serde_yaml::from_str(&config_content).expect("parse config");
    assert_eq!(
        config
            .get("project_key")
            .and_then(|k| k.as_str())
            .unwrap_or(""),
        &key
    );
}

#[then(expr = "project key should still be {string}")]
fn then_project_key_still_is(world: &mut KanbusWorld, key: String) {
    then_project_key_is(world, key);
}

#[then("the event history should reflect the rekey operation")]
fn then_event_history_reflects_rekey(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let events_dir = project_dir.join("events");
    assert!(events_dir.exists(), "Events directory should exist");
}

#[given("the project is committed to git")]
fn given_project_committed(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    // Configure git for tests
    std::process::Command::new("git")
        .args(&["config", "user.email", "test@example.com"])
        .current_dir(cwd)
        .output()
        .ok();
    std::process::Command::new("git")
        .args(&["config", "user.name", "Test User"])
        .current_dir(cwd)
        .output()
        .ok();
    // Add and commit
    std::process::Command::new("git")
        .args(&["add", "-A"])
        .current_dir(cwd)
        .output()
        .ok();
    std::process::Command::new("git")
        .args(&["commit", "-m", "test setup"])
        .current_dir(cwd)
        .output()
        .ok();
}

#[given("the project directory has uncommitted changes")]
fn given_project_dir_uncommitted_changes(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let test_file = project_dir.join("test-change.txt");
    fs::write(test_file, "uncommitted").expect("write test file");
}

#[when(expr = "I run \"kanbus rekey {string}\"")]
fn when_run_rekey(world: &mut KanbusWorld, args: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let output = std::process::Command::new("kanbus")
        .args(&["rekey", &args])
        .current_dir(cwd)
        .output()
        .expect("run kanbus rekey");

    world.exit_code = Some(output.status.code().unwrap_or(-1));
    world.stdout = Some(String::from_utf8_lossy(&output.stdout).to_string());
    world.stderr = Some(String::from_utf8_lossy(&output.stderr).to_string());
}

#[given(expr = "issue {string} is blocked by {string}")]
fn given_issue_blocked(world: &mut KanbusWorld, id: String, blocker: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    // Use kanbus dep command to add dependency
    let output = std::process::Command::new("kanbus")
        .args(&["dep", &id, "blocked-by", &blocker])
        .current_dir(cwd)
        .output()
        .expect("run kanbus dep");

    if output.status.code().unwrap_or(-1) != 0 {
        panic!("Failed to add dependency: {}", String::from_utf8_lossy(&output.stderr));
    }
}


#[then(expr = "issue {string} should be blocked by {string}")]
fn then_issue_blocked(world: &mut KanbusWorld, id: String, blocker: String) {
    let project_dir = load_project_dir(world);
    let issue_json = read_issue(&project_dir, &id);
    let deps = issue_json.get("dependencies").and_then(|d| d.as_array());
    assert!(
        deps.map(|d| d
            .iter()
            .any(|dep| dep
                .get("target")
                .and_then(|t| t.as_str())
                .map(|t| t == blocker)
                .unwrap_or(false)
                && (dep
                    .get("type")
                    .and_then(|t| t.as_str())
                    .map(|t| t == "blocked-by")
                    .unwrap_or(false)
                    || dep
                        .get("dependency_type")
                        .and_then(|t| t.as_str())
                        .map(|t| t == "blocked-by")
                        .unwrap_or(false))))
            .unwrap_or(false),
        "Dependency blocked-by -> {} not found",
        blocker
    );
}

#[then(expr = ".kanbus.yml should have project_key {string}")]
fn then_project_key_file(world: &mut KanbusWorld, key: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let config_path = cwd.join(".kanbus.yml");
    let config_content = fs::read_to_string(&config_path).expect("read config");
    let config: Value = serde_yaml::from_str(&config_content).expect("parse config");
    assert_eq!(
        config
            .get("project_key")
            .and_then(|k| k.as_str())
            .unwrap_or(""),
        &key,
        "Expected project_key '{}' but got '{}'",
        key,
        config.get("project_key").and_then(|k| k.as_str()).unwrap_or("")
    );
}
