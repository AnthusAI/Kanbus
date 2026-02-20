use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::config_loader::load_project_configuration;
use kanbus::file_io::load_project_directory;
use kanbus::issue_display::format_issue_for_display;
use kanbus::models::IssueData;

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

#[given("an issue \"kanbus-aaa\" exists with title \"Implement OAuth2 flow\"")]
fn given_issue_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = build_issue("kanbus-aaa", "Implement OAuth2 flow");
    write_issue_file(&project_dir, &issue);
}

#[given("an issue \"kanbus-desc\" exists with title \"Describe me\"")]
fn given_issue_desc_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = build_issue("kanbus-desc", "Describe me");
    write_issue_file(&project_dir, &issue);
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

#[when("I format issue \"kanbus-labels\" for display")]
fn when_format_issue_display(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-labels.json");
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    world.formatted_output = Some(format_issue_for_display(&issue, None, false, false));
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
    world.formatted_output = Some(format_issue_for_display(&issue, None, true, false));
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
