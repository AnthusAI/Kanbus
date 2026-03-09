use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::given;

use kanbus::config::default_project_configuration;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn create_repo(world: &mut KanbusWorld, name: &str) -> PathBuf {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join(name);
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path.clone());
    world.temp_dir = Some(temp_dir);
    repo_path
}

fn write_default_config(repo_root: &PathBuf) {
    let configuration = default_project_configuration();
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(repo_root.join(".kanbus.yml"), payload).expect("write config");
}

fn build_issue(identifier: &str, title: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: String::new(),
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

fn write_issue(project_dir: &PathBuf, issue: &IssueData) {
    let issues_dir = project_dir.join("issues");
    fs::create_dir_all(&issues_dir).expect("create issues dir");
    let issue_path = issues_dir.join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given("a repository with nested project directories")]
fn given_repo_nested_projects(world: &mut KanbusWorld) {
    let root = create_repo(world, "nested-projects");
    let root_project = root.join("project");
    let nested_project = root.join("nested").join("project");
    write_issue(&root_project, &build_issue("kanbus-root", "Root task"));
    write_issue(
        &nested_project,
        &build_issue("kanbus-nested", "Nested task"),
    );
}

#[given("a workspace with nested Kanbus projects")]
fn given_workspace_with_nested_kanbus_projects(world: &mut KanbusWorld) {
    let root = create_repo(world, "workspace-nested-projects");
    let alpha_repo = root.join("alpha");
    let beta_repo = root.join("beta");
    let alpha_project = alpha_repo.join("project");
    let beta_project = beta_repo.join("project");
    write_issue(&alpha_project, &build_issue("kanbus-alpha", "Alpha task"));
    write_issue(&beta_project, &build_issue("kanbus-beta", "Beta task"));
    write_default_config(&alpha_repo);
    write_default_config(&beta_repo);
}

#[given("a Kanbus project with a nested Kanbus project")]
fn given_kanbus_project_with_nested_kanbus_project(world: &mut KanbusWorld) {
    let root = create_repo(world, "root-with-nested");
    let root_project = root.join("project");
    let nested_repo = root.join("nested");
    let nested_project = nested_repo.join("project");
    write_issue(&root_project, &build_issue("kanbus-root", "Root task"));
    write_issue(
        &nested_project,
        &build_issue("kanbus-nested", "Nested task"),
    );
    write_default_config(&root);
    write_default_config(&nested_repo);
}

#[given("a repository with a project directory above the current directory")]
fn given_repo_project_above_cwd(world: &mut KanbusWorld) {
    let root = create_repo(world, "project-above");
    let project_dir = root.join("project");
    write_issue(&project_dir, &build_issue("kanbus-above", "Above task"));
    let child_dir = root.join("child");
    fs::create_dir_all(&child_dir).expect("create child dir");
    world.working_directory = Some(child_dir);
}
