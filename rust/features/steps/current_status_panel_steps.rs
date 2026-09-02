use std::thread;
use std::time::Duration;

use cucumber::{given, then, when};
use reqwest::blocking::Client;
use serde_json::json;

use crate::step_definitions::console_ui_steps::{ConsoleIssue, ConsoleState};
use crate::step_definitions::initialization_steps::KanbusWorld;

const RIGHT_NOW_PLACEHOLDER: &str = "(no right-now summary)";
const STATUS_FEED_LIMIT: usize = 30;

fn require_console_state(world: &mut KanbusWorld) -> &mut ConsoleState {
    world
        .console_state
        .as_mut()
        .expect("console state not initialized")
}

fn find_issue_by_title(state: &ConsoleState, title: &str) -> Option<usize> {
    state.issues.iter().position(|issue| issue.title == title)
}

fn status_feed_issues(issues: &[ConsoleIssue]) -> Vec<&ConsoleIssue> {
    let mut sorted: Vec<&ConsoleIssue> = issues.iter().collect();
    sorted.sort_by(|left, right| {
        let left_key = left.updated_at.as_deref().unwrap_or("");
        let right_key = right.updated_at.as_deref().unwrap_or("");
        right_key
            .cmp(left_key)
            .then_with(|| left.title.cmp(&right.title))
    });
    sorted.truncate(STATUS_FEED_LIMIT);
    sorted
}

fn resolve_feed_summary(issue: &ConsoleIssue) -> String {
    match issue.right_now_summary.as_deref() {
        None | Some("") => RIGHT_NOW_PLACEHOLDER.to_string(),
        Some(summary) => summary.to_string(),
    }
}

fn post_notification(world: &KanbusWorld, body: serde_json::Value) {
    let port = world.console_port.unwrap_or(5174);
    let url = format!("http://127.0.0.1:{port}/api/notifications");
    thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("build http client");
        client
            .post(&url)
            .json(&body)
            .send()
            .expect("post notification");
    })
    .join()
    .expect("post notification thread");
}

#[when(expr = "I switch to the \"Current Status\" view")]
fn when_switch_current_status_view(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.panel_mode = "now".to_string();
    world.console_local_storage.panel_mode = Some("now".to_string());
}

#[given(expr = "I switch to the \"Current Status\" view")]
fn given_switch_current_status_view(world: &mut KanbusWorld) {
    when_switch_current_status_view(world);
}

#[then("the current status view should be active")]
fn then_current_status_view_active(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert_eq!(state.panel_mode, "now");
}

#[given(expr = "a status issue {string} updated at {string}")]
fn given_status_issue(world: &mut KanbusWorld, title: String, timestamp: String) {
    let state = require_console_state(world);
    let index = state.issues.len() + 1;
    state.issues.push(ConsoleIssue {
        identifier: Some(format!("kanbus-status-{index}")),
        title,
        issue_type: "task".to_string(),
        parent_title: None,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: Some(timestamp),
        closed_at: None,
        status: "open".to_string(),
        priority: 2,
        project_label: "kbs".to_string(),
        location: "shared".to_string(),
        right_now_summary: None,
    });
}

#[given(expr = "the status issue {string} has right-now summary {string}")]
fn given_status_issue_summary(world: &mut KanbusWorld, title: String, summary: String) {
    let state = require_console_state(world);
    let issue = state
        .issues
        .iter_mut()
        .find(|issue| issue.title == title)
        .expect("issue not found");
    issue.right_now_summary = Some(summary);
}

#[given("35 status issues exist with sequential update times")]
fn given_thirty_five_status_issues(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    for index in 0..35 {
        let day = index + 1;
        state.issues.push(ConsoleIssue {
            identifier: Some(format!("kanbus-status-{day}")),
            title: format!("Status issue {day}"),
            issue_type: "task".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: Some(format!("2026-01-{day:02}T10:00:00.000Z")),
            closed_at: None,
            status: "open".to_string(),
            priority: 2,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
            right_now_summary: None,
        });
    }
}

#[then(expr = "the status feed should list issues in order {string}")]
fn then_status_feed_order(world: &mut KanbusWorld, order: String) {
    let state = require_console_state(world);
    let expected: Vec<String> = order
        .split(',')
        .map(|title| title.trim().to_string())
        .collect();
    let actual: Vec<String> = status_feed_issues(&state.issues)
        .iter()
        .map(|issue| issue.title.clone())
        .collect();
    assert_eq!(actual, expected);
}

#[then(expr = "the status feed row for {string} should show title {string}")]
fn then_status_feed_row_title(world: &mut KanbusWorld, title: String, expected: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    assert_eq!(state.issues[index].title, expected);
}

#[then(expr = "the status feed row for {string} should show right-now summary {string}")]
fn then_status_feed_row_summary(world: &mut KanbusWorld, title: String, expected: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    assert_eq!(resolve_feed_summary(&state.issues[index]), expected);
}

#[when(expr = "the right-now summary for {string} is updated to {string}")]
fn when_right_now_summary_updated(world: &mut KanbusWorld, title: String, summary: String) {
    let state = require_console_state(world);
    let issue = state
        .issues
        .iter_mut()
        .find(|issue| issue.title == title)
        .expect("issue not found");
    issue.right_now_summary = Some(summary);
}

#[when(expr = "the console receives an issue update for {string} with right-now summary {string}")]
fn when_console_receives_issue_update(world: &mut KanbusWorld, title: String, summary: String) {
    let console_port = world.console_port;
    let notification: Option<serde_json::Value> = {
        let state = require_console_state(world);
        let issue = state
            .issues
            .iter_mut()
            .find(|issue| issue.title == title)
            .expect("issue not found");
        issue.right_now_summary = Some(summary.clone());
        if console_port.is_none() {
            None
        } else {
            let issue_id = issue
                .identifier
                .clone()
                .unwrap_or_else(|| issue.title.clone());
            let updated_at = issue.updated_at.clone().unwrap_or_default();
            let issue_type = issue.issue_type.clone();
            let status = issue.status.clone();
            let priority = issue.priority;
            let title_value = issue.title.clone();
            let created_at = issue
                .created_at
                .clone()
                .unwrap_or_else(|| updated_at.clone());
            let assignee = issue.assignee.clone();
            let closed_at = issue.closed_at.clone();
            let comments = issue
                .comments
                .iter()
                .map(|comment| {
                    json!({
                        "id": null,
                        "author": comment.author,
                        "text": "",
                        "created_at": comment.created_at,
                    })
                })
                .collect::<Vec<_>>();
            Some(json!({
                "type": "issue_updated",
                "issue_id": issue_id,
                "fields_changed": ["right_now_summary"],
                "issue_data": {
                    "id": issue_id,
                    "title": title_value,
                    "description": "",
                    "type": issue_type,
                    "status": status,
                    "priority": priority,
                    "assignee": assignee,
                    "creator": null,
                    "parent": null,
                    "labels": [],
                    "dependencies": [],
                    "comments": comments,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "closed_at": closed_at,
                    "right_now_summary": summary,
                    "right_now_updated_at": updated_at,
                    "custom": {},
                }
            }))
        }
    };
    if let Some(body) = notification {
        post_notification(world, body);
    }
}

#[then(expr = "the status feed should contain {int} rows")]
fn then_status_feed_row_count(world: &mut KanbusWorld, count: i32) {
    let state = require_console_state(world);
    let actual = status_feed_issues(&state.issues).len();
    assert_eq!(actual, count as usize);
}
