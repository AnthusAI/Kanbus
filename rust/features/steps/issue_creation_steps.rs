use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when};
use regex::Regex;
use serde_json::Value;
use std::env;
use tempfile::TempDir;

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::issue_creation::{create_issue, IssueCreationRequest};

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

#[when("I create an issue directly with title \"Implement OAuth2 flow\"")]
fn when_create_issue_directly(world: &mut KanbusWorld) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let request = IssueCreationRequest {
        root: root.clone(),
        title: "Implement OAuth2 flow".to_string(),
        issue_type: None,
        priority: None,
        assignee: None,
        parent: None,
        labels: Vec::new(),
        description: None,
        local: false,
    };
    match create_issue(&request) {
        Ok(_) => {
            world.exit_code = Some(0);
            world.stdout = Some(String::new());
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn capture_issue_identifier(world: &mut KanbusWorld) -> String {
    let stdout = world.stdout.as_ref().expect("stdout");
    let ansi_regex = Regex::new(r"\x1b\[[0-9;]*m").expect("regex");
    let clean_stdout = ansi_regex.replace_all(stdout, "");
    let full_regex = Regex::new(
        r"([A-Za-z0-9]+-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    )
    .expect("regex");
    if let Some(capture) = full_regex
        .captures(&clean_stdout)
        .and_then(|matches| matches.get(1))
        .map(|match_value| match_value.as_str().to_string())
    {
        world.stdout = Some(stdout.to_string());
        return capture;
    }

    let labeled_regex = Regex::new(r"(?i)\bID:\s*([A-Za-z0-9.-]+)").expect("regex");
    let abbreviated = labeled_regex
        .captures(&clean_stdout)
        .and_then(|matches| matches.get(1))
        .map(|match_value| match_value.as_str().to_string())
        .unwrap_or_else(|| {
            let fallback_regex = Regex::new(r"\b([A-Za-z0-9]{6}(?:\.[0-9]+)?)\b").expect("regex");
            fallback_regex
                .captures(&clean_stdout)
                .and_then(|matches| matches.get(1))
                .map(|match_value| match_value.as_str().to_string())
                .expect("issue id not found")
        });
    let (abbrev_base, abbrev_suffix) = parse_abbreviation(&abbreviated);
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let entries = fs::read_dir(issues_dir).expect("read issues dir");
    for entry in entries {
        let path = entry.expect("issue entry").path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let identifier = path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .unwrap_or_default()
            .to_string();
        if matches_abbreviation(&identifier, &abbrev_base, abbrev_suffix.as_deref()) {
            world.stdout = Some(stdout.to_string());
            return identifier;
        }
    }
    panic!("issue id not found");
}

fn parse_abbreviation(value: &str) -> (String, Option<String>) {
    let remainder = if let Some((_, rest)) = value.split_once('-') {
        rest
    } else {
        value
    };
    if let Some((base, suffix)) = remainder.split_once('.') {
        (base.to_lowercase(), Some(suffix.to_lowercase()))
    } else {
        (remainder.to_lowercase(), None)
    }
}

fn matches_abbreviation(identifier: &str, base: &str, suffix: Option<&str>) -> bool {
    let remainder = if let Some((_, rest)) = identifier.split_once('-') {
        rest
    } else {
        identifier
    };
    let (id_base, id_suffix) = if let Some((head, tail)) = remainder.split_once('.') {
        (head, Some(tail))
    } else {
        (remainder, None)
    };
    let normalized = id_base.replace('-', "").to_lowercase();
    if !normalized.starts_with(base) {
        return false;
    }
    match (suffix, id_suffix) {
        (None, _) => true,
        (Some(expected), Some(actual)) => actual.to_lowercase() == expected.to_lowercase(),
        _ => false,
    }
}

fn load_issue_json(project_dir: &PathBuf, identifier: &str) -> Value {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given("a Kanbus project with default configuration")]
fn given_kanbus_project(world: &mut KanbusWorld) {
    env::set_var("KANBUS_NO_DAEMON", "1");
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    run_cli(world, "kanbus init");
    assert_eq!(world.exit_code, Some(0));
}

#[when("I run \"kanbus create Implement OAuth2 flow\"")]
fn when_run_create_default(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Implement OAuth2 flow");
}

#[when("I run \"kanbus create implement oauth2 flow\"")]
fn when_run_create_duplicate_title(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create implement oauth2 flow");
}

#[when("I run \"kanbus create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent kanbus-epic01 --label auth --label urgent --description \\\"Bug in login\\\"\"")]
fn when_run_create_full(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent kanbus-epic01 --label auth --label urgent --description \"Bug in login\"");
}

#[when("I run \"kanbus create Bad Issue --type nonexistent\"")]
fn when_run_create_invalid_type(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Bad Issue --type nonexistent");
}

#[when("I run \"kanbus create Orphan --parent kanbus-nonexistent\"")]
fn when_run_create_missing_parent(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Orphan --parent kanbus-nonexistent");
}

#[when("I run \"kanbus create\"")]
fn when_run_create_without_title(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create");
}

#[when("I run \"kanbus create Bad Priority --priority 99\"")]
fn when_run_create_invalid_priority(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Bad Priority --priority 99");
}

#[when(expr = "I run \"kanbus create Child Task --type {word} --parent kanbus-parent\"")]
fn when_run_create_child_task_with_parent(world: &mut KanbusWorld, issue_type: String) {
    run_cli(
        world,
        &format!("kanbus create Child Task --type {issue_type} --parent kanbus-parent"),
    );
}

#[when(expr = "I run \"kanbus create Child --type {word} --parent kanbus-bug01\"")]
fn when_run_create_child_with_bug_parent(world: &mut KanbusWorld, issue_type: String) {
    run_cli(
        world,
        &format!("kanbus create Child --type {issue_type} --parent kanbus-bug01"),
    );
}

#[when("I run \"kanbus create Standalone Task --type task\"")]
fn when_run_create_standalone_task(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Standalone Task --type task");
}

#[when("I run \"kanbus create Snapshot issue\"")]
fn when_run_create_snapshot_issue(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create Snapshot issue");
}

#[then("the command should succeed")]
fn then_command_succeeds(world: &mut KanbusWorld) {
    assert_eq!(
        world.exit_code,
        Some(0),
        "stderr: {:?}",
        world.stderr.as_deref().unwrap_or("")
    );
}

#[then("stdout should contain a valid issue ID")]
fn then_stdout_contains_issue_id(world: &mut KanbusWorld) {
    let _ = capture_issue_identifier(world);
}

#[then("an issue file should be created in the issues directory")]
fn then_issue_file_created(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let count = fs::read_dir(&issues_dir)
        .expect("read issues dir")
        .filter(|entry| {
            let Ok(item) = entry else {
                return false;
            };
            let path = item.path();
            path.extension()
                .and_then(|ext| ext.to_str())
                .map(|ext| ext == "json")
                .unwrap_or(false)
        })
        .count();
    assert_eq!(count, 1);
}

#[then(expr = "the issues directory should contain {int} issue file")]
fn then_issues_directory_contains_count(world: &mut KanbusWorld, count: i32) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let actual = fs::read_dir(&issues_dir)
        .expect("read issues dir")
        .filter(|entry| {
            let Ok(item) = entry else {
                return false;
            };
            let path = item.path();
            path.extension()
                .and_then(|ext| ext.to_str())
                .map(|ext| ext == "json")
                .unwrap_or(false)
        })
        .count();
    assert_eq!(actual as i32, count);
}

#[then("the created issue should have title \"Implement OAuth2 flow\"")]
fn then_created_issue_title(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["title"], "Implement OAuth2 flow");
}

#[then("the created issue should have type \"task\"")]
fn then_created_issue_type_task(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["type"], "task");
}

#[then("the created issue should have status \"open\"")]
fn then_created_issue_status(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["status"], "open");
}

#[then("the created issue should have priority 2")]
fn then_created_issue_priority(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["priority"], 2);
}

#[then("the created issue should have an empty labels list")]
fn then_created_issue_labels_empty(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["labels"].as_array().map(Vec::len), Some(0));
}

#[then("the created issue should have an empty dependencies list")]
fn then_created_issue_dependencies_empty(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["dependencies"].as_array().map(Vec::len), Some(0));
}

#[then("the created issue should have a created_at timestamp")]
fn then_created_issue_created_at(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert!(payload.get("created_at").is_some());
}

#[then("the created issue should have an updated_at timestamp")]
fn then_created_issue_updated_at(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert!(payload.get("updated_at").is_some());
}

#[then("the created issue should have type \"bug\"")]
fn then_created_issue_type_bug(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["type"], "bug");
}

#[then("the created issue should have priority 1")]
fn then_created_issue_priority_one(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["priority"], 1);
}

#[then("the created issue should have assignee \"dev@example.com\"")]
fn then_created_issue_assignee(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["assignee"], "dev@example.com");
}

#[then("the created issue should have parent \"kanbus-epic01\"")]
fn then_created_issue_parent(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["parent"], "kanbus-epic01");
}

#[then("the created issue should have labels \"auth, urgent\"")]
fn then_created_issue_labels(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    let labels = payload["labels"]
        .as_array()
        .expect("labels array")
        .iter()
        .filter_map(|value| value.as_str())
        .collect::<Vec<_>>();
    assert_eq!(labels, vec!["auth", "urgent"]);
}

#[then("the created issue should have description \"Bug in login\"")]
fn then_created_issue_description(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["description"], "Bug in login");
}

#[then("the created issue should have no parent")]
fn then_created_issue_no_parent(world: &mut KanbusWorld) {
    let identifier = capture_issue_identifier(world);
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert!(payload["parent"].is_null());
}
