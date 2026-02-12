use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::dependencies::add_dependency;
use taskulus::file_io::load_project_directory;
use taskulus::models::{DependencyLink, IssueData};

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
    world: &mut TaskulusWorld,
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

#[when("I run \"tsk dep add tsk-child --blocked-by tsk-parent\"")]
fn when_run_dep_add_blocked(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-child --blocked-by tsk-parent");
}

#[when("I run \"tsk dep add tsk-left --relates-to tsk-right\"")]
fn when_run_dep_add_relates(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-left --relates-to tsk-right");
}

#[when("I run \"tsk dep add tsk-left --blocked-by tsk-right\"")]
fn when_run_dep_add_blocked_left(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-left --blocked-by tsk-right");
}

#[when("I run \"tsk dep remove tsk-left --blocked-by tsk-right\"")]
fn when_run_dep_remove(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep remove tsk-left --blocked-by tsk-right");
}

#[when("I run \"tsk dep remove tsk-left --relates-to tsk-right\"")]
fn when_run_dep_remove_relates(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep remove tsk-left --relates-to tsk-right");
}

#[when("I run \"tsk dep add tsk-b --blocked-by tsk-a\"")]
fn when_run_dep_add_cycle(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-b --blocked-by tsk-a");
}

#[when("I run \"tsk dep add tsk-a --blocked-by tsk-c\"")]
fn when_run_dep_add_shared_downstream(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-a --blocked-by tsk-c");
}

#[when("I run \"tsk dep add tsk-missing --blocked-by tsk-parent\"")]
fn when_run_dep_add_missing_issue(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-missing --blocked-by tsk-parent");
}

#[when("I run \"tsk ready\"")]
fn when_run_ready(world: &mut TaskulusWorld) {
    run_cli(world, "tsk ready");
}

#[when("I run \"tsk ready --local-only --no-local\"")]
fn when_run_ready_conflict(world: &mut TaskulusWorld) {
    run_cli(world, "tsk ready --local-only --no-local");
}

#[when("I run \"tsk ready --local-only\"")]
fn when_run_ready_local_only(world: &mut TaskulusWorld) {
    run_cli(world, "tsk ready --local-only");
}

#[when("I run \"tsk ready --no-local\"")]
fn when_run_ready_no_local(world: &mut TaskulusWorld) {
    run_cli(world, "tsk ready --no-local");
}

#[when("I run \"tsk dep add tsk-child\"")]
fn when_run_dep_add_missing_target(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep add tsk-child");
}

#[when("I run \"tsk dep remove tsk-child\"")]
fn when_run_dep_remove_missing_target(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep remove tsk-child");
}

#[when("I run \"tsk dep remove tsk-missing --blocked-by tsk-parent\"")]
fn when_run_dep_remove_missing_issue(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep remove tsk-missing --blocked-by tsk-parent");
}

#[when("I add an invalid dependency type")]
fn when_add_invalid_dependency(world: &mut TaskulusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    match add_dependency(root, "tsk-left", "tsk-right", "invalid-type") {
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

#[when("I run \"tsk dep tree tsk-child\"")]
fn when_run_dep_tree_child(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-child");
}

#[when("I run \"tsk dep tree tsk-c --depth 1\"")]
fn when_run_dep_tree_depth(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-c --depth 1");
}

#[when("I run \"tsk dep tree tsk-root\"")]
fn when_run_dep_tree_root(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-root");
}

#[when("I run \"tsk dep tree tsk-missing\"")]
fn when_run_dep_tree_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-missing");
}

#[when("I run \"tsk dep tree tsk-a\"")]
fn when_run_dep_tree_a(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-a");
}

#[when("I run \"tsk dep tree tsk-child --format json\"")]
fn when_run_dep_tree_json(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-child --format json");
}

#[when("I run \"tsk dep tree tsk-child --format dot\"")]
fn when_run_dep_tree_dot(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-child --format dot");
}

#[when("I run \"tsk dep tree tsk-child --format invalid\"")]
fn when_run_dep_tree_invalid(world: &mut TaskulusWorld) {
    run_cli(world, "tsk dep tree tsk-child --format invalid");
}

#[given("a dependency tree with more than 25 nodes exists")]
fn given_large_dependency_tree(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let chain_length = 26;
    for index in 0..chain_length {
        let identifier = if index == 0 {
            "tsk-root".to_string()
        } else {
            format!("tsk-node-{}", index)
        };
        let mut issue = build_issue(&identifier);
        if index < chain_length - 1 {
            let target = format!("tsk-node-{}", index + 1);
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
    world: &mut TaskulusWorld,
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
    world: &mut TaskulusWorld,
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
fn then_issue_has_single_dependency(world: &mut TaskulusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    assert_eq!(issue.dependencies.len(), 1);
}
