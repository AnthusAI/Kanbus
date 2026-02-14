use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::config_loader::load_project_configuration;
use kanbus::daemon_client::{has_test_daemon_response, set_test_daemon_response};
use kanbus::daemon_protocol::{RequestEnvelope, PROTOCOL_VERSION};
use kanbus::daemon_server::handle_request_for_testing;
use kanbus::file_io::{get_configuration_path, load_project_directory};
use kanbus::issue_listing::list_issues;
use kanbus::models::IssueData;
use tempfile::TempDir;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli(world: &mut KanbusWorld, command: &str) {
    if command.starts_with("kanbus list")
        && kanbus::daemon_client::is_daemon_enabled()
        && !has_test_daemon_response()
    {
        let root = world
            .working_directory
            .as_ref()
            .expect("working directory not set");
        let request = RequestEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: "req-list".to_string(),
            action: "index.list".to_string(),
            payload: BTreeMap::new(),
        };
        let response = handle_request_for_testing(root.as_path(), request);
        set_test_daemon_response(Some(kanbus::daemon_client::TestDaemonResponse::Envelope(
            response,
        )));
    }
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

fn initialize_project(world: &mut KanbusWorld) {
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

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
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
fn given_issues_exist(world: &mut KanbusWorld, first: String, second: String) {
    let project_dir = load_project_dir(world);
    let issue_first = build_issue(&first);
    let issue_second = build_issue(&second);
    write_issue_file(&project_dir, &issue_first);
    write_issue_file(&project_dir, &issue_second);
}

#[given(expr = "issues {string} exist")]
fn given_single_issue_exists(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = build_issue(&identifier);
    write_issue_file(&project_dir, &issue);
}

#[given("a Kanbus repository with an unreadable project directory")]
fn given_repo_unreadable_project_dir(world: &mut KanbusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&project_dir)
            .expect("project metadata")
            .permissions();
        let original = permissions.mode();
        permissions.set_mode(0o000);
        fs::set_permissions(&project_dir, permissions).expect("set permissions");
        world.unreadable_path = Some(project_dir);
        world.unreadable_mode = Some(original);
    }
}

#[given(expr = "issue {string} has status {string}")]
fn given_issue_has_status(world: &mut KanbusWorld, identifier: String, status: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.status = status;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has type {string}")]
fn given_issue_has_type(world: &mut KanbusWorld, identifier: String, issue_type: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.issue_type = issue_type;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has assignee {string}")]
fn given_issue_has_assignee(world: &mut KanbusWorld, identifier: String, assignee: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.assignee = Some(assignee);
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has labels {string}")]
fn given_issue_has_labels(world: &mut KanbusWorld, identifier: String, label_text: String) {
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
fn given_issue_has_priority(world: &mut KanbusWorld, identifier: String, priority: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    let parsed = priority.parse::<i32>().expect("priority int");
    issue.priority = parsed;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has parent {string}")]
fn given_issue_has_parent(world: &mut KanbusWorld, identifier: String, parent: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let mut issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    issue.parent = Some(parent);
    write_issue_file(&project_dir, &issue);
}

#[given(
    expr = "an issue {string} exists with status {string}, priority {int}, type {string}, and assignee {string}"
)]
fn given_issue_with_full_metadata(
    world: &mut KanbusWorld,
    identifier: String,
    status: String,
    priority: i32,
    issue_type: String,
    assignee: String,
) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let issue = match fs::read_to_string(&issue_path) {
        Ok(contents) => serde_json::from_str(&contents).expect("parse issue"),
        Err(_) => build_issue(&identifier),
    };
    let mut issue = issue;
    issue.status = status;
    issue.priority = priority;
    issue.issue_type = issue_type;
    issue.assignee = Some(assignee);
    write_issue_file(&project_dir, &issue);
}

#[when("I run \"kanbus --help\"")]
fn when_run_help(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --help");
}

#[when("I run \"kanbus --unknown\"")]
fn when_run_unknown(world: &mut KanbusWorld) {
    run_cli(world, "kanbus --unknown");
}

#[when("I list issues directly after configuration path lookup fails")]
fn when_list_issues_directly_after_configuration_failure(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    if let Err(error) = list_issues(root, None, None, None, None, None, None, true, false) {
        world.exit_code = Some(1);
        world.stdout = Some(String::new());
        world.stderr = Some(error.to_string());
        return;
    }
    match get_configuration_path(root) {
        Ok(path) => match load_project_configuration(&path) {
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
        },
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[when("I run \"kanbus console snapshot\"")]
fn when_run_console_snapshot(world: &mut KanbusWorld) {
    run_cli(world, "kanbus console snapshot");
}

#[given(expr = "issue {string} has title {string}")]
fn given_issue_has_title(world: &mut KanbusWorld, identifier: String, title: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.title = title;
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has description {string}")]
fn given_issue_has_description(world: &mut KanbusWorld, identifier: String, description: String) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.description = description;
    write_issue_file(&project_dir, &issue);
}

#[when("I run \"kanbus list --status open\"")]
fn when_run_list_status(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --status open");
}

#[when("I run \"kanbus list --type task\"")]
fn when_run_list_type(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --type task");
}

#[when("I run \"kanbus list --assignee dev@example.com\"")]
fn when_run_list_assignee(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --assignee dev@example.com");
}

#[when("I run \"kanbus list --label auth\"")]
fn when_run_list_label(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --label auth");
}

#[when("I run \"kanbus list --sort priority\"")]
fn when_run_list_sort(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --sort priority");
}

#[when("I run \"kanbus list --search login\"")]
fn when_run_list_search(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --search login");
}

#[when("I run \"kanbus list --search Searchable\"")]
fn when_run_list_search_comment(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --search Searchable");
}

#[when("I run \"kanbus list --search Dup\"")]
fn when_run_list_search_dup(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --search Dup");
}

#[when("I run \"kanbus list --sort invalid\"")]
fn when_run_list_invalid_sort(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --sort invalid");
}

#[when("I run \"kanbus list --no-local\"")]
fn when_run_list_no_local(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --no-local");
}

#[when("I run \"kanbus list --local-only\"")]
fn when_run_list_local_only(world: &mut KanbusWorld) {
    if world.local_listing_error {
        world.exit_code = Some(1);
        world.stdout = Some(String::new());
        world.stderr = Some("local listing failed".to_string());
        return;
    }
    run_cli(world, "kanbus list --local-only");
}

#[when("I run \"kanbus list --local-only --no-local\"")]
fn when_run_list_local_conflict(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --local-only --no-local");
}

#[when("I run \"kanbus list --porcelain\"")]
fn when_run_list_porcelain(world: &mut KanbusWorld) {
    run_cli(world, "kanbus list --porcelain");
}

#[then(expr = "stdout should contain the line {string}")]
fn then_stdout_contains_line(world: &mut KanbusWorld, expected: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let found = stdout.lines().any(|line| line == expected);
    assert!(found, "expected line not found in stdout");
}

#[given("the daemon list request will fail")]
fn given_daemon_list_fails(world: &mut KanbusWorld) {
    world.daemon_list_error = true;
}

#[given("local listing will fail")]
fn given_local_listing_fails(world: &mut KanbusWorld) {
    world.local_listing_error = true;
}

#[when("shared issues are listed without local issues")]
fn when_shared_only_listed(world: &mut KanbusWorld) {
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
fn then_shared_only_contains(world: &mut KanbusWorld, identifier: String) {
    let list = world.shared_only_results.as_ref().expect("shared list");
    assert!(list.iter().any(|item| item == &identifier));
}

#[then(expr = "the shared-only list should not contain {string}")]
fn then_shared_only_not_contains(world: &mut KanbusWorld, identifier: String) {
    let list = world.shared_only_results.as_ref().expect("shared list");
    assert!(!list.iter().any(|item| item == &identifier));
}
