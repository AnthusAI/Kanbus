use std::fs;
use std::path::{Path, PathBuf};

use cucumber::{given, then, when};
use serde_json::Value;
use tempfile::TempDir;

use kanbus::cli::run_from_args_with_output;
use kanbus::ids::format_issue_key;

use crate::step_definitions::initialization_steps::KanbusWorld;

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

fn fixture_beads_dir() -> PathBuf {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("repo root");
    root.join("specs")
        .join("fixtures")
        .join("beads_repo")
        .join(".beads")
}

fn beads_issues_path(world: &KanbusWorld) -> PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".beads")
        .join("issues.jsonl")
}

fn load_beads_records(path: &Path) -> Vec<Value> {
    let text = fs::read_to_string(path).expect("read issues.jsonl");
    text.lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(
                    serde_json::from_str::<serde_json::Value>(trimmed).expect("parse beads record"),
                )
            }
        })
        .collect()
}

#[given("a Beads fixture repository")]
fn given_beads_fixture_repo(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("beads-interop");
    if repo_path.exists() {
        fs::remove_dir_all(&repo_path).expect("clean existing repo");
    }
    fs::create_dir_all(repo_path.join(".beads")).expect("create beads dir");
    let fixture = fixture_beads_dir();
    fs::copy(
        fixture.join("issues.jsonl"),
        repo_path.join(".beads").join("issues.jsonl"),
    )
    .expect("copy issues");
    fs::copy(
        fixture.join("metadata.json"),
        repo_path.join(".beads").join("metadata.json"),
    )
    .expect("copy metadata");
    fs::write(repo_path.join(".kanbus.yml"), "").expect("write kanbus config");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    world.last_beads_issue_id = None;
}

#[when(expr = "I update the last created beads issue to status {string}")]
fn when_update_last_beads_issue(world: &mut KanbusWorld, status: String) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    run_cli(
        world,
        &format!("kanbus --beads update {} --status {}", identifier, status),
    );
}

#[when("I delete the last created beads issue")]
fn when_delete_last_beads_issue(world: &mut KanbusWorld) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    run_cli(world, &format!("kanbus --beads delete {}", identifier));
}

#[then("the last created beads issue should exist in beads issues.jsonl")]
fn then_last_issue_exists(world: &mut KanbusWorld) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    let records = load_beads_records(&beads_issues_path(world));
    assert!(records
        .iter()
        .any(|record| record.get("id").and_then(|id| id.as_str()) == Some(identifier)));
}

#[then("beads issues.jsonl should contain the last created beads issue")]
fn then_beads_contains_last_issue(world: &mut KanbusWorld) {
    then_last_issue_exists(world);
}

#[then(expr = "beads issues.jsonl should show the last created beads issue with status {string}")]
fn then_last_issue_has_status(world: &mut KanbusWorld, status: String) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    let records = load_beads_records(&beads_issues_path(world));
    let match_record = records.iter().find(|record| {
        record
            .get("id")
            .and_then(|id| id.as_str())
            .map(|value| value == identifier)
            .unwrap_or(false)
    });
    assert!(match_record.is_some(), "issue not found in beads JSONL");
    let found_status = match_record
        .and_then(|record| record.get("status"))
        .and_then(|value| value.as_str())
        .unwrap_or("");
    assert_eq!(found_status, status);
}

#[then("beads issues.jsonl should not contain the last created beads issue")]
fn then_beads_missing_last_issue(world: &mut KanbusWorld) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    let records = load_beads_records(&beads_issues_path(world));
    assert!(records.iter().all(|record| {
        record
            .get("id")
            .and_then(|id| id.as_str())
            .map(|value| value != identifier)
            .unwrap_or(true)
    }));
}

#[then("the last created beads issue should appear in the Kanbus beads list output")]
fn then_last_issue_in_list_output(world: &mut KanbusWorld) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    let stdout = world.stdout.as_ref().expect("command result missing");
    let display_key = format_issue_key(identifier, true);
    assert!(
        stdout.to_lowercase().contains(&display_key.to_lowercase()),
        "issue id not in list output"
    );
}

#[then("the last created beads issue should not appear in the Kanbus beads list output")]
fn then_last_issue_not_in_list_output(world: &mut KanbusWorld) {
    let identifier = world
        .last_beads_issue_id
        .as_ref()
        .expect("last beads issue id missing");
    let stdout = world.stdout.as_ref().expect("command result missing");
    let display_key = format_issue_key(identifier, true);
    assert!(
        !stdout.to_lowercase().contains(&display_key.to_lowercase()),
        "issue id unexpectedly present in list output"
    );
}
