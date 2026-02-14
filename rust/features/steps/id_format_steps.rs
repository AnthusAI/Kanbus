use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use cucumber::{given, then, when};
use regex::Regex;

use kanbus::cli::run_from_args_with_output;
use kanbus::ids::format_issue_key;
use kanbus::migration::migrate_from_beads;
use tempfile::TempDir;

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

fn project_issues_dir(world: &KanbusWorld) -> PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join("project")
        .join("issues")
}

fn current_issue_ids(world: &KanbusWorld) -> HashSet<String> {
    project_issues_dir(world)
        .read_dir()
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .filter_map(|entry| {
            entry
                .path()
                .file_stem()
                .and_then(|s| s.to_str())
                .map(String::from)
        })
        .collect()
}

#[given("a migrated Kanbus repository from the Beads fixture")]
fn given_migrated_kanbus_repo(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().to_path_buf();
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("create beads dir");
    let fixture = fixture_beads_dir();
    fs::copy(fixture.join("issues.jsonl"), beads_dir.join("issues.jsonl")).expect("copy issues");
    fs::copy(
        fixture.join("metadata.json"),
        beads_dir.join("metadata.json"),
    )
    .expect("copy metadata");
    std::process::Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    migrate_from_beads(&repo_path).expect("migrate from beads");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    world.existing_kanbus_ids = None;
    world.last_kanbus_issue_id = None;
}

#[given("I record existing Kanbus issue ids")]
fn given_record_existing_ids(world: &mut KanbusWorld) {
    let ids = current_issue_ids(world);
    world.existing_kanbus_ids = Some(ids);
}

#[when("I run \"kanbus --beads create Beads epic --type epic\"")]
fn when_run_create_beads_epic(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Beads epic --type epic");
}

#[when("I run \"kanbus --beads create Beads child --parent bdx-epic\"")]
fn when_run_create_beads_child(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --beads create Beads child --parent bdx-epic");
}

#[when("I run \"kanbus create Native epic --type epic\"")]
#[given("I run \"kanbus create Native epic --type epic\"")]
fn when_run_create_native_epic(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Native epic --type epic");
}

#[when("I run \"kanbus create Native deletable --type epic\"")]
fn when_run_create_native_deletable(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Native deletable --type epic");
    record_new_kanbus_id(world);
}

fn record_new_kanbus_id(world: &mut KanbusWorld) {
    let before = world
        .existing_kanbus_ids
        .clone()
        .unwrap_or_else(HashSet::new);
    let current = current_issue_ids(world);
    let new_ids: HashSet<String> = current.difference(&before).cloned().collect();
    assert!(
        !new_ids.is_empty(),
        "no new issue created to record Kanbus id"
    );
    assert!(
        new_ids.len() == 1,
        "expected one new id, found {}",
        new_ids.len()
    );
    world.last_kanbus_issue_id = Some(new_ids.iter().next().expect("new id").to_string());
    world.existing_kanbus_ids = Some(current);
}

#[then(expr = "stdout should match pattern {string}")]
fn then_stdout_matches_pattern(world: &mut KanbusWorld, pattern: String) {
    let stdout = world.stdout.as_ref().expect("command result missing");
    let ansi_regex = Regex::new(r"\x1b\[[0-9;]*m").expect("regex");
    let cleaned = ansi_regex.replace_all(stdout, "");
    let regex = regex::RegexBuilder::new(&pattern)
        .case_insensitive(true)
        .build()
        .expect("regex");
    assert!(
        regex.is_match(cleaned.as_ref()),
        "pattern {} not found in {:?}",
        pattern,
        cleaned
    );
}

#[then(expr = "beads issues.jsonl should contain an id matching {string}")]
fn then_beads_jsonl_contains_pattern(world: &mut KanbusWorld, pattern: String) {
    let issues_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".beads")
        .join("issues.jsonl");
    let text = fs::read_to_string(issues_path).expect("read issues.jsonl");
    let regex = Regex::new(&pattern).expect("regex");
    let mut matches = false;
    for line in text.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: serde_json::Value = serde_json::from_str(line).expect("parse beads record");
        if let Some(value) = record.get("id").and_then(|id| id.as_str()) {
            if regex.is_match(value) {
                matches = true;
                break;
            }
        }
    }
    assert!(matches, "no id matching {}", pattern);
}

#[then(expr = "the last Kanbus issue id should match {string}")]
fn then_last_kanbus_id_matches(world: &mut KanbusWorld, pattern: String) {
    let before = world
        .existing_kanbus_ids
        .clone()
        .unwrap_or_else(HashSet::new);
    let current = current_issue_ids(world);
    let new_ids: HashSet<String> = current.difference(&before).cloned().collect();
    assert!(!new_ids.is_empty(), "no new issue created");
    assert!(
        new_ids.len() == 1,
        "expected one new id, found {}",
        new_ids.len()
    );
    let identifier = new_ids.iter().next().expect("new id");
    let regex = Regex::new(&pattern).expect("regex");
    assert!(
        regex.is_match(identifier),
        "{} does not match {}",
        identifier,
        pattern
    );
    world.last_kanbus_issue_id = Some(identifier.to_string());
    world.existing_kanbus_ids = Some(current);
}

#[given("I record the new Kanbus issue id")]
fn given_record_new_kanbus_id(world: &mut KanbusWorld) {
    record_new_kanbus_id(world);
}

#[when("I create a native task under the recorded Kanbus epic")]
fn when_create_native_task_under_recorded_epic(world: &mut KanbusWorld) {
    let parent_id = world
        .last_kanbus_issue_id
        .as_ref()
        .expect("no recorded epic id");
    run_cli(
        world,
        &format!("kanbus create Native task --parent {}", parent_id),
    );
}

#[then("the last Kanbus issue id should be recorded")]
fn then_last_kanbus_id_recorded(world: &mut KanbusWorld) {
    assert!(
        world.last_kanbus_issue_id.is_some(),
        "no Kanbus issue id recorded"
    );
}

#[then("the recorded Kanbus issue id should appear in the Kanbus list output")]
fn then_recorded_id_in_list_output(world: &mut KanbusWorld) {
    let identifier = world
        .last_kanbus_issue_id
        .as_ref()
        .expect("no Kanbus issue id recorded");
    let stdout = world.stdout.as_ref().expect("command result missing");
    let display_key = format_issue_key(identifier, true);
    assert!(
        stdout.contains(&display_key),
        "recorded id not found in Kanbus list output"
    );
}

#[then("the recorded Kanbus issue id should not appear in the Kanbus list output")]
fn then_recorded_id_not_in_list_output(world: &mut KanbusWorld) {
    let identifier = world
        .last_kanbus_issue_id
        .as_ref()
        .expect("no Kanbus issue id recorded");
    let stdout = world.stdout.as_ref().expect("command result missing");
    let display_key = format_issue_key(identifier, true);
    assert!(
        !stdout.contains(&display_key),
        "recorded id unexpectedly present in Kanbus list output"
    );
}

#[when("I delete the recorded Kanbus issue")]
fn when_delete_recorded_kanbus_issue(world: &mut KanbusWorld) {
    let identifier = world
        .last_kanbus_issue_id
        .as_ref()
        .expect("no Kanbus issue id recorded");
    run_cli(world, &format!("kanbus delete {}", identifier));
}
