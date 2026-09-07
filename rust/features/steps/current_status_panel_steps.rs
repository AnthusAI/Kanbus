use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use cucumber::{given, then, when};
use reqwest::blocking::Client;
use serde_json::json;

use crate::step_definitions::console_ui_steps::{ConsoleIssue, ConsoleState};
use crate::step_definitions::initialization_steps::KanbusWorld;

const RIGHT_NOW_PLACEHOLDER: &str = "(no right-now summary)";
const RIGHT_NOW_LOADING_SUMMARY: &str = "Generating right-now summary...";
const RIGHT_NOW_UNAVAILABLE_SUMMARY: &str = "Right-now summary unavailable";
const STATUS_FEED_LIMIT: usize = 30;
const NOW_STATUS_FILTER_ALL: &str = "all";

struct StatusTreeNode {
    issue_index: usize,
    children: Vec<StatusTreeNode>,
}

fn require_console_state(world: &mut KanbusWorld) -> &mut ConsoleState {
    world
        .console_state
        .as_mut()
        .expect("console state not initialized")
}

fn find_issue_by_title(state: &ConsoleState, title: &str) -> Option<usize> {
    state.issues.iter().position(|issue| issue.title == title)
}

fn resolve_parent_identifier(state: &ConsoleState, issue: &ConsoleIssue) -> Option<String> {
    let parent_title = issue.parent_title.as_ref()?;
    let parent_index = find_issue_by_title(state, parent_title)?;
    state.issues[parent_index]
        .identifier
        .clone()
        .or_else(|| Some(state.issues[parent_index].title.clone()))
}

fn compare_recently_updated(left: &ConsoleIssue, right: &ConsoleIssue) -> std::cmp::Ordering {
    let left_key = left.updated_at.as_deref().unwrap_or("");
    let right_key = right.updated_at.as_deref().unwrap_or("");
    right_key.cmp(left_key).then_with(|| {
        let left_id = left.identifier.as_deref().unwrap_or(left.title.as_str());
        let right_id = right.identifier.as_deref().unwrap_or(right.title.as_str());
        left_id.cmp(right_id)
    })
}

fn issue_matches_status_filter(state: &ConsoleState, issue: &ConsoleIssue) -> bool {
    state.status_filter == NOW_STATUS_FILTER_ALL || issue.status == state.status_filter
}

fn now_visible_issues(state: &ConsoleState) -> Vec<&ConsoleIssue> {
    state
        .issues
        .iter()
        .filter(|issue| issue_matches_status_filter(state, issue))
        .collect()
}

fn issue_tree_identifier(issue: &ConsoleIssue) -> String {
    issue
        .identifier
        .clone()
        .unwrap_or_else(|| issue.title.clone())
}

fn now_tree_identifiers(state: &ConsoleState) -> std::collections::HashSet<String> {
    let matching: Vec<String> = state
        .issues
        .iter()
        .filter(|issue| issue_matches_status_filter(state, issue))
        .map(issue_tree_identifier)
        .collect();
    if matching.len() == state.issues.len() {
        return matching.into_iter().collect();
    }
    let mut children_by_parent: HashMap<String, Vec<String>> = HashMap::new();
    for issue in &state.issues {
        if let Some(parent_identifier) = resolve_parent_identifier(state, issue) {
            children_by_parent
                .entry(parent_identifier)
                .or_default()
                .push(issue_tree_identifier(issue));
        }
    }
    let mut included = std::collections::HashSet::new();
    let mut pending = matching;
    while let Some(identifier) = pending.pop() {
        if !included.insert(identifier.clone()) {
            continue;
        }
        if let Some(children) = children_by_parent.get(&identifier) {
            pending.extend(children.iter().cloned());
        }
    }
    included
}

fn build_status_tree(state: &ConsoleState) -> Vec<StatusTreeNode> {
    let identifiers = now_tree_identifiers(state);
    let mut children_by_parent: HashMap<String, Vec<usize>> = HashMap::new();
    for (index, issue) in state.issues.iter().enumerate() {
        if !identifiers.contains(&issue_tree_identifier(issue)) {
            continue;
        }
        let Some(parent_identifier) = resolve_parent_identifier(state, issue) else {
            continue;
        };
        children_by_parent
            .entry(parent_identifier)
            .or_default()
            .push(index);
    }
    for children in children_by_parent.values_mut() {
        children.sort_by(|left, right| {
            compare_recently_updated(&state.issues[*left], &state.issues[*right])
        });
    }

    let mut roots = Vec::new();
    for (index, issue) in state.issues.iter().enumerate() {
        if !identifiers.contains(&issue_tree_identifier(issue)) {
            continue;
        }
        match resolve_parent_identifier(state, issue) {
            None => roots.push(index),
            Some(parent_identifier) if !identifiers.contains(&parent_identifier) => {
                roots.push(index);
            }
            Some(_) => {}
        }
    }
    roots.sort_by(|left, right| {
        compare_recently_updated(&state.issues[*left], &state.issues[*right])
    });

    fn build_node(
        state: &ConsoleState,
        index: usize,
        children_by_parent: &HashMap<String, Vec<usize>>,
    ) -> StatusTreeNode {
        let issue_identifier = state.issues[index]
            .identifier
            .clone()
            .unwrap_or_else(|| state.issues[index].title.clone());
        let child_indices = children_by_parent
            .get(&issue_identifier)
            .cloned()
            .unwrap_or_default();
        StatusTreeNode {
            issue_index: index,
            children: child_indices
                .into_iter()
                .map(|child_index| build_node(state, child_index, children_by_parent))
                .collect(),
        }
    }

    roots
        .into_iter()
        .map(|index| build_node(state, index, &children_by_parent))
        .collect()
}

fn status_tree_has_children(state: &ConsoleState, issue: &ConsoleIssue) -> bool {
    let identifiers = now_tree_identifiers(state);
    let issue_identifier = issue_tree_identifier(issue);
    state.issues.iter().any(|candidate| {
        identifiers.contains(&issue_tree_identifier(candidate))
            && resolve_parent_identifier(state, candidate).as_deref()
                == Some(issue_identifier.as_str())
    })
}

fn status_tree_node_expanded(state: &ConsoleState, issue: &ConsoleIssue) -> bool {
    if let Some(expanded) = state.status_tree_expanded_overrides.get(&issue.title) {
        return *expanded;
    }
    state.default_tree_expanded
}

fn status_tree_visible_titles(state: &ConsoleState) -> Vec<String> {
    if !state.status_tree_mode {
        return Vec::new();
    }

    let mut visible_titles = Vec::new();

    fn walk(state: &ConsoleState, node: &StatusTreeNode, visible_titles: &mut Vec<String>) {
        visible_titles.push(state.issues[node.issue_index].title.clone());
        let issue = &state.issues[node.issue_index];
        if !status_tree_has_children(state, issue) {
            return;
        }
        if !status_tree_node_expanded(state, issue) {
            return;
        }
        for child in &node.children {
            walk(state, child, visible_titles);
        }
    }

    for root in build_status_tree(state) {
        walk(state, &root, &mut visible_titles);
    }
    visible_titles
}

fn status_feed_issues<'a>(issues: Vec<&'a ConsoleIssue>) -> Vec<&'a ConsoleIssue> {
    let mut sorted = issues;
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

fn resolve_feed_summary(state: &ConsoleState, issue: &ConsoleIssue) -> String {
    if let Some(summary) = issue.right_now_summary.as_deref() {
        if !summary.is_empty() {
            return summary.to_string();
        }
    }
    match state.now_backfill_state.as_str() {
        "loading" => RIGHT_NOW_LOADING_SUMMARY.to_string(),
        "unavailable" => RIGHT_NOW_UNAVAILABLE_SUMMARY.to_string(),
        _ => RIGHT_NOW_PLACEHOLDER.to_string(),
    }
}

pub fn simulate_now_jit_backfill(state: &mut ConsoleState) {
    state.now_backfill_state = "loading".to_string();
    for issue in state.issues.iter_mut() {
        if issue.status != "in_progress" {
            continue;
        }
        if issue
            .right_now_summary
            .as_ref()
            .is_some_and(|summary| !summary.is_empty())
        {
            continue;
        }
        let identifier = issue_tree_identifier(issue);
        issue.right_now_summary = Some(format!("Mock right-now summary for {identifier}."));
    }
    state.now_backfill_state = "ready".to_string();
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

#[then("the current status view should be active")]
fn then_current_status_view_active(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert_eq!(state.panel_mode, "now");
}

#[then("the type filter selector should be hidden")]
fn then_type_filter_selector_hidden(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert_eq!(state.panel_mode, "now");
    let app_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("apps")
        .join("console")
        .join("src")
        .join("App.tsx");
    let app_source = fs::read_to_string(app_path).expect("read App.tsx");
    assert!(
        app_source.contains("panelMode !== \"now\""),
        "App.tsx does not hide the type filter on Now"
    );
}

#[then("the type filter selector should be visible")]
fn then_type_filter_selector_visible(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert_ne!(state.panel_mode, "now");
}

#[then(expr = "the status tree node for {string} should be expandable")]
fn then_status_tree_node_expandable(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    let issue = &state.issues[index];
    assert!(
        status_tree_has_children(state, issue),
        "expected expandable tree node: {title}"
    );
}

#[then(expr = "the now panel board title should be {string}")]
fn then_now_panel_board_title(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    assert_eq!(state.board_name, title);
}

#[then("the now panel board title should be the repository directory name")]
fn then_now_panel_board_title_is_repository_directory(world: &mut KanbusWorld) {
    let expected = world
        .working_directory
        .as_ref()
        .expect("working directory")
        .file_name()
        .and_then(|name| name.to_str())
        .expect("directory name")
        .to_string();
    then_now_panel_board_title(world, expected);
}

#[then(expr = "the panel mode selector labels should be {string}")]
fn then_panel_mode_selector_labels(_world: &mut KanbusWorld, labels: String) {
    let expected: Vec<String> = labels
        .split(',')
        .map(|label| label.trim().to_string())
        .collect();
    let actual = panel_mode_selector_labels();
    assert_eq!(actual, expected);
}

#[then("the status tree view should be enabled")]
fn then_status_tree_view_enabled(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert!(
        state.status_tree_mode,
        "expected status tree view to be enabled"
    );
}

fn panel_mode_selector_labels() -> Vec<String> {
    let app_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("apps")
        .join("console")
        .join("src")
        .join("App.tsx");
    let app_source = fs::read_to_string(app_path).expect("read App.tsx");
    let start = app_source
        .find("const panelModeOptions")
        .expect("panelModeOptions not found in App.tsx");
    let end = start.saturating_add(800).min(app_source.len());
    let chunk = &app_source[start..end];
    let mut labels = Vec::new();
    for line in chunk.lines() {
        let trimmed = line.trim();
        let Some(rest) = trimmed.strip_prefix("buildOption(") else {
            continue;
        };
        let parts: Vec<&str> = rest.split('"').collect();
        if parts.len() >= 4 {
            labels.push(parts[3].to_string());
        }
    }
    labels
}

#[given(expr = "a status issue {string} updated at {string}")]
fn given_status_issue(world: &mut KanbusWorld, title: String, timestamp: String) {
    push_status_issue(world, title, "task", timestamp, "in_progress", None);
}

#[given(expr = "the status issue {string} has status {string}")]
fn given_status_issue_has_status(world: &mut KanbusWorld, title: String, status: String) {
    let state = require_console_state(world);
    let issue = state
        .issues
        .iter_mut()
        .find(|issue| issue.title == title)
        .expect("issue not found");
    issue.status = status;
}

fn push_status_issue(
    world: &mut KanbusWorld,
    title: String,
    issue_type: &str,
    timestamp: String,
    status: &str,
    parent_title: Option<String>,
) {
    let state = require_console_state(world);
    let index = state.issues.len() + 1;
    state.issues.push(ConsoleIssue {
        identifier: Some(format!("kanbus-status-{index}")),
        title,
        issue_type: issue_type.to_string(),
        parent_title,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: Some(timestamp),
        closed_at: None,
        status: status.to_string(),
        priority: 2,
        project_label: "kbs".to_string(),
        location: "shared".to_string(),
        agent: None,
        right_now_summary: None,
    });
}

#[given(expr = "a status hierarchy root {string} of type {string} updated at {string}")]
fn given_status_hierarchy_root(
    world: &mut KanbusWorld,
    title: String,
    issue_type: String,
    timestamp: String,
) {
    let state = require_console_state(world);
    let index = state.issues.len() + 1;
    state.issues.push(ConsoleIssue {
        identifier: Some(format!("kanbus-status-{index}")),
        title,
        issue_type,
        parent_title: None,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: Some(timestamp),
        closed_at: None,
        status: "in_progress".to_string(),
        priority: 2,
        project_label: "kbs".to_string(),
        location: "shared".to_string(),
        agent: None,
        right_now_summary: None,
    });
}

#[given(
    expr = "a status hierarchy child {string} of type {string} under {string} updated at {string}"
)]
fn given_status_hierarchy_child(
    world: &mut KanbusWorld,
    title: String,
    issue_type: String,
    parent_title: String,
    timestamp: String,
) {
    let state = require_console_state(world);
    let index = state.issues.len() + 1;
    state.issues.push(ConsoleIssue {
        identifier: Some(format!("kanbus-status-{index}")),
        title,
        issue_type,
        parent_title: Some(parent_title),
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: Some(timestamp),
        closed_at: None,
        status: "in_progress".to_string(),
        priority: 2,
        project_label: "kbs".to_string(),
        location: "shared".to_string(),
        agent: None,
        right_now_summary: None,
    });
}

#[given(expr = "the console right now configuration has default_tree_expanded {word}")]
fn given_console_default_tree_expanded(world: &mut KanbusWorld, expected: String) {
    let state = require_console_state(world);
    state.default_tree_expanded = expected.eq_ignore_ascii_case("true");
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
            status: "in_progress".to_string(),
            priority: 2,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
            agent: None,
            right_now_summary: None,
        });
    }
}

#[when("I enable the status tree view")]
fn when_enable_status_tree_view(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.status_tree_mode = true;
}

#[when("I disable the status tree view")]
#[given("I disable the status tree view")]
fn when_disable_status_tree_view(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.status_tree_mode = false;
}

#[when(expr = "I select the now status filter {string}")]
#[given(expr = "I select the now status filter {string}")]
fn when_select_now_status_filter(world: &mut KanbusWorld, status: String) {
    let state = require_console_state(world);
    state.status_filter = status;
}

#[when(expr = "I collapse the status tree node for {string}")]
fn when_collapse_status_tree_node(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    assert!(
        find_issue_by_title(state, &title).is_some(),
        "issue not found: {title}"
    );
    state.status_tree_expanded_overrides.insert(title, false);
}

#[when(expr = "I expand the status tree node for {string}")]
fn when_expand_status_tree_node(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    assert!(
        find_issue_by_title(state, &title).is_some(),
        "issue not found: {title}"
    );
    state.status_tree_expanded_overrides.insert(title, true);
}

#[then(expr = "the status feed should list issues in order {string}")]
fn then_status_feed_order(world: &mut KanbusWorld, order: String) {
    let state = require_console_state(world);
    let expected: Vec<String> = order
        .split(',')
        .map(|title| title.trim().to_string())
        .collect();
    let actual: Vec<String> = status_feed_issues(now_visible_issues(state))
        .iter()
        .map(|issue| issue.title.clone())
        .collect();
    assert_eq!(actual, expected);
}

#[then(expr = "the status tree should list issues in order {string}")]
fn then_status_tree_order(world: &mut KanbusWorld, order: String) {
    let state = require_console_state(world);
    let expected: Vec<String> = order
        .split(',')
        .map(|title| title.trim().to_string())
        .collect();
    let actual = status_tree_visible_titles(state);
    assert_eq!(actual, expected);
}

#[then(expr = "the status tree node for {string} should be expanded")]
fn then_status_tree_node_expanded(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    let issue = &state.issues[index];
    assert!(
        status_tree_has_children(state, issue),
        "issue has no tree children: {title}"
    );
    assert!(
        status_tree_node_expanded(state, issue),
        "expected tree node expanded: {title}"
    );
}

#[then(expr = "the status tree node for {string} should be collapsed")]
fn then_status_tree_node_collapsed(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    let issue = &state.issues[index];
    assert!(
        status_tree_has_children(state, issue),
        "issue has no tree children: {title}"
    );
    assert!(
        !status_tree_node_expanded(state, issue),
        "expected tree node collapsed: {title}"
    );
}

#[then(expr = "the status feed row for {string} should show title {string}")]
fn then_status_feed_row_title(world: &mut KanbusWorld, title: String, expected: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    assert_eq!(state.issues[index].title, expected);
}

#[then(expr = "the status tree row for {string} should show title {string}")]
fn then_status_tree_row_title(world: &mut KanbusWorld, title: String, expected: String) {
    then_status_feed_row_title(world, title, expected);
}

#[then(expr = "the status feed row for {string} should show right-now summary {string}")]
fn then_status_feed_row_summary(world: &mut KanbusWorld, title: String, expected: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    assert_eq!(resolve_feed_summary(state, &state.issues[index]), expected);
}

#[then(expr = "the status tree row for {string} should show right-now summary {string}")]
fn then_status_tree_row_summary(world: &mut KanbusWorld, title: String, expected: String) {
    then_status_feed_row_summary(world, title, expected);
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
    let actual = status_feed_issues(now_visible_issues(state)).len();
    assert_eq!(actual, count as usize);
}

#[when("I request the console now snapshot")]
fn when_request_console_now_snapshot(world: &mut KanbusWorld) {
    let port = world.console_port.expect("console port not set");
    let url = format!("http://127.0.0.1:{port}/api/now");
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .expect("build http client");
    let response = client.get(&url).send().expect("get console now snapshot");
    let status = response.status();
    let body = response.text().expect("read console now response");
    assert_eq!(
        status,
        200,
        "console now snapshot failed: {body}"
    );
    let issues: Vec<serde_json::Value> =
        serde_json::from_str(&body).expect("parse console now issues");
    world.console_now_issues = Some(issues);
}

#[then(expr = "the console now response should include issue {string} with right-now summary {string}")]
fn then_console_now_response_includes_summary(
    world: &mut KanbusWorld,
    issue_id: String,
    expected_summary: String,
) {
    let issues = world
        .console_now_issues
        .as_ref()
        .expect("console now response not loaded");
    let issue = issues
        .iter()
        .find(|entry| entry.get("id").and_then(|value| value.as_str()) == Some(issue_id.as_str()))
        .unwrap_or_else(|| panic!("issue not found in now response: {issue_id}"));
    let actual = issue
        .get("right_now_summary")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    assert_eq!(actual, expected_summary);
}
