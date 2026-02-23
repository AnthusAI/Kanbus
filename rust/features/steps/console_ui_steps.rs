use chrono::{DateTime, Datelike, Timelike, Utc};
use chrono_tz::Tz;
use cucumber::{given, then, when};
use std::path::PathBuf;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[derive(Debug, Clone)]
pub struct ConsoleIssue {
    pub title: String,
    pub issue_type: String,
    pub parent_title: Option<String>,
    pub comments: Vec<ConsoleComment>,
    pub assignee: Option<String>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
    pub closed_at: Option<String>,
    pub project_label: String,
    pub location: String,
}

#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct ConsoleComment {
    pub author: String,
    pub created_at: String,
}

#[derive(Debug, Clone)]
pub struct ConsoleSettings {
    pub theme: String,
    pub mode: String,
    pub typeface: String,
    pub motion: String,
}

impl Default for ConsoleSettings {
    fn default() -> Self {
        Self {
            theme: "default".to_string(),
            mode: "light".to_string(),
            typeface: "sans".to_string(),
            motion: "on".to_string(),
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct ConsoleLocalStorage {
    pub selected_tab: Option<String>,
    pub settings: ConsoleSettings,
    pub selected_project_filter: Option<String>,
    pub selected_local_filter: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ConsoleState {
    pub issues: Vec<ConsoleIssue>,
    pub selected_tab: String,
    pub selected_task_title: Option<String>,
    pub settings: ConsoleSettings,
    pub time_zone: Option<String>,
    pub project_filter_options: Vec<String>,
    pub project_filter_visible: bool,
    pub local_filter_visible: bool,
    pub selected_project_filter: Option<String>,
    pub selected_local_filter: Option<String>,
}

#[given("the console is open")]
fn given_console_open(world: &mut KanbusWorld) {
    world.console_state = Some(open_console(world));
}

#[given("local storage is cleared")]
fn given_local_storage_cleared(world: &mut KanbusWorld) {
    world.console_local_storage = ConsoleLocalStorage::default();
}

#[when("the console is reloaded")]
fn when_console_reloaded(world: &mut KanbusWorld) {
    world.console_state = Some(open_console(world));
}

#[when(expr = "I switch to the {string} tab")]
fn when_switch_tab(world: &mut KanbusWorld, tab: String) {
    let state = require_console_state(world);
    if state.selected_tab == tab {
        state.selected_tab = "All".to_string();
        world.console_local_storage.selected_tab = Some("All".to_string());
        return;
    }
    state.selected_tab = tab.clone();
    world.console_local_storage.selected_tab = Some(tab);
}

#[when(expr = "I open the task {string}")]
fn when_open_task(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    state.selected_task_title = Some(title);
}

#[when(expr = "a new task issue named {string} is added")]
fn when_add_task_issue(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    state.issues.push(ConsoleIssue {
        title,
        issue_type: "task".to_string(),
        parent_title: None,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: None,
        closed_at: None,
        project_label: "kbs".to_string(),
        location: "shared".to_string(),
    });
}

#[when("I open settings")]
fn when_open_settings(world: &mut KanbusWorld) {
    require_console_state(world);
}

#[given(expr = "the console configuration sets time zone {string}")]
fn given_console_time_zone(world: &mut KanbusWorld, time_zone: String) {
    world.console_time_zone = Some(time_zone.clone());
    let state = require_console_state(world);
    state.time_zone = Some(time_zone);
}

#[given(expr = "the console has a comment from {string} at {string} on task {string}")]
fn given_console_comment(
    world: &mut KanbusWorld,
    author: String,
    timestamp: String,
    title: String,
) {
    let state = require_console_state(world);
    for issue in &mut state.issues {
        if issue.title == title {
            issue.comments.push(ConsoleComment {
                author,
                created_at: timestamp,
            });
            return;
        }
    }
    panic!("task not found: {title}");
}

#[given(expr = "the console has a task {string} created at {string} updated at {string}")]
fn given_console_task_timestamps(
    world: &mut KanbusWorld,
    title: String,
    created_at: String,
    updated_at: String,
) {
    let state = require_console_state(world);
    for issue in &mut state.issues {
        if issue.title == title {
            issue.created_at = Some(created_at);
            issue.updated_at = Some(updated_at);
            return;
        }
    }
    panic!("task not found: {title}");
}

#[given(
    expr = "the console has a closed task {string} created at {string} updated at {string} closed at {string}"
)]
fn given_console_closed_task(
    world: &mut KanbusWorld,
    title: String,
    created_at: String,
    updated_at: String,
    closed_at: String,
) {
    let state = require_console_state(world);
    for issue in &mut state.issues {
        if issue.title == title {
            issue.created_at = Some(created_at);
            issue.updated_at = Some(updated_at);
            issue.closed_at = Some(closed_at);
            return;
        }
    }
    panic!("task not found: {title}");
}

#[given(expr = "the console has an assignee {string} on task {string}")]
fn given_console_task_assignee(world: &mut KanbusWorld, assignee: String, title: String) {
    let state = require_console_state(world);
    for issue in &mut state.issues {
        if issue.title == title {
            issue.assignee = Some(assignee);
            return;
        }
    }
    panic!("task not found: {title}");
}

#[when(expr = "I set the theme to {string}")]
fn when_set_theme(world: &mut KanbusWorld, theme: String) {
    let state = require_console_state(world);
    state.settings.theme = theme.clone();
    world.console_local_storage.settings.theme = theme;
}

#[when(expr = "I set the mode to {string}")]
fn when_set_mode(world: &mut KanbusWorld, mode: String) {
    let state = require_console_state(world);
    state.settings.mode = mode.clone();
    world.console_local_storage.settings.mode = mode;
}

#[when(expr = "I set the typeface to {string}")]
fn when_set_typeface(world: &mut KanbusWorld, typeface: String) {
    let state = require_console_state(world);
    state.settings.typeface = typeface.clone();
    world.console_local_storage.settings.typeface = typeface;
}

#[when(expr = "I set motion to {string}")]
fn when_set_motion(world: &mut KanbusWorld, motion: String) {
    let state = require_console_state(world);
    state.settings.motion = motion.clone();
    world.console_local_storage.settings.motion = motion;
}

#[given("the console is open with virtual projects configured")]
fn given_console_open_with_virtual_projects(world: &mut KanbusWorld) {
    world.console_state = Some(open_console(world));
    let state = require_console_state(world);
    state.project_filter_options = vec!["kbs".to_string(), "alpha".to_string(), "beta".to_string()];
    state.project_filter_visible = true;
    // Add a default alpha shared issue so filter scenarios have data.
    state.issues.push(ConsoleIssue {
        title: "Alpha shared issue".to_string(),
        issue_type: "task".to_string(),
        parent_title: None,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: None,
        closed_at: None,
        project_label: "alpha".to_string(),
        location: "shared".to_string(),
    });
}

#[given(expr = "the console is open with virtual projects {string} and {string} configured")]
fn given_console_open_with_virtual_projects_named(
    world: &mut KanbusWorld,
    alpha: String,
    beta: String,
) {
    world.console_state = Some(open_console(world));
    let state = require_console_state(world);
    state.project_filter_options = vec!["kbs".to_string(), alpha.clone(), beta.clone()];
    state.project_filter_visible = true;
}

#[given("no virtual projects are configured")]
fn given_no_virtual_projects(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.project_filter_options = vec!["kbs".to_string()];
    state.project_filter_visible = false;
}

#[given("issues exist in multiple projects")]
fn given_issues_exist_multiple_projects(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.issues = vec![
        ConsoleIssue {
            title: "KBS issue".to_string(),
            issue_type: "task".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
        },
        ConsoleIssue {
            title: "Alpha issue".to_string(),
            issue_type: "task".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "alpha".to_string(),
            location: "shared".to_string(),
        },
        ConsoleIssue {
            title: "Beta issue".to_string(),
            issue_type: "task".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "beta".to_string(),
            location: "shared".to_string(),
        },
    ];
}

#[given("local issues exist in the current project")]
fn given_local_issues_current_project(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.issues.push(ConsoleIssue {
        title: "Local current issue".to_string(),
        issue_type: "task".to_string(),
        parent_title: None,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: None,
        closed_at: None,
        project_label: "kbs".to_string(),
        location: "local".to_string(),
    });
    state.local_filter_visible = true;
}

#[given(expr = "local issues exist in virtual project {string}")]
fn given_local_issues_virtual_project(world: &mut KanbusWorld, label: String) {
    let state = require_console_state(world);
    state.issues.push(ConsoleIssue {
        title: format!("{label} local issue"),
        issue_type: "task".to_string(),
        parent_title: None,
        comments: Vec::new(),
        assignee: None,
        created_at: None,
        updated_at: None,
        closed_at: None,
        project_label: label,
        location: "local".to_string(),
    });
    state.local_filter_visible = true;
}

#[given("no local issues exist in any project")]
fn given_no_local_issues_any_project(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    for issue in &mut state.issues {
        issue.location = "shared".to_string();
    }
    state.local_filter_visible = false;
}

#[when(expr = "I select project {string} in the project filter")]
fn when_select_project_filter(world: &mut KanbusWorld, label: String) {
    let state = require_console_state(world);
    state.selected_project_filter = Some(label.clone());
    world.console_local_storage.selected_project_filter = Some(label);
}

#[when("I select all projects in the project filter")]
fn when_select_all_projects_filter(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.selected_project_filter = None;
    world.console_local_storage.selected_project_filter = None;
}

#[when("I select \"local only\" in the local filter")]
fn when_select_local_only_filter(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.selected_local_filter = Some("local".to_string());
    world.console_local_storage.selected_local_filter = Some("local".to_string());
}

#[when("I select \"project only\" in the local filter")]
fn when_select_project_only_filter(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    state.selected_local_filter = Some("shared".to_string());
    world.console_local_storage.selected_local_filter = Some("shared".to_string());
}

#[then("the project filter should be visible in the navigation bar")]
fn then_project_filter_visible(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert!(state.project_filter_visible);
}

#[then("the project filter should not be visible")]
fn then_project_filter_not_visible(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert!(!state.project_filter_visible);
}

#[then(expr = "the project filter should list {string}")]
fn then_project_filter_should_list(world: &mut KanbusWorld, label: String) {
    let state = require_console_state(world);
    assert!(state.project_filter_options.contains(&label));
}

#[then("the local issues filter should be visible in the navigation bar")]
fn then_local_filter_visible(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert!(state.local_filter_visible);
}

#[then("the local issues filter should not be visible")]
fn then_local_filter_not_visible(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert!(!state.local_filter_visible);
}

#[then(expr = "project {string} should still be selected in the project filter")]
fn then_project_filter_still_selected(world: &mut KanbusWorld, label: String) {
    let state = require_console_state(world);
    assert_eq!(
        state.selected_project_filter.as_deref(),
        Some(label.as_str())
    );
}

#[then(expr = "I should only see issues from {string}")]
fn then_only_see_issues_from(world: &mut KanbusWorld, label: String) {
    let visible = visible_issues_with_filters(require_console_state(world));
    assert!(!visible.is_empty());
    assert!(visible.iter().all(|issue| issue.project_label == label));
}

#[then("I should see issues from all projects")]
fn then_see_issues_from_all_projects(world: &mut KanbusWorld) {
    let visible = visible_issues_with_filters(require_console_state(world));
    let labels: std::collections::HashSet<String> = visible
        .iter()
        .map(|issue| issue.project_label.clone())
        .collect();
    assert!(labels.contains("kbs"));
    assert!(labels.contains("alpha"));
    assert!(labels.contains("beta"));
}

#[then(expr = "I should only see local issues from {string}")]
fn then_only_local_issues_from(world: &mut KanbusWorld, label: String) {
    let visible = visible_issues_with_filters(require_console_state(world));
    assert!(!visible.is_empty());
    assert!(visible.iter().all(|issue| issue.project_label == label));
    assert!(visible.iter().all(|issue| issue.location == "local"));
}

#[then(expr = "I should only see shared issues from {string}")]
fn then_only_shared_issues_from(world: &mut KanbusWorld, label: String) {
    let visible = visible_issues_with_filters(require_console_state(world));
    assert!(!visible.is_empty());
    assert!(visible.iter().all(|issue| issue.project_label == label));
    assert!(visible.iter().all(|issue| issue.location == "shared"));
}

#[then(expr = "the {string} tab should be selected")]
fn then_tab_selected(world: &mut KanbusWorld, tab: String) {
    let state = require_console_state(world);
    assert_eq!(state.selected_tab, tab);
}

#[then("no view tab should be selected")]
fn then_no_tab_selected(world: &mut KanbusWorld) {
    let state = require_console_state(world);
    assert!(
        state.selected_tab.is_empty(),
        "Expected no tab to be selected, but '{}' is selected",
        state.selected_tab
    );
}

#[then(expr = "the detail panel should show issue {string}")]
fn then_detail_panel_shows_issue(world: &mut KanbusWorld, issue_title: String) {
    let state = require_console_state(world);
    assert_eq!(
        state.selected_task_title.as_deref(),
        Some(issue_title.as_str())
    );
}

#[then(expr = "I should see the issue {string}")]
fn then_should_see_issue(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    let visible_titles = visible_issue_titles(state);
    assert!(visible_titles.contains(&title));
}

#[then(expr = "I should not see the issue {string}")]
fn then_should_not_see_issue(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    let visible_titles = visible_issue_titles(state);
    assert!(!visible_titles.contains(&title));
}

#[then(expr = "I should see the sub-task {string}")]
fn then_should_see_subtask(world: &mut KanbusWorld, title: String) {
    let state = require_console_state(world);
    let selected = state.selected_task_title.clone().expect("no task selected");
    let matches: Vec<&String> = state
        .issues
        .iter()
        .filter(|issue| issue.parent_title.as_ref() == Some(&selected))
        .map(|issue| &issue.title)
        .collect();
    assert!(matches.contains(&&title));
}

#[then(expr = "the theme should be {string}")]
fn then_theme_should_be(world: &mut KanbusWorld, theme: String) {
    let state = require_console_state(world);
    assert_eq!(state.settings.theme, theme);
}

#[then(expr = "the mode should be {string}")]
fn then_mode_should_be(world: &mut KanbusWorld, mode: String) {
    let state = require_console_state(world);
    assert_eq!(state.settings.mode, mode);
}

#[then(expr = "the typeface should be {string}")]
fn then_typeface_should_be(world: &mut KanbusWorld, typeface: String) {
    let state = require_console_state(world);
    assert_eq!(state.settings.typeface, typeface);
}

#[then(expr = "the motion mode should be {string}")]
fn then_motion_should_be(world: &mut KanbusWorld, motion: String) {
    let state = require_console_state(world);
    assert_eq!(state.settings.motion, motion);
}

#[then(expr = "the comment timestamp should be {string}")]
fn then_comment_timestamp_should_be(world: &mut KanbusWorld, timestamp: String) {
    let state = require_console_state(world);
    let selected = state.selected_task_title.clone().expect("no task selected");
    for issue in &state.issues {
        if issue.title != selected {
            continue;
        }
        let comment = issue.comments.first().expect("no comments found");
        let formatted = format_timestamp(&comment.created_at, state.time_zone.as_deref());
        assert_eq!(formatted, timestamp);
        return;
    }
    panic!("selected task not found");
}

#[then(expr = "the issue metadata should include created timestamp {string}")]
fn then_issue_created_timestamp(world: &mut KanbusWorld, timestamp: String) {
    let formatted = get_selected_issue_timestamp(world, "created_at");
    assert_eq!(formatted, timestamp);
}

#[then(expr = "the issue metadata should include updated timestamp {string}")]
fn then_issue_updated_timestamp(world: &mut KanbusWorld, timestamp: String) {
    let formatted = get_selected_issue_timestamp(world, "updated_at");
    assert_eq!(formatted, timestamp);
}

#[then(expr = "the issue metadata should include closed timestamp {string}")]
fn then_issue_closed_timestamp(world: &mut KanbusWorld, timestamp: String) {
    let formatted = get_selected_issue_timestamp(world, "closed_at");
    assert_eq!(formatted, timestamp);
}

#[then(expr = "the issue metadata should include assignee {string}")]
fn then_issue_metadata_assignee(world: &mut KanbusWorld, assignee: String) {
    let issue = get_selected_issue(world);
    assert_eq!(issue.assignee.as_deref(), Some(assignee.as_str()));
}

#[when(expr = "I open the console route {string}")]
fn when_open_console_route(world: &mut KanbusWorld, route: String) {
    let state = require_console_state(world);
    if route.contains("/issues/kanbus-epic-1/kanbus-task-1") {
        state.selected_tab = String::new();
        state.selected_task_title = Some("Add structured logging".to_string());
    } else if route.contains("/all") {
        state.selected_tab = String::new();
    } else if route.contains("/issues/kanbus-epic") {
        state.selected_tab = "Epics".to_string();
        state.selected_task_title = Some("Observability overhaul".to_string());
    } else if route.contains("/epics/") || route.ends_with("/epics") {
        state.selected_tab = "Epics".to_string();
    } else if route.contains("/issues/") && !route.contains("/kanbus-") && !route.contains("/acme/")
    {
        state.selected_tab = "Issues".to_string();
    } else if route.contains("/acme/") && route.contains("/epics/") {
        state.selected_tab = "Epics".to_string();
    }
}

#[when("I view an issue card or detail that shows priority")]
fn when_view_issue_card_or_detail_with_priority(world: &mut KanbusWorld) {
    require_console_state(world);
}

#[then("the priority label should use the priority color as background")]
fn then_priority_label_uses_background(_world: &mut KanbusWorld) {
    assert_priority_pill_uses_background();
}

#[then("the priority label text should use the normal text foreground color")]
fn then_priority_label_uses_foreground_text(_world: &mut KanbusWorld) {
    assert_priority_pill_uses_foreground_text();
}

fn open_console(world: &KanbusWorld) -> ConsoleState {
    let selected_tab = world
        .console_local_storage
        .selected_tab
        .clone()
        .unwrap_or_else(|| "Epics".to_string());
    let settings = world.console_local_storage.settings.clone();
    let time_zone = world.console_time_zone.clone();
    let selected_project_filter = world.console_local_storage.selected_project_filter.clone();
    let selected_local_filter = world.console_local_storage.selected_local_filter.clone();
    ConsoleState {
        issues: default_issues(),
        selected_tab,
        selected_task_title: None,
        settings,
        time_zone,
        project_filter_options: vec!["kbs".to_string()],
        project_filter_visible: false,
        local_filter_visible: false,
        selected_project_filter,
        selected_local_filter,
    }
}

fn require_console_state(world: &mut KanbusWorld) -> &mut ConsoleState {
    world
        .console_state
        .as_mut()
        .expect("console state not initialized")
}

fn visible_issue_titles(state: &ConsoleState) -> Vec<String> {
    let issues = if state.selected_tab == "Epics" {
        state
            .issues
            .iter()
            .filter(|issue| issue.issue_type == "epic")
            .collect()
    } else if state.selected_tab == "Initiatives" {
        state
            .issues
            .iter()
            .filter(|issue| issue.issue_type == "initiative")
            .collect()
    } else if state.selected_tab == "Tasks" {
        state
            .issues
            .iter()
            .filter(|issue| issue.issue_type == "task" && issue.parent_title.is_none())
            .collect()
    } else if state.selected_tab == "All" {
        state.issues.iter().collect()
    } else {
        Vec::new()
    };
    issues.iter().map(|issue| issue.title.clone()).collect()
}

fn visible_issues_with_filters(state: &ConsoleState) -> Vec<&ConsoleIssue> {
    let mut issues: Vec<&ConsoleIssue> = state.issues.iter().collect();
    if let Some(ref filter) = state.selected_project_filter {
        issues = issues
            .into_iter()
            .filter(|issue| &issue.project_label == filter)
            .collect();
    }
    if let Some(ref local_filter) = state.selected_local_filter {
        if local_filter == "local" {
            issues = issues
                .into_iter()
                .filter(|issue| issue.location == "local")
                .collect();
        } else if local_filter == "shared" {
            issues = issues
                .into_iter()
                .filter(|issue| issue.location == "shared")
                .collect();
        }
    }
    issues
}

fn default_issues() -> Vec<ConsoleIssue> {
    vec![
        ConsoleIssue {
            title: "Observability overhaul".to_string(),
            issue_type: "epic".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
        },
        ConsoleIssue {
            title: "Increase reliability".to_string(),
            issue_type: "initiative".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
        },
        ConsoleIssue {
            title: "Add structured logging".to_string(),
            issue_type: "task".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
        },
        ConsoleIssue {
            title: "Fix crash on startup".to_string(),
            issue_type: "task".to_string(),
            parent_title: None,
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
        },
        ConsoleIssue {
            title: "Wire logger middleware".to_string(),
            issue_type: "task".to_string(),
            parent_title: Some("Add structured logging".to_string()),
            comments: Vec::new(),
            assignee: None,
            created_at: None,
            updated_at: None,
            closed_at: None,
            project_label: "kbs".to_string(),
            location: "shared".to_string(),
        },
    ]
}

fn get_selected_issue(world: &mut KanbusWorld) -> &mut ConsoleIssue {
    let state = require_console_state(world);
    let selected = state.selected_task_title.clone().expect("no task selected");
    state
        .issues
        .iter_mut()
        .find(|issue| issue.title == selected)
        .expect("selected task not found")
}

fn get_selected_issue_timestamp(world: &mut KanbusWorld, field: &str) -> String {
    let state = require_console_state(world);
    let selected = state.selected_task_title.clone().expect("no task selected");
    let issue = state
        .issues
        .iter()
        .find(|issue| issue.title == selected)
        .expect("selected task not found");
    let raw = match field {
        "created_at" => issue.created_at.as_deref(),
        "updated_at" => issue.updated_at.as_deref(),
        "closed_at" => issue.closed_at.as_deref(),
        _ => None,
    }
    .expect("timestamp not set");
    format_timestamp(raw, state.time_zone.as_deref())
}

fn format_timestamp(value: &str, time_zone: Option<&str>) -> String {
    let parsed = DateTime::parse_from_rfc3339(value).unwrap_or_else(|_| {
        panic!("invalid timestamp: {value}");
    });
    let utc = parsed.with_timezone(&Utc);
    let resolved_tz = time_zone
        .and_then(|tz| tz.parse::<Tz>().ok())
        .unwrap_or(chrono_tz::UTC);
    let localized = utc.with_timezone(&resolved_tz);
    let hour24 = localized.hour();
    let (hour, period) = if hour24 == 0 {
        (12, "AM")
    } else if hour24 < 12 {
        (hour24, "AM")
    } else if hour24 == 12 {
        (12, "PM")
    } else {
        (hour24 - 12, "PM")
    };
    let tzname = localized.format("%Z").to_string();
    format!(
        "{}, {} {}, {} {}:{:02} {} {}",
        localized.format("%A"),
        localized.format("%B"),
        localized.day(),
        localized.year(),
        hour,
        localized.minute(),
        period,
        tzname
    )
}

fn console_app_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("apps")
        .join("console")
}

fn assert_priority_pill_uses_background() {
    let root = console_app_root();
    let globals_css = std::fs::read_to_string(root.join("src").join("styles").join("globals.css"))
        .expect("read globals.css");
    if !globals_css.contains("background") || !globals_css.contains("--issue-priority-bg") {
        panic!("priority label must use background with --issue-priority-bg in globals.css");
    }
    let issue_colors =
        std::fs::read_to_string(root.join("src").join("utils").join("issue-colors.ts"))
            .expect("read issue-colors.ts");
    if !issue_colors.contains("issue-priority-bg-light")
        || !issue_colors.contains("issue-priority-bg-dark")
    {
        panic!("issue-colors.ts must set --issue-priority-bg-light and --issue-priority-bg-dark");
    }
}

fn assert_priority_pill_uses_foreground_text() {
    let root = console_app_root();
    let globals_css = std::fs::read_to_string(root.join("src").join("styles").join("globals.css"))
        .expect("read globals.css");
    let start = globals_css.find(".issue-accent-priority");
    let start = start.expect(".issue-accent-priority not found in globals.css");
    let end = std::cmp::min(start + 600, globals_css.len());
    let block = &globals_css[start..end];
    if !block.contains("var(--text-foreground)") || !block.contains("color") {
        panic!(".issue-accent-priority must set color to var(--text-foreground)");
    }
}
