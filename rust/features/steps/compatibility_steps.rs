use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when};
use serde_json::Value;

use kanbus::beads_write::set_test_beads_slug_sequence;
use kanbus::cli::run_from_args_with_output;
use kanbus::config::default_project_configuration;

use crate::step_definitions::initialization_steps::KanbusWorld;
use regex::Regex;

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

fn run_cli(world: &mut KanbusWorld, command: &str) {
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

fn capture_last_issue_id(world: &KanbusWorld) -> Option<String> {
    let stdout = world.stdout.as_ref()?;
    let regex = Regex::new(r"([A-Za-z]+-[A-Za-z0-9.]+)").expect("compile regex");
    regex
        .captures(stdout)
        .and_then(|caps| caps.get(1).map(|m| m.as_str().to_lowercase()))
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

#[when("I run \"kanbus --beads list\"")]
fn when_run_list_beads(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads list");
}

#[when("I run \"kanbus --beads list --no-local\"")]
fn when_run_list_beads_no_local(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads list --no-local");
}

#[when("I run \"kanbus --beads ready\"")]
fn when_run_ready_beads(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads ready");
}

#[when("I run \"kanbus --beads ready --no-local\"")]
fn when_run_ready_beads_no_local(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads ready --no-local");
}

#[when(expr = "I run \"kanbus --beads show {word}\"")]
fn when_run_show_beads(world: &mut KanbusWorld, identifier: String) {
    run_cli(world, &format!("kanbus --beads show {}", identifier));
}

#[when("I run \"kanbus --beads create New beads child --parent bdx-epic\"")]
fn when_run_create_beads_child(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create New beads child --parent bdx-epic",
    );
    world.last_beads_issue_id = capture_last_issue_id(world);
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

#[when("I run \"kanbus --beads create Local beads issue --local\"")]
fn when_run_create_beads_local(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Local beads issue --local");
}

#[when("I run \"kanbus --beads create Missing beads issue\"")]
fn when_run_create_beads_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Missing beads issue");
}

#[when("I run \"kanbus --beads create Missing issues file\"")]
fn when_run_create_beads_missing_issues(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Missing issues file");
}

#[when("I run \"kanbus --beads create Empty beads file\"")]
fn when_run_create_beads_empty(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Empty beads file");
}

#[when("I run \"kanbus --beads create Orphan beads issue --parent bdx-missing\"")]
fn when_run_create_beads_orphan(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Orphan beads issue --parent bdx-missing",
    );
}

#[when("I run \"kanbus --beads create Assigned beads issue --assignee dev@example.com\"")]
fn when_run_create_beads_assigned(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Assigned beads issue --assignee dev@example.com",
    );
}

#[when("I run \"kanbus --beads create Described beads issue --description Details\"")]
fn when_run_create_beads_description(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Described beads issue --description Details",
    );
}

#[when("I run \"kanbus --beads create Beads with blanks\"")]
fn when_run_create_beads_with_blanks(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Beads with blanks");
}

#[when("I run \"kanbus --beads create Invalid prefix\"")]
fn when_run_create_beads_invalid_prefix(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Invalid prefix");
}

#[when("I run \"kanbus --beads create Colliding beads issue\"")]
fn when_run_create_beads_collision(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Colliding beads issue");
}

#[when("I run \"kanbus --beads create Next child --parent bdx-epic\"")]
fn when_run_create_beads_next_child(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Next child --parent bdx-epic");
}

#[when("I run \"kanbus --beads update bdx-missing --status closed\"")]
fn when_run_update_beads_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads update bdx-missing --status closed");
}

#[when("I run \"kanbus --beads update bdx-epic --status closed\"")]
fn when_run_update_beads_success(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads update bdx-epic --status closed");
}

#[when("I run \"kanbus --beads delete bdx-missing\"")]
fn when_run_delete_beads_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads delete bdx-missing");
}

#[when("I run \"kanbus --beads delete bdx-task\"")]
fn when_run_delete_beads_success(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads delete bdx-task");
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
    assert!(!contents.contains(&identifier));
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

#[when("I run \"kanbus --beads create Interop deletable --parent bdx-epic\"")]
fn when_run_create_beads_deletable(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Interop deletable --parent bdx-epic",
    );
    world.last_beads_issue_id = capture_last_issue_id(world);
}

#[when("I run \"kanbus --beads create Interop child via Kanbus --parent bdx-epic\"")]
fn when_run_create_beads_child_via_kanbus(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Interop child via Kanbus --parent bdx-epic",
    );
    world.last_beads_issue_id = capture_last_issue_id(world);
}

#[when("I run \"kanbus --beads create Interop updatable --parent bdx-epic\"")]
fn when_run_create_beads_updatable(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Interop updatable --parent bdx-epic",
    );
    world.last_beads_issue_id = capture_last_issue_id(world);
}
