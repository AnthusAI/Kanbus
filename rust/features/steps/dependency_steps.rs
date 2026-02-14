use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::dependencies::{add_dependency, list_ready_issues};
use kanbus::file_io::load_project_directory;
use kanbus::models::{DependencyLink, IssueData};

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

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn read_issue_file(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
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

#[given(expr = "issue {string} depends on {string} with type {string}")]
fn given_issue_depends_on(
    world: &mut KanbusWorld,
    identifier: String,
    target: String,
    dependency_type: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue(&identifier);
    issue.dependencies.push(DependencyLink {
        target,
        dependency_type,
    });
    write_issue_file(&project_dir, &issue);
}

#[when("I run \"kanbus dep add kanbus-child --blocked-by kanbus-parent\"")]
fn when_run_dep_add_blocked(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-child --blocked-by kanbus-parent");
}

#[when("I run \"kanbus dep add kanbus-left --relates-to kanbus-right\"")]
fn when_run_dep_add_relates(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-left --relates-to kanbus-right");
}

#[when("I run \"kanbus dep add kanbus-left --blocked-by kanbus-right\"")]
fn when_run_dep_add_blocked_left(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-left --blocked-by kanbus-right");
}

#[when("I run \"kanbus dep remove kanbus-left --blocked-by kanbus-right\"")]
fn when_run_dep_remove(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep remove kanbus-left --blocked-by kanbus-right");
}

#[when("I run \"kanbus dep remove kanbus-left --relates-to kanbus-right\"")]
fn when_run_dep_remove_relates(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep remove kanbus-left --relates-to kanbus-right");
}

#[when("I run \"kanbus dep add kanbus-b --blocked-by kanbus-a\"")]
fn when_run_dep_add_cycle(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-b --blocked-by kanbus-a");
}

#[when("I run \"kanbus dep add kanbus-a --blocked-by kanbus-c\"")]
fn when_run_dep_add_shared_downstream(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-a --blocked-by kanbus-c");
}

#[when("I run \"kanbus dep add kanbus-missing --blocked-by kanbus-parent\"")]
fn when_run_dep_add_missing_issue(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-missing --blocked-by kanbus-parent");
}

#[when("I run \"kanbus ready\"")]
fn when_run_ready(world: &mut KanbusWorld) {
    run_cli(world, "kanbus ready");
}

#[when("I run \"kanbus ready --local-only --no-local\"")]
fn when_run_ready_conflict(world: &mut KanbusWorld) {
    run_cli(world, "kanbus ready --local-only --no-local");
}

#[when("I run \"kanbus ready --local-only\"")]
fn when_run_ready_local_only(world: &mut KanbusWorld) {
    run_cli(world, "kanbus ready --local-only");
}

#[when("I run \"kanbus ready --no-local\"")]
fn when_run_ready_no_local(world: &mut KanbusWorld) {
    run_cli(world, "kanbus ready --no-local");
}

#[when("ready issues are listed for a single project")]
fn when_ready_issues_listed_single_project(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    let canonical = root.canonicalize().unwrap_or_else(|_| root.clone());
    let issues = list_ready_issues(&canonical, true, false).expect("ready list");
    world.ready_issue_ids = Some(issues.into_iter().map(|issue| issue.identifier).collect());
}

#[then(expr = "the ready list should contain {string}")]
fn then_ready_list_contains(world: &mut KanbusWorld, identifier: String) {
    let ids = world.ready_issue_ids.as_ref().expect("ready ids not set");
    assert!(ids.contains(&identifier));
}

#[when("I run \"kanbus dep add kanbus-child\"")]
fn when_run_dep_add_missing_target(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep add kanbus-child");
}

#[when("I run \"kanbus dep remove kanbus-child\"")]
fn when_run_dep_remove_missing_target(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep remove kanbus-child");
}

#[when("I run \"kanbus dep remove kanbus-missing --blocked-by kanbus-parent\"")]
fn when_run_dep_remove_missing_issue(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep remove kanbus-missing --blocked-by kanbus-parent");
}

#[when("I add an invalid dependency type")]
fn when_add_invalid_dependency(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    match add_dependency(root, "kanbus-left", "kanbus-right", "invalid-type") {
        Ok(_) => {
            world.exit_code = Some(0);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stderr = Some(error.to_string());
        }
    }
    world.stdout = Some(String::new());
}

#[when("I run \"kanbus dep tree kanbus-child\"")]
fn when_run_dep_tree_child(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-child");
}

#[when("I run \"kanbus dep tree kanbus-c --depth 1\"")]
fn when_run_dep_tree_depth(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-c --depth 1");
}

#[when("I run \"kanbus dep tree kanbus-root\"")]
fn when_run_dep_tree_root(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-root");
}

#[when("I run \"kanbus dep tree kanbus-missing\"")]
fn when_run_dep_tree_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-missing");
}

#[when("I run \"kanbus dep tree kanbus-a\"")]
fn when_run_dep_tree_a(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-a");
}

#[when("I run \"kanbus dep tree kanbus-child --format json\"")]
fn when_run_dep_tree_json(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-child --format json");
}

#[when("I run \"kanbus dep tree kanbus-child --format dot\"")]
fn when_run_dep_tree_dot(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-child --format dot");
}

#[when("I run \"kanbus dep tree kanbus-child --format invalid\"")]
fn when_run_dep_tree_invalid(world: &mut KanbusWorld) {
    run_cli(world, "kanbus dep tree kanbus-child --format invalid");
}

#[given("a dependency tree with more than 25 nodes exists")]
fn given_large_dependency_tree(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let chain_length = 26;
    for index in 0..chain_length {
        let identifier = if index == 0 {
            "kanbus-root".to_string()
        } else {
            format!("kanbus-node-{}", index)
        };
        let mut issue = build_issue(&identifier);
        if index < chain_length - 1 {
            let target = format!("kanbus-node-{}", index + 1);
            issue.dependencies.push(DependencyLink {
                target,
                dependency_type: "blocked-by".to_string(),
            });
        }
        write_issue_file(&project_dir, &issue);
    }
}

#[then(expr = "issue {string} should depend on {string} with type {string}")]
fn then_issue_should_depend_on(
    world: &mut KanbusWorld,
    identifier: String,
    target: String,
    dependency_type: String,
) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    assert!(issue
        .dependencies
        .iter()
        .any(|link| link.target == target && link.dependency_type == dependency_type));
}

#[then(expr = "issue {string} should not depend on {string} with type {string}")]
fn then_issue_should_not_depend_on(
    world: &mut KanbusWorld,
    identifier: String,
    target: String,
    dependency_type: String,
) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    assert!(!issue
        .dependencies
        .iter()
        .any(|link| link.target == target && link.dependency_type == dependency_type));
}

#[then(expr = "issue {string} should have 1 dependency")]
fn then_issue_has_single_dependency(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    assert_eq!(issue.dependencies.len(), 1);
}
