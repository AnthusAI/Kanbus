use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::config::default_project_configuration;
use kanbus::config_loader::load_project_configuration;
use kanbus::file_io::load_project_directory;
use kanbus::issue_display::format_issue_for_display;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

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

fn write_default_config(repo_root: &PathBuf, project_key: &str) {
    let mut configuration = default_project_configuration();
    configuration.project_key = project_key.to_string();
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

#[given("a workspace with multiple Kanbus projects and duplicate fragments")]
fn given_workspace_with_duplicate_fragments(world: &mut KanbusWorld) {
    let root = create_repo(world, "workspace");
    let alpha_repo = root.join("alpha");
    let beta_repo = root.join("beta");
    let alpha_project = alpha_repo.join("project");
    let beta_project = beta_repo.join("project");

    write_issue(&alpha_project, &build_issue("alpha-aaaaaa", "Alpha task"));
    write_issue(&beta_project, &build_issue("beta-aaaaaa", "Beta task"));
    write_default_config(&alpha_repo, "alpha");
    write_default_config(&beta_repo, "beta");
}

#[given("issue \"kanbus-aaa\" has status \"open\" and type \"task\"")]
fn given_issue_status_type(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-aaa.json");
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let mut payload: serde_json::Value = serde_json::from_str(&contents).expect("parse");
    payload["status"] = "open".into();
    payload["type"] = "task".into();
    let updated = serde_json::to_string_pretty(&payload).expect("serialize");
    fs::write(&issue_path, updated).expect("write issue");
}

#[when(expr = "I format issue {string} for display")]
fn when_format_issue_display_generic(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    let config_path = project_dir
        .parent()
        .unwrap_or(&project_dir)
        .join(".kanbus.yml");
    let configuration = if config_path.exists() {
        Some(load_project_configuration(&config_path).expect("load configuration"))
    } else {
        None
    };
    world.formatted_output = Some(format_issue_for_display(
        &issue,
        configuration.as_ref(),
        false,
        false,
        None,
    ));
}

#[when(expr = "I format issue {string} for display with NO_COLOR set")]
fn when_format_issue_display_no_color(world: &mut KanbusWorld, identifier: String) {
    std::env::set_var("NO_COLOR", "1");
    when_format_issue_display_generic(world, identifier);
    std::env::remove_var("NO_COLOR");
}

#[when(expr = "I format issue {string} for display with color enabled")]
fn when_format_issue_display_with_color(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    let config_path = project_dir
        .parent()
        .unwrap_or(&project_dir)
        .join(".kanbus.yml");
    let configuration = if config_path.exists() {
        Some(load_project_configuration(&config_path).expect("load configuration"))
    } else {
        None
    };
    world.formatted_output = Some(format_issue_for_display(
        &issue,
        configuration.as_ref(),
        true,
        false,
        None,
    ));
}

#[when(expr = "I format issue {string} for display with color enabled without configuration")]
fn when_format_issue_display_without_configuration(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    world.formatted_output = Some(format_issue_for_display(&issue, None, true, false, None));
}

#[then("the formatted output should contain ANSI color codes")]
fn then_formatted_output_contains_ansi(world: &mut KanbusWorld) {
    let output = world.formatted_output.as_deref().unwrap_or("");
    assert!(output.contains("\u{1b}["));
}

#[then(expr = "the formatted output should contain text {string}")]
fn then_formatted_output_contains_text(world: &mut KanbusWorld, text: String) {
    let output = world.formatted_output.as_deref().unwrap_or("");
    assert!(output.contains(&text));
}
