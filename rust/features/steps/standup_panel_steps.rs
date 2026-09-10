use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::PathBuf;
use std::thread;

use chrono::{DateTime, Utc};
use cucumber::{given, then, when};
use reqwest::blocking::Client;
use serde_json::json;

use chrono_tz::UTC;
use kanbus::models::IssueData;
use kanbus::standup::{
    build_standup_report, collect_right_now_texts, format_standup_text, load_standup_configuration,
    resolve_standup_profile, MEETING_SCRIPT_PROFILE,
};
use kanbus::standup_command::STANDUP_DEFAULT_STATUS_FILTER;
use kanbus::standup_rollup::resolve_standup_rollup;
use kanbus::standup_window::{StandupWindowSettings, DEFAULT_STANDUP_LOOKBACK, ROLLING_WINDOW};

use crate::step_definitions::console_ui_steps::{ConsoleIssue, ConsoleState};
use crate::step_definitions::initialization_steps::KanbusWorld;

#[derive(Debug, Clone, Default)]
pub struct StandupPanelState {
    pub is_open: bool,
    pub profile: String,
    pub is_generating: bool,
    pub error: Option<String>,
    pub report_text: Option<String>,
    pub section_names: Vec<String>,
    pub clipboard: Option<String>,
    pub generation_should_fail: bool,
}

fn ensure_standup_state(world: &mut KanbusWorld) -> &mut StandupPanelState {
    if world.console_standup_state.is_none() {
        world.console_standup_state = Some(StandupPanelState {
            profile: MEETING_SCRIPT_PROFILE.to_string(),
            ..StandupPanelState::default()
        });
    }
    world.console_standup_state.as_mut().unwrap()
}

fn require_console_state(world: &mut KanbusWorld) -> &mut ConsoleState {
    world
        .console_state
        .as_mut()
        .expect("console state not initialized")
}

fn parse_console_timestamp(value: Option<&str>) -> DateTime<Utc> {
    match value {
        Some(raw) => DateTime::parse_from_rfc3339(raw)
            .map(|parsed| parsed.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
        None => Utc::now(),
    }
}

fn standup_statuses() -> Vec<String> {
    STANDUP_DEFAULT_STATUS_FILTER
        .split(',')
        .map(|status| status.trim().to_string())
        .collect()
}

fn console_issue_to_issue_data(issue: &ConsoleIssue) -> IssueData {
    let timestamp = parse_console_timestamp(issue.updated_at.as_deref());
    IssueData {
        identifier: issue
            .identifier
            .clone()
            .unwrap_or_else(|| issue.title.clone()),
        title: issue.title.clone(),
        description: String::new(),
        issue_type: issue.issue_type.clone(),
        status: issue.status.clone(),
        priority: issue.priority,
        assignee: issue.assignee.clone(),
        creator: Some("agent".to_string()),
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: issue
            .closed_at
            .as_deref()
            .map(|value| parse_console_timestamp(Some(value))),
        right_now_summary: issue.right_now_summary.clone(),
        right_now_updated_at: issue.right_now_summary.as_ref().map(|_| timestamp),
        custom: BTreeMap::new(),
        agent: None,
    }
}

fn standup_fact_feed_issues(console_state: &ConsoleState) -> Vec<IssueData> {
    let allowed = standup_statuses();
    let mut issues = console_state
        .issues
        .iter()
        .filter(|issue| allowed.iter().any(|status| status == &issue.status))
        .map(console_issue_to_issue_data)
        .collect::<Vec<_>>();
    issues.sort_by(|left, right| {
        right
            .updated_at
            .cmp(&left.updated_at)
            .then_with(|| left.identifier.cmp(&right.identifier))
    });
    issues
}

fn generate_from_console_state(
    console_state: &ConsoleState,
    profile_name: &str,
    root: &std::path::Path,
) -> Result<(String, Vec<String>), String> {
    let profile = resolve_standup_profile(Some(profile_name)).map_err(|error| error.to_string())?;
    let issues = standup_fact_feed_issues(console_state);
    let right_now_texts = collect_right_now_texts(&issues).map_err(|error| error.to_string())?;
    let window_settings = StandupWindowSettings {
        window: ROLLING_WINDOW.to_string(),
        lookback: DEFAULT_STANDUP_LOOKBACK.to_string(),
        lookback_hours: 24,
        skip_weekends: false,
        timezone: UTC,
    };
    let configuration = load_standup_configuration(root).map_err(|error| error.to_string())?;
    let rollup_settings =
        resolve_standup_rollup(None, &configuration, false).map_err(|error| error.to_string())?;
    let report = build_standup_report(
        root,
        &profile,
        &issues,
        &right_now_texts,
        &HashMap::new(),
        Utc::now(),
        &window_settings,
        false,
        &configuration,
        &rollup_settings,
    )
    .map_err(|error| error.to_string())?;
    let section_names = report
        .sections
        .iter()
        .map(|section| section.name.clone())
        .collect();
    Ok((format_standup_text(&report), section_names))
}

fn console_app_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("apps")
        .join("console")
}

fn assert_standup_drawer_portals_to_body() {
    let source = fs::read_to_string(console_app_root().join("src/components/StandupDrawer.tsx"))
        .expect("read StandupDrawer.tsx");
    assert!(
        source.contains("createPortal") && source.contains("document.body"),
        "StandupDrawer must render via createPortal to document.body"
    );
}

#[given(regex = r"^the browser viewport is (?P<width>\d+) by (?P<height>\d+)$")]
fn given_browser_viewport(world: &mut KanbusWorld, width: u32, height: u32) {
    world.console_viewport = Some((width, height));
}

#[given("standup generation is configured to fail")]
fn given_standup_generation_configured_to_fail(world: &mut KanbusWorld) {
    ensure_standup_state(world).generation_should_fail = true;
}

#[when("I open the standup drawer")]
fn when_open_standup_drawer(world: &mut KanbusWorld) {
    ensure_standup_state(world).is_open = true;
}

#[when(regex = r#"^I select the standup profile "(?P<profile>[^"]+)"$"#)]
fn when_select_standup_profile(world: &mut KanbusWorld, profile: String) {
    ensure_standup_state(world).profile = profile;
}

#[when("I generate the standup report")]
fn when_generate_standup_report(world: &mut KanbusWorld) {
    let generation_should_fail = ensure_standup_state(world).generation_should_fail;
    let profile = ensure_standup_state(world).profile.clone();
    let generated = if generation_should_fail {
        Err("standup generation failed".to_string())
    } else {
        let root = world.working_directory.clone().unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .expect("repository root")
                .to_path_buf()
        });
        let console_state = require_console_state(world);
        generate_from_console_state(console_state, &profile, &root)
    };
    let standup = ensure_standup_state(world);
    standup.is_generating = true;
    standup.error = None;
    standup.report_text = None;
    standup.section_names.clear();
    match generated {
        Ok((report_text, section_names)) => {
            standup.report_text = Some(report_text);
            standup.section_names = section_names;
            standup.is_generating = false;
        }
        Err(message) => {
            standup.error = Some(message);
            standup.is_generating = false;
        }
    }
}

#[when("I copy the standup report")]
fn when_copy_standup_report(world: &mut KanbusWorld) {
    let standup = ensure_standup_state(world);
    let report_text = standup
        .report_text
        .clone()
        .expect("no standup report to copy");
    standup.clipboard = Some(report_text);
}

#[when(
    regex = r#"^I request a standup report from the console API with profile "(?P<profile>[^"]+)"$"#
)]
fn when_request_standup_from_console_api(world: &mut KanbusWorld, profile: String) {
    let port = world.console_port.expect("console server is not running");
    let url = format!("http://127.0.0.1:{port}/api/standup");
    let payload = json!({ "profile": profile });
    let (status, body) = thread::spawn(move || {
        let client = Client::new();
        let response = client
            .post(url)
            .json(&payload)
            .send()
            .expect("standup request");
        let status = response.status().as_u16();
        let body = response.text().expect("standup response body");
        (status, body)
    })
    .join()
    .expect("standup request thread");
    world.standup_api_status = Some(status);
    world.standup_api_response = Some(serde_json::from_str(&body).expect("parse standup json"));
}

#[then("the standup drawer should be in the viewport")]
fn then_standup_drawer_in_viewport(world: &mut KanbusWorld) {
    let standup = ensure_standup_state(world);
    assert!(standup.is_open, "expected standup drawer to be open");
    assert_standup_drawer_portals_to_body();
}

#[then("the standup profile select should be in the viewport")]
fn then_standup_profile_select_in_viewport(_world: &mut KanbusWorld) {
    assert_standup_drawer_portals_to_body();
}

#[then("the standup window select should be in the viewport")]
fn then_standup_window_select_in_viewport(_world: &mut KanbusWorld) {
    assert_standup_drawer_portals_to_body();
}

#[then("the standup lookback input should be in the viewport")]
fn then_standup_lookback_input_in_viewport(_world: &mut KanbusWorld) {
    assert_standup_drawer_portals_to_body();
}

#[then("the standup skip weekends checkbox should be in the viewport")]
fn then_standup_skip_weekends_checkbox_in_viewport(_world: &mut KanbusWorld) {
    assert_standup_drawer_portals_to_body();
}

#[then("the now standup button should be visible")]
fn then_now_standup_button_visible(world: &mut KanbusWorld) {
    let console_state = require_console_state(world);
    assert_eq!(
        console_state.panel_mode, "now",
        "expected Now panel to be active"
    );
    let source =
        fs::read_to_string(console_app_root().join("src/components/CurrentStatusPanel.tsx"))
            .expect("read CurrentStatusPanel.tsx");
    assert!(
        source.contains("data-testid=\"now-standup-button\""),
        "CurrentStatusPanel is missing now-standup-button"
    );
}

#[then(regex = r#"^the standup drawer should show section "(?P<section_name>[^"]+)"$"#)]
fn then_standup_drawer_shows_section(world: &mut KanbusWorld, section_name: String) {
    let standup = ensure_standup_state(world);
    assert!(
        standup
            .section_names
            .iter()
            .any(|name| name == &section_name),
        "expected section {}, got {:?}",
        section_name,
        standup.section_names
    );
}

#[then(regex = r#"^the standup drawer result should mention "(?P<text>[^"]+)"$"#)]
fn then_standup_drawer_result_mentions(world: &mut KanbusWorld, text: String) {
    let standup = ensure_standup_state(world);
    let report_text = standup.report_text.as_deref().unwrap_or("");
    assert!(
        report_text.contains(&text),
        "expected standup result to mention {}",
        text
    );
}

#[then(regex = r#"^the standup drawer should show error "(?P<message>[^"]+)"$"#)]
fn then_standup_drawer_shows_error(world: &mut KanbusWorld, message: String) {
    let standup = ensure_standup_state(world);
    assert_eq!(standup.error.as_deref(), Some(message.as_str()));
}

#[then("the standup drawer should not show a success result")]
fn then_standup_drawer_has_no_success_result(world: &mut KanbusWorld) {
    let standup = ensure_standup_state(world);
    assert!(
        standup.report_text.is_none(),
        "expected no standup success result"
    );
}

#[then(regex = r#"^the standup clipboard should contain "(?P<text>[^"]+)"$"#)]
fn then_standup_clipboard_contains(world: &mut KanbusWorld, text: String) {
    let standup = ensure_standup_state(world);
    let clipboard = standup.clipboard.as_deref().unwrap_or("");
    assert!(
        clipboard.contains(&text),
        "expected clipboard to contain {}",
        text
    );
}

#[then(regex = r#"^the standup API response should have profile "(?P<profile>[^"]+)"$"#)]
fn then_standup_api_response_profile(world: &mut KanbusWorld, profile: String) {
    assert_eq!(world.standup_api_status, Some(200));
    let response = world
        .standup_api_response
        .as_ref()
        .expect("standup api response");
    assert_eq!(
        response.get("profile").and_then(|value| value.as_str()),
        Some(profile.as_str())
    );
}

#[then(regex = r#"^the standup API response should include section "(?P<section_name>[^"]+)"$"#)]
fn then_standup_api_response_includes_section(world: &mut KanbusWorld, section_name: String) {
    let response = world
        .standup_api_response
        .as_ref()
        .expect("standup api response");
    let sections = response
        .get("sections")
        .and_then(|value| value.as_array())
        .expect("sections array");
    let names = sections
        .iter()
        .filter_map(|section| section.get("name").and_then(|name| name.as_str()))
        .collect::<Vec<_>>();
    assert!(
        names.iter().any(|name| *name == section_name),
        "expected section {}, got {:?}",
        section_name,
        names
    );
}

#[then(regex = r#"^the standup API response text should mention "(?P<text>[^"]+)"$"#)]
fn then_standup_api_response_text_mentions(world: &mut KanbusWorld, text: String) {
    let response = world
        .standup_api_response
        .as_ref()
        .expect("standup api response");
    let report_text = response
        .get("text")
        .and_then(|value| value.as_str())
        .unwrap_or("");
    assert!(
        report_text.contains(&text),
        "expected API text to mention {}",
        text
    );
}
