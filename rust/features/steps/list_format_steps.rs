use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::config_loader::load_project_configuration;
use kanbus::file_io::load_project_directory;
use kanbus::issue_line::{compute_widths, format_issue_line};
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn build_issue(
    identifier: &str,
    title: &str,
    issue_type: &str,
    status: &str,
    parent: Option<&str>,
    priority: i32,
) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: "".to_string(),
        issue_type: issue_type.to_string(),
        status: status.to_string(),
        priority,
        assignee: None,
        creator: None,
        parent: parent.map(|value| value.to_string()),
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given("issues for list color coverage exist")]
fn given_issues_for_list_color_coverage(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("kanbus-line-epic", "Epic", "epic", "open", None, 0),
        build_issue(
            "kanbus-line-task",
            "Task",
            "task",
            "in_progress",
            Some("kanbus-line-epic"),
            1,
        ),
        build_issue("kanbus-line-bug", "Bug", "bug", "blocked", None, 2),
        build_issue("kanbus-line-story", "Story", "story", "closed", None, 3),
        build_issue("kanbus-line-chore", "Chore", "chore", "deferred", None, 4),
        build_issue(
            "kanbus-line-initiative",
            "Initiative",
            "initiative",
            "unknown",
            None,
            9,
        ),
        build_issue(
            "kanbus-line-sub",
            "Sub",
            "sub-task",
            "open",
            Some("kanbus-line-epic"),
            2,
        ),
        build_issue("kanbus-line-event", "Event", "event", "open", None, 2),
        build_issue("kanbus-line-unknown", "Unknown", "mystery", "open", None, 2),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[when("I format list lines for color coverage")]
fn when_format_list_lines_for_color_coverage(world: &mut KanbusWorld) {
    let original_no_color = std::env::var("NO_COLOR").ok();
    std::env::remove_var("NO_COLOR");

    let project_dir = load_project_dir(world);
    let config_path = project_dir
        .parent()
        .unwrap_or(&project_dir)
        .join(".kanbus.yml");
    let configuration = if config_path.exists() {
        Some(load_project_configuration(&config_path).expect("load configuration"))
    } else {
        None
    };
    let mut issues = Vec::new();
    for entry in fs::read_dir(project_dir.join("issues")).expect("read issues dir") {
        let entry = entry.expect("issue entry");
        let contents = fs::read_to_string(entry.path()).expect("read issue");
        let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
        issues.push(issue);
    }
    let widths = compute_widths(&issues, false);
    let mut lines = Vec::new();
    for issue in &issues {
        lines.push(format_issue_line(
            issue,
            Some(&widths),
            false,
            false,
            configuration.as_ref(),
        ));
        lines.push(format_issue_line(issue, Some(&widths), false, false, None));
    }
    world.formatted_output = Some(lines.join("\n"));

    match original_no_color {
        Some(value) => std::env::set_var("NO_COLOR", value),
        None => std::env::remove_var("NO_COLOR"),
    }
}

#[when(expr = "I format the list line for issue {string}")]
fn when_format_list_line_for_issue(world: &mut KanbusWorld, identifier: String) {
    let original_no_color = std::env::var("NO_COLOR").ok();
    std::env::remove_var("NO_COLOR");

    let project_dir = load_project_dir(world);
    let config_path = project_dir
        .parent()
        .unwrap_or(&project_dir)
        .join(".kanbus.yml");
    let configuration = if config_path.exists() {
        Some(load_project_configuration(&config_path).expect("load configuration"))
    } else {
        None
    };
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    let widths = compute_widths(std::slice::from_ref(&issue), false);
    let line = format_issue_line(&issue, Some(&widths), false, false, configuration.as_ref());
    world.formatted_output = Some(line);

    match original_no_color {
        Some(value) => std::env::set_var("NO_COLOR", value),
        None => std::env::remove_var("NO_COLOR"),
    }
}

#[when(expr = "I format the list line for issue {string} with NO_COLOR set")]
fn when_format_list_line_for_issue_no_color(world: &mut KanbusWorld, identifier: String) {
    let original_no_color = std::env::var("NO_COLOR").ok();
    std::env::set_var("NO_COLOR", "1");

    let project_dir = load_project_dir(world);
    let config_path = project_dir
        .parent()
        .unwrap_or(&project_dir)
        .join(".kanbus.yml");
    let configuration = if config_path.exists() {
        Some(load_project_configuration(&config_path).expect("load configuration"))
    } else {
        None
    };
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let issue: IssueData = serde_json::from_str(&contents).expect("parse issue");
    let widths = compute_widths(std::slice::from_ref(&issue), false);
    let line = format_issue_line(&issue, Some(&widths), false, false, configuration.as_ref());
    world.formatted_output = Some(line);

    match original_no_color {
        Some(value) => std::env::set_var("NO_COLOR", value),
        None => std::env::remove_var("NO_COLOR"),
    }
}

#[then("each formatted line should contain ANSI color codes")]
fn then_each_formatted_line_contains_ansi(world: &mut KanbusWorld) {
    let output = world.formatted_output.as_deref().unwrap_or("");
    let lines: Vec<&str> = output
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    assert!(!lines.is_empty(), "no formatted lines");
    assert!(lines.iter().all(|line| line.contains("\u{1b}[")));
}

#[then("the formatted output should contain no ANSI color codes")]
fn then_formatted_output_has_no_ansi(world: &mut KanbusWorld) {
    let output = world.formatted_output.as_deref().unwrap_or("");
    let lines: Vec<&str> = output
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    assert!(!lines.is_empty(), "no formatted lines");
    assert!(lines.iter().all(|line| !line.contains("\u{1b}[")));
}
