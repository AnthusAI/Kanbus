use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then};
use serde_json::Value;

use kanbus::beads_write::set_test_beads_slug_sequence;
use kanbus::config::default_project_configuration;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn fixture_beads_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("specs")
        .join("fixtures")
        .join("beads_repo")
        .join(".beads")
}

fn copy_dir(source: &std::path::Path, destination: &std::path::Path) {
    fs::create_dir_all(destination).expect("create beads dir");
    for entry in fs::read_dir(source).expect("read beads dir") {
        let entry = entry.expect("beads dir entry");
        let path = entry.path();
        let dest = destination.join(entry.file_name());
        if path.is_dir() {
            copy_dir(&path, &dest);
        } else {
            fs::copy(&path, &dest).expect("copy beads file");
        }
    }
}

#[given("a Kanbus project with beads compatibility enabled")]
fn given_project_with_beads_compatibility(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let target_beads = repo_path.join(".beads");
    fs::create_dir_all(&target_beads).expect("beads dir");
    copy_dir(&fixture_beads_dir(), &target_beads);
    let mut configuration = default_project_configuration();
    configuration.beads_compatibility = true;
    let project_dir = repo_path.join(&configuration.project_directory);
    let issues_dir = project_dir.join("issues");
    fs::create_dir_all(&issues_dir).expect("create issues dir");
    let contents = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(repo_path.join(".kanbus.yml"), contents).expect("write config");

    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a project directory exists")]
fn given_project_directory_exists(world: &mut KanbusWorld) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = root.join("project");
    fs::create_dir_all(project_dir.join("issues")).expect("create issues dir");
    fs::create_dir_all(project_dir.join("events")).expect("create events dir");
}

#[then(expr = "beads issues.jsonl should contain {string}")]
fn then_beads_jsonl_contains(world: &mut KanbusWorld, identifier: String) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let path = root.join(".beads").join("issues.jsonl");
    let contents = std::fs::read_to_string(path).expect("read issues.jsonl");
    assert!(contents.contains(&identifier));
}

#[then(expr = "beads issues.jsonl should include assignee {string}")]
fn then_beads_jsonl_includes_assignee(world: &mut KanbusWorld, assignee: String) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let path = root.join(".beads").join("issues.jsonl");
    let contents = fs::read_to_string(path).expect("read issues.jsonl");
    let mut found = false;
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: Value = serde_json::from_str(line).expect("parse record");
        if record.get("assignee").and_then(|value| value.as_str()) == Some(assignee.as_str()) {
            found = true;
            break;
        }
    }
    assert!(found);
}

#[then(expr = "beads issues.jsonl should include description {string}")]
fn then_beads_jsonl_includes_description(world: &mut KanbusWorld, description: String) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let path = root.join(".beads").join("issues.jsonl");
    let contents = fs::read_to_string(path).expect("read issues.jsonl");
    let mut found = false;
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: Value = serde_json::from_str(line).expect("parse record");
        if record.get("description").and_then(|value| value.as_str()) == Some(description.as_str())
        {
            found = true;
            break;
        }
    }
    assert!(found);
}

#[then(expr = "beads issues.jsonl should include status {string} for {string}")]
fn then_beads_jsonl_includes_status_for(
    world: &mut KanbusWorld,
    status: String,
    identifier: String,
) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let path = root.join(".beads").join("issues.jsonl");
    let contents = fs::read_to_string(path).expect("read issues.jsonl");
    let mut found = false;
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: Value = serde_json::from_str(line).expect("parse record");
        if record.get("id").and_then(|value| value.as_str()) == Some(identifier.as_str()) {
            let value = record.get("status").and_then(|value| value.as_str());
            assert_eq!(value, Some(status.as_str()));
            found = true;
            break;
        }
    }
    assert!(found);
}

#[then(expr = "beads issues.jsonl should not contain {string}")]
fn then_beads_jsonl_not_contains(world: &mut KanbusWorld, identifier: String) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let path = root.join(".beads").join("issues.jsonl");
    let contents = fs::read_to_string(path).expect("read issues.jsonl");
    let needle = format!("\"id\":\"{identifier}\"");
    assert!(
        !contents.contains(&needle),
        "issue id unexpectedly present in beads issues.jsonl"
    );
}

#[then(expr = "stdout should list issue {string}")]
fn then_stdout_lists_issue(world: &mut KanbusWorld, identifier: String) {
    use kanbus::ids::format_issue_key;
    let stdout = world.stdout.as_ref().expect("stdout");
    // Format the identifier for beads mode (strips project key)
    let formatted = format_issue_key(&identifier, true);
    // Check for identifier as a word boundary to avoid matching within issue type or title
    // Look for patterns like: "identifier " or " | identifier | " (porcelain)
    let patterns = vec![
        format!("{} ", identifier),
        format!(" {} ", identifier),
        format!(" | {} | ", identifier),
        format!("{} ", formatted),
        format!(" {} ", formatted),
        format!(" | {} | ", formatted),
    ];
    let found = patterns.iter().any(|pattern| stdout.contains(pattern));
    assert!(
        found,
        "Issue {} (or formatted {}) not found in stdout as identifier",
        identifier, formatted
    );
}

#[then(expr = "stdout should not list issue {string}")]
fn then_stdout_not_lists_issue(world: &mut KanbusWorld, identifier: String) {
    use kanbus::ids::format_issue_key;
    let stdout = world.stdout.as_ref().expect("stdout");
    // Format the identifier for beads mode (strips project key)
    let formatted = format_issue_key(&identifier, true);
    // Check for identifier as a word boundary
    let patterns = vec![
        format!("{} ", identifier),
        format!(" {} ", identifier),
        format!(" | {} | ", identifier),
        format!("{} ", formatted),
        format!(" {} ", formatted),
        format!(" | {} | ", formatted),
    ];
    let found = patterns.iter().any(|pattern| stdout.contains(pattern));
    assert!(
        !found,
        "Issue {} (or formatted {}) unexpectedly found in stdout",
        identifier, formatted
    );
}

#[given(expr = "the beads slug generator always returns {string}")]
fn given_beads_slug_generator_returns(_world: &mut KanbusWorld, slug: String) {
    set_test_beads_slug_sequence(Some(vec![slug; 11]));
}

#[given(expr = "a beads issue with id {string} exists")]
fn given_beads_issue_exists(world: &mut KanbusWorld, identifier: String) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let path = root.join(".beads").join("issues.jsonl");
    let record = serde_json::json!({
        "id": identifier,
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    });
    let mut contents = fs::read_to_string(&path).expect("read issues.jsonl");
    if !contents.ends_with('\n') && !contents.is_empty() {
        contents.push('\n');
    }
    contents.push_str(&format!("{}\n", record.to_string()));
    fs::write(&path, contents).expect("write issues.jsonl");
}
