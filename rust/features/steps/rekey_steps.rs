use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then};
use serde_json::{json, Value};

use kanbus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::KanbusWorld;
use crate::step_definitions::issue_creation_steps::given_kanbus_project;

fn project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("working directory");
    load_project_directory(cwd).expect("project dir")
}

fn issue_path(world: &KanbusWorld, issue_id: &str) -> PathBuf {
    project_dir(world)
        .join("issues")
        .join(format!("{issue_id}.json"))
}

fn read_issue(world: &KanbusWorld, issue_id: &str) -> Value {
    let contents = fs::read_to_string(issue_path(world, issue_id)).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn write_issue(world: &KanbusWorld, issue_id: &str, issue: &Value) {
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path(world, issue_id), contents).expect("write issue");
}

fn project_key(world: &KanbusWorld) -> String {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let contents = fs::read_to_string(cwd.join(".kanbus.yml")).expect("read config");
    let config: serde_yaml::Value = serde_yaml::from_str(&contents).expect("parse config");
    config["project_key"].as_str().unwrap_or("").to_string()
}

fn git(world: &KanbusWorld, args: &[&str]) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let output = Command::new("git")
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("run git");
    assert!(
        output.status.success(),
        "git {:?} failed: {}",
        args,
        String::from_utf8_lossy(&output.stderr)
    );
}

#[given(expr = "a Kanbus project with key {string}")]
fn given_project_with_key(world: &mut KanbusWorld, key: String) {
    given_kanbus_project(world);
    let cwd = world.working_directory.as_ref().expect("working directory");
    let config_path = cwd.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut config: serde_yaml::Value = serde_yaml::from_str(&contents).expect("parse config");
    config["project_key"] = serde_yaml::Value::String(key);
    fs::write(
        config_path,
        serde_yaml::to_string(&config).expect("serialize config"),
    )
    .expect("write config");
}

#[given("the project is committed to git")]
fn given_project_committed(world: &mut KanbusWorld) {
    git(world, &["add", "-A"]);
    git(
        world,
        &[
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-q",
            "-m",
            "test setup",
        ],
    );
}

#[given("the project directory has uncommitted changes")]
fn given_uncommitted_changes(world: &mut KanbusWorld) {
    fs::write(project_dir(world).join("test-change.txt"), "uncommitted").expect("write test file");
}

#[given(expr = "issue {string} is blocked by {string}")]
fn given_issue_blocked(world: &mut KanbusWorld, issue_id: String, blocker: String) {
    let mut issue = read_issue(world, &issue_id);
    issue["dependencies"] = json!([{ "target": blocker, "type": "blocked-by" }]);
    write_issue(world, &issue_id, &issue);
}

#[given(expr = "issue {string} has a comment {string}")]
fn given_issue_has_comment(world: &mut KanbusWorld, issue_id: String, text: String) {
    let mut issue = read_issue(world, &issue_id);
    issue["comments"] = json!([{
        "id": "comment-1",
        "author": "test",
        "text": text,
        "created_at": "2026-02-11T00:00:00Z",
    }]);
    write_issue(world, &issue_id, &issue);
}

#[then(expr = "issue {string} should be blocked by {string}")]
fn then_issue_blocked(world: &mut KanbusWorld, issue_id: String, blocker: String) {
    let issue = read_issue(world, &issue_id);
    let found = issue["dependencies"].as_array().is_some_and(|deps| {
        deps.iter()
            .any(|dep| dep["target"] == blocker.as_str() && dep["type"] == "blocked-by")
    });
    assert!(found, "{issue_id} is not blocked by {blocker}: {issue}");
}

#[then(expr = "issue {string} should have description {string}")]
fn then_issue_has_description(world: &mut KanbusWorld, issue_id: String, description: String) {
    let issue = read_issue(world, &issue_id);
    assert_eq!(issue["description"].as_str().unwrap_or(""), description);
}

#[then(expr = "issue {string} should have a comment {string}")]
fn then_issue_has_comment(world: &mut KanbusWorld, issue_id: String, text: String) {
    let issue = read_issue(world, &issue_id);
    let found = issue["comments"].as_array().is_some_and(|comments| {
        comments
            .iter()
            .any(|comment| comment["text"].as_str() == Some(text.as_str()))
    });
    assert!(found, "{issue_id} has no comment {text:?}: {issue}");
}

#[then(expr = ".kanbus.yml should have project_key {string}")]
fn then_project_key_is(world: &mut KanbusWorld, key: String) {
    assert_eq!(project_key(world), key);
}

#[given(expr = ".kanbus.yml ends with the comment {string}")]
fn given_config_comment(world: &mut KanbusWorld, comment: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let config_path = cwd.join(".kanbus.yml");
    let mut contents = fs::read_to_string(&config_path).expect("read config");
    if !contents.ends_with('\n') {
        contents.push('\n');
    }
    contents.push_str(&comment);
    contents.push('\n');
    fs::write(config_path, contents).expect("write config");
}

#[then(expr = ".kanbus.yml should contain {string}")]
fn then_config_contains(world: &mut KanbusWorld, text: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let contents = fs::read_to_string(cwd.join(".kanbus.yml")).expect("read config");
    assert!(
        contents.contains(&text),
        "{text:?} not in .kanbus.yml:\n{contents}"
    );
}
