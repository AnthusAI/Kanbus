use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

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
        custom: std::collections::BTreeMap::new(),
    }
}

#[when("I run \"kanbus create --local Local task\"")]
fn when_run_create_local(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create --local Local task");
}

#[when("I run \"kanbus create --local local\"")]
fn when_run_create_local_duplicate(world: &mut KanbusWorld) {
    run_cli(world, "kanbus create --local local");
}

#[when("I run \"kanbus promote kanbus-local01\"")]
fn when_run_promote(world: &mut KanbusWorld) {
    run_cli(world, "kanbus promote kanbus-local01");
}

#[when("I run \"kanbus localize kanbus-shared01\"")]
fn when_run_localize(world: &mut KanbusWorld) {
    run_cli(world, "kanbus localize kanbus-shared01");
}

#[when("I run \"kanbus promote kanbus-missing\"")]
fn when_run_promote_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus promote kanbus-missing");
}

#[when("I run \"kanbus promote kanbus-dupe01\"")]
fn when_run_promote_dupe(world: &mut KanbusWorld) {
    run_cli(world, "kanbus promote kanbus-dupe01");
}

#[when("I run \"kanbus localize kanbus-missing\"")]
fn when_run_localize_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus localize kanbus-missing");
}

#[when("I run \"kanbus localize kanbus-dupe02\"")]
fn when_run_localize_dupe(world: &mut KanbusWorld) {
    run_cli(world, "kanbus localize kanbus-dupe02");
}

#[given("a local issue \"kanbus-local01\" exists")]
fn given_local_issue_exists(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("kanbus-local01", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"kanbus-dupe01\" exists")]
fn given_local_issue_dupe_exists(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("kanbus-dupe01", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"kanbus-other\" exists")]
fn given_local_issue_other_exists(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("kanbus-other", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"kanbus-dupe02\" exists")]
fn given_local_issue_dupe02_exists(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("kanbus-dupe02", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"kanbus-local\" exists")]
fn given_local_issue_local_exists(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("kanbus-local", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given(".gitignore already includes \"project-local/\"")]
fn given_gitignore_includes_project_local(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    fs::write(gitignore_path, "project-local/\n").expect("write gitignore");
}

#[given("a .gitignore without a trailing newline exists")]
fn given_gitignore_without_trailing_newline(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    fs::write(gitignore_path, "node_modules").expect("write gitignore");
}

#[then("a local issue file should be created in the local issues directory")]
fn then_local_issue_file_created(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issues_dir = local_dir.join("issues");
    let count = fs::read_dir(&issues_dir)
        .expect("read local issues")
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

#[then(expr = "the local issues directory should contain {int} issue file")]
fn then_local_issues_directory_contains_count(world: &mut KanbusWorld, count: i32) {
    let local_dir = local_project_dir(world);
    let issues_dir = local_dir.join("issues");
    let actual = fs::read_dir(&issues_dir)
        .expect("read local issues")
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

#[then("issue \"kanbus-local01\" should exist in the shared issues directory")]
fn then_issue_exists_shared_local(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-local01.json");
    assert!(issue_path.exists());
}

#[then("issue \"kanbus-local01\" should not exist in the local issues directory")]
fn then_issue_missing_local_local(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue_path = local_dir.join("issues").join("kanbus-local01.json");
    assert!(!issue_path.exists());
}

#[then("issue \"kanbus-shared01\" should exist in the local issues directory")]
fn then_issue_exists_local_shared(world: &mut KanbusWorld) {
    let local_dir = local_project_dir(world);
    let issue_path = local_dir.join("issues").join("kanbus-shared01.json");
    assert!(issue_path.exists());
}

#[then("issue \"kanbus-shared01\" should not exist in the shared issues directory")]
fn then_issue_missing_shared_shared(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-shared01.json");
    assert!(!issue_path.exists());
}

#[then(".gitignore should include \"project-local/\"")]
fn then_gitignore_includes_project_local(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    let contents = fs::read_to_string(gitignore_path).expect("read gitignore");
    assert!(contents.lines().any(|line| line == "project-local/"));
}

#[then(".gitignore should include \"project-local/\" only once")]
fn then_gitignore_includes_once(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    let contents = fs::read_to_string(gitignore_path).expect("read gitignore");
    let count = contents
        .lines()
        .filter(|line| *line == "project-local/")
        .count();
    assert_eq!(count, 1);
}
