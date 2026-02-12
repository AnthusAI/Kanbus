use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::file_io::load_project_directory;
use taskulus::models::IssueData;

use crate::step_definitions::initialization_steps::TaskulusWorld;

fn run_cli(world: &mut TaskulusWorld, command: &str) {
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

fn load_project_dir(world: &TaskulusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn local_project_dir(world: &TaskulusWorld) -> PathBuf {
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

#[when("I run \"tsk create --local Local task\"")]
fn when_run_create_local(world: &mut TaskulusWorld) {
    run_cli(world, "tsk create --local Local task");
}

#[when("I run \"tsk promote tsk-local01\"")]
fn when_run_promote(world: &mut TaskulusWorld) {
    run_cli(world, "tsk promote tsk-local01");
}

#[when("I run \"tsk localize tsk-shared01\"")]
fn when_run_localize(world: &mut TaskulusWorld) {
    run_cli(world, "tsk localize tsk-shared01");
}

#[when("I run \"tsk promote tsk-missing\"")]
fn when_run_promote_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk promote tsk-missing");
}

#[when("I run \"tsk promote tsk-dupe01\"")]
fn when_run_promote_dupe(world: &mut TaskulusWorld) {
    run_cli(world, "tsk promote tsk-dupe01");
}

#[when("I run \"tsk localize tsk-missing\"")]
fn when_run_localize_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk localize tsk-missing");
}

#[when("I run \"tsk localize tsk-dupe02\"")]
fn when_run_localize_dupe(world: &mut TaskulusWorld) {
    run_cli(world, "tsk localize tsk-dupe02");
}

#[given("a local issue \"tsk-local01\" exists")]
fn given_local_issue_exists(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("tsk-local01", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"tsk-dupe01\" exists")]
fn given_local_issue_dupe_exists(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("tsk-dupe01", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"tsk-other\" exists")]
fn given_local_issue_other_exists(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("tsk-other", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"tsk-dupe02\" exists")]
fn given_local_issue_dupe02_exists(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("tsk-dupe02", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given("a local issue \"tsk-local\" exists")]
fn given_local_issue_local_exists(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue = build_issue("tsk-local", "Local");
    write_issue_file(&local_dir, &issue);
}

#[given(".gitignore already includes \"project-local/\"")]
fn given_gitignore_includes_project_local(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    fs::write(gitignore_path, "project-local/\n").expect("write gitignore");
}

#[given("a .gitignore without a trailing newline exists")]
fn given_gitignore_without_trailing_newline(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    fs::write(gitignore_path, "node_modules").expect("write gitignore");
}

#[then("a local issue file should be created in the local issues directory")]
fn then_local_issue_file_created(world: &mut TaskulusWorld) {
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

#[then("issue \"tsk-local01\" should exist in the shared issues directory")]
fn then_issue_exists_shared_local(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("tsk-local01.json");
    assert!(issue_path.exists());
}

#[then("issue \"tsk-local01\" should not exist in the local issues directory")]
fn then_issue_missing_local_local(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue_path = local_dir.join("issues").join("tsk-local01.json");
    assert!(!issue_path.exists());
}

#[then("issue \"tsk-shared01\" should exist in the local issues directory")]
fn then_issue_exists_local_shared(world: &mut TaskulusWorld) {
    let local_dir = local_project_dir(world);
    let issue_path = local_dir.join("issues").join("tsk-shared01.json");
    assert!(issue_path.exists());
}

#[then("issue \"tsk-shared01\" should not exist in the shared issues directory")]
fn then_issue_missing_shared_shared(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("tsk-shared01.json");
    assert!(!issue_path.exists());
}

#[then(".gitignore should include \"project-local/\"")]
fn then_gitignore_includes_project_local(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let gitignore_path = project_dir
        .parent()
        .expect("project parent")
        .join(".gitignore");
    let contents = fs::read_to_string(gitignore_path).expect("read gitignore");
    assert!(contents.lines().any(|line| line == "project-local/"));
}

#[then(".gitignore should include \"project-local/\" only once")]
fn then_gitignore_includes_once(world: &mut TaskulusWorld) {
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
