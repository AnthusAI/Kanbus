use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::dependencies::{add_dependency, list_ready_issues};
use kanbus::file_io::load_project_directory;
use kanbus::models::{DependencyLink, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

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

#[given(expr = "issue {string} has dependency {string} of type {string}")]
fn given_issue_has_dependency(
    world: &mut KanbusWorld,
    identifier: String,
    target: String,
    dependency_type: String,
) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let mut issue = if issue_path.exists() {
        read_issue_file(&project_dir, &identifier)
    } else {
        build_issue(&identifier)
    };
    issue.dependencies.push(DependencyLink {
        target,
        dependency_type,
    });
    write_issue_file(&project_dir, &issue);
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

#[then(expr = "issue {string} has dependency {string} of type {string}")]
fn then_issue_has_dependency(
    world: &mut KanbusWorld,
    identifier: String,
    target: String,
    dependency_type: String,
) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    let found = issue
        .dependencies
        .iter()
        .any(|dep| dep.target == target && dep.dependency_type == dependency_type);
    assert!(found, "expected dependency not found");
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
