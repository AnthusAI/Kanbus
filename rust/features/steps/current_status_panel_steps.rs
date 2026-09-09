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
    let issues_by_identifier: HashMap<String, usize> = state
        .issues
        .iter()
        .enumerate()
        .map(|(index, issue)| (issue_tree_identifier(issue), index))
        .collect();
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
        if let Some(&issue_index) = issues_by_identifier.get(&identifier) {
            if let Some(parent_identifier) =
                resolve_parent_identifier(state, &state.issues[issue_index])
            {
                pending.push(parent_identifier);
            }
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

fn resolve_feed_summary(issue: &ConsoleIssue) -> String {
    match issue.right_now_summary.as_deref() {
        None => String::new(),
        Some(summary) => summary.trim().to_string(),
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
    assert_eq!(resolve_feed_summary(&state.issues[index]), expected);
}

#[then(expr = "the status tree row for {string} should show right-now summary {string}")]
fn then_status_tree_row_summary(world: &mut KanbusWorld, title: String, expected: String) {
    then_status_feed_row_summary(world, title, expected);
}

#[then(expr = "the status tree row for {string} should show status {string}")]
fn then_status_tree_row_status(world: &mut KanbusWorld, title: String, expected: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    assert_eq!(state.issues[index].status, expected);
}

fn default_type_accent_color(issue_type: &str) -> Option<&'static str> {
    match issue_type {
        "initiative" => Some("indigo"),
        "epic" => Some("purple"),
        "story" => Some("amber"),
        "bug" => Some("red"),
        "task" => Some("blue"),
        "sub-task" => Some("teal"),
        "chore" => Some("green"),
        "event" => Some("indigo"),
        _ => None,
    }
}

fn default_status_badge_color(status: &str) -> Option<&'static str> {
    match status {
        "open" | "backlog" | "todo" | "Discovery" | "deferred" => Some("gray"),
        "in_progress" | "blocked" | "copy_writing" => Some("blue"),
        "closed" | "done" => Some("green"),
        _ => None,
    }
}

#[then(expr = "the status tree row for {string} should show type accent color {string}")]
fn then_status_tree_row_type_accent_color(
    world: &mut KanbusWorld,
    title: String,
    expected: String,
) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    let issue = &state.issues[index];
    let actual = default_type_accent_color(&issue.issue_type).expect("unknown type accent color");
    assert_eq!(actual, expected);
}

#[then(expr = "the status tree row for {string} should show status color {string}")]
fn then_status_tree_row_status_color(world: &mut KanbusWorld, title: String, expected: String) {
    let state = require_console_state(world);
    let index = find_issue_by_title(state, &title).expect("issue not found");
    let issue = &state.issues[index];
    let actual = default_status_badge_color(&issue.status).expect("unknown status color");
    assert_eq!(actual, expected);
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

#[then("the now panel should not show right-now placeholder text")]
fn then_now_panel_no_right_now_placeholder(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    let issues: Vec<&ConsoleIssue> = if state.status_tree_mode {
        state
            .issues
            .iter()
            .filter(|issue| now_tree_identifiers(state).contains(&issue_tree_identifier(issue)))
            .collect()
    } else {
        status_feed_issues(now_visible_issues(state))
    };
    for issue in issues {
        assert_ne!(
            resolve_feed_summary(issue),
            RIGHT_NOW_PLACEHOLDER,
            "issue {:?} rendered right-now placeholder text",
            issue.title
        );
    }
}

#[when("I request the console now snapshot from the API")]
fn when_request_console_now_snapshot(world: &mut KanbusWorld) {
    let port = world.console_port.expect("console server is not running");
    let url = format!("http://127.0.0.1:{port}/api/now");
    let (status, body) = thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .expect("build http client");
        let response = client.get(&url).send().expect("request now snapshot");
        let status = response.status().as_u16();
        let body = response.text().expect("read now snapshot body");
        (status, body)
    })
    .join()
    .expect("now snapshot request thread");
    world.now_api_status = Some(status);
    world.now_api_response = Some(body);
}

#[then("the console now API response should succeed")]
fn then_console_now_api_response_succeeds(world: &mut KanbusWorld) {
    let status = world.now_api_status.expect("now API status missing");
    assert_eq!(
        status, 200,
        "expected now API status 200, got {}: {:?}",
        status, world.now_api_response
    );
}

#[then("the console now API response should not contain \"(no right-now summary)\"")]
fn then_console_now_api_response_has_no_placeholder(world: &mut KanbusWorld) {
    let body = world
        .now_api_response
        .as_ref()
        .expect("now API response missing");
    assert!(
        !body.contains(RIGHT_NOW_PLACEHOLDER),
        "now API response contains right-now placeholder text"
    );
}
