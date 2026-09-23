//! On-demand standup report generation.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use chrono::{DateTime, Duration, Utc};
use regex::Regex;
use serde::Serialize;
use serde_json::Value;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueData, ProjectConfiguration};
use crate::right_now::{
    ensure_right_now_summaries, is_persisted_mock_right_now_summary,
    require_display_right_now_summary,
};
use crate::standup_rollup::{
    build_close_out_bullets, close_out_issue_identifiers, ensure_yesterday_bullets,
    roll_up_active_bullets, StandupRollupSettings, CLOSE_OUT_SECTION, ROLLUP_FLAT,
};
use crate::standup_window::{
    is_on_completed_calendar_day, parse_standup_lookback_hours, start_of_report_calendar_day,
    StandupWindowSettings, CALENDAR_WINDOW,
};

pub const MEETING_SCRIPT_PROFILE: &str = "meeting-script";
pub const DIRECTOR_BRIEF_PROFILE: &str = "director-brief";
pub const DEFAULT_STANDUP_LOOKBACK_HOURS: u32 = 24;
const MAX_STANDUP_BULLET_LENGTH: usize = 120;
const FIRST_PERSON_INTRO: &str = "Here is my standup update.";
const EXECUTIVE_BRIEF_INTRO: &str = "Executive brief for stakeholders.";

static STANDUP_PROFILES: [&str; 2] = [MEETING_SCRIPT_PROFILE, DIRECTOR_BRIEF_PROFILE];
static DONE_STATUSES: [&str; 2] = ["closed", "done"];

/// Named standup report section with bullet lines.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StandupSection {
    /// Section heading.
    pub name: String,
    /// Bullet text lines without leading markers.
    pub bullets: Vec<String>,
}

/// Structured standup report payload.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StandupReport {
    /// Standup profile identifier.
    pub profile: String,
    /// Ordered report sections.
    pub sections: Vec<StandupSection>,
    /// Fact-feed issue identifiers in display order.
    pub source_issues: Vec<String>,
    /// Right-now summary text keyed by issue identifier.
    pub right_now_texts: HashMap<String, String>,
}

#[derive(Serialize)]
struct StandupJsonSection<'report> {
    name: &'report str,
    bullets: &'report [String],
}

#[derive(Serialize)]
struct StandupJsonPayload<'report> {
    profile: &'report str,
    sections: Vec<StandupJsonSection<'report>>,
    source_issues: &'report [String],
    right_now_texts: &'report HashMap<String, String>,
}

/// Resolve a standup profile name to a canonical identifier.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when the profile name is unknown.
pub fn resolve_standup_profile(profile_name: Option<&str>) -> Result<String, KanbusError> {
    let resolved = profile_name.unwrap_or(MEETING_SCRIPT_PROFILE);
    if !STANDUP_PROFILES.contains(&resolved) {
        return Err(KanbusError::IssueOperation(format!(
            "unknown standup profile: {resolved}"
        )));
    }
    Ok(resolved.to_string())
}

/// Load project configuration for standup generation.
///
/// # Errors
///
/// Returns `KanbusError` when configuration cannot be loaded.
pub fn load_standup_configuration(root: &Path) -> Result<ProjectConfiguration, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    load_project_configuration(&configuration_path)
}

/// Return configured standup lookback hours.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when lookback is invalid.
pub fn resolve_standup_lookback_hours(
    configuration: &ProjectConfiguration,
) -> Result<u32, KanbusError> {
    parse_standup_lookback_hours(&configuration.standup.lookback)
}

/// Load event history records for an issue.
pub fn load_issue_event_records(root: &Path, issue_identifier: &str) -> Vec<Value> {
    let lookup = match load_issue_from_project(root, issue_identifier) {
        Ok(lookup) => lookup,
        Err(_) => return Vec::new(),
    };
    let project_dir = lookup.project_dir;
    let mut events_dirs = vec![project_dir.join("events")];
    let local_events = project_dir
        .parent()
        .map(|parent| parent.join("project-local").join("events"))
        .unwrap_or_else(|| Path::new("").join("project-local").join("events"));
    if local_events.is_dir() {
        events_dirs.push(local_events);
    }
    let mut records = Vec::new();
    for events_dir in events_dirs {
        if !events_dir.is_dir() {
            continue;
        }
        let entries = match fs::read_dir(&events_dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let contents = match fs::read_to_string(&path) {
                Ok(contents) => contents,
                Err(_) => continue,
            };
            let payload: Value = match serde_json::from_str(&contents) {
                Ok(payload) => payload,
                Err(_) => continue,
            };
            if payload.get("issue_id").and_then(Value::as_str) == Some(issue_identifier) {
                records.push(payload);
            }
        }
    }
    records
}

fn parse_rfc3339_timestamp(value: Option<&DateTime<Utc>>) -> Option<DateTime<Utc>> {
    value.copied()
}

fn parse_rfc3339_timestamp_from_value(value: Option<&Value>) -> Option<DateTime<Utc>> {
    let raw = value?;
    if let Some(text) = raw.as_str() {
        let normalized = text.replace('Z', "+00:00");
        return DateTime::parse_from_rfc3339(&normalized)
            .ok()
            .map(|timestamp| timestamp.with_timezone(&Utc));
    }
    None
}

/// Return whether a timestamp falls within the lookback window.
pub fn is_within_lookback(
    timestamp: Option<&DateTime<Utc>>,
    report_time: DateTime<Utc>,
    lookback_hours: u32,
) -> bool {
    let parsed = match parse_rfc3339_timestamp(timestamp) {
        Some(parsed) => parsed,
        None => return false,
    };
    let window_start = report_time - Duration::hours(i64::from(lookback_hours));
    parsed >= window_start && parsed <= report_time
}

pub(crate) fn is_event_within_lookback(
    event: &Value,
    report_time: DateTime<Utc>,
    lookback_hours: u32,
) -> bool {
    is_within_lookback_from_value(event.get("occurred_at"), report_time, lookback_hours)
}

fn is_within_lookback_from_value(
    timestamp: Option<&Value>,
    report_time: DateTime<Utc>,
    lookback_hours: u32,
) -> bool {
    let parsed = match parse_rfc3339_timestamp_from_value(timestamp) {
        Some(parsed) => parsed,
        None => return false,
    };
    let window_start = report_time - Duration::hours(i64::from(lookback_hours));
    parsed >= window_start && parsed <= report_time
}

/// Return whether an issue had a qualifying state transition in lookback.
pub fn had_state_transition_within_lookback(
    events: &[Value],
    target_statuses: &HashSet<String>,
    report_time: DateTime<Utc>,
    lookback_hours: u32,
) -> bool {
    for event in events {
        if event.get("event_type").and_then(Value::as_str) != Some("state_transition") {
            continue;
        }
        let payload = event.get("payload").and_then(Value::as_object);
        let Some(payload) = payload else {
            continue;
        };
        let to_status = payload.get("to_status").and_then(Value::as_str);
        let Some(to_status) = to_status else {
            continue;
        };
        if !target_statuses.contains(to_status) {
            continue;
        }
        if is_event_within_lookback(event, report_time, lookback_hours) {
            return true;
        }
    }
    false
}

fn done_statuses() -> HashSet<String> {
    DONE_STATUSES
        .iter()
        .map(|status| (*status).to_string())
        .collect()
}

/// Return whether an issue belongs in the Yesterday section.
pub fn qualifies_for_yesterday(
    issue: &IssueData,
    events: &[Value],
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    if window_settings.window == CALENDAR_WINDOW {
        if is_on_completed_calendar_day(issue.closed_at.as_ref(), report_time, window_settings) {
            return true;
        }
        for event in events {
            if event.get("event_type").and_then(Value::as_str) != Some("state_transition") {
                continue;
            }
            let payload = event.get("payload").and_then(Value::as_object);
            let Some(payload) = payload else {
                continue;
            };
            let to_status = payload.get("to_status").and_then(Value::as_str);
            if !done_statuses().contains(to_status.unwrap_or("")) {
                continue;
            }
            if is_event_on_completed_calendar_day(event, report_time, window_settings) {
                return true;
            }
        }
        return false;
    }
    let lookback_hours = window_settings.lookback_hours;
    if is_within_lookback(issue.closed_at.as_ref(), report_time, lookback_hours) {
        return true;
    }
    had_state_transition_within_lookback(events, &done_statuses(), report_time, lookback_hours)
}

fn is_event_on_completed_calendar_day(
    event: &Value,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    let timestamp = parse_rfc3339_timestamp_from_value(event.get("occurred_at"));
    is_on_completed_calendar_day(timestamp.as_ref(), report_time, window_settings)
}

/// Return whether an in-progress issue is stale relative to lookback.
pub fn is_stale_in_progress(
    issue: &IssueData,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    if issue.status != "in_progress" {
        return false;
    }
    if window_settings.window == CALENDAR_WINDOW {
        let report_day_start = start_of_report_calendar_day(report_time, window_settings);
        return issue.updated_at < report_day_start;
    }
    !is_within_lookback(
        Some(&issue.updated_at),
        report_time,
        window_settings.lookback_hours,
    )
}

/// Return whether an issue belongs in the Momentum section.
pub fn qualifies_for_momentum(
    issue: &IssueData,
    events: &[Value],
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    let lookback_hours = window_settings.lookback_hours;
    let in_progress = HashSet::from([String::from("in_progress")]);
    if had_state_transition_within_lookback(events, &in_progress, report_time, lookback_hours) {
        return true;
    }
    if had_state_transition_within_lookback(events, &done_statuses(), report_time, lookback_hours) {
        return true;
    }
    if done_statuses().contains(&issue.status)
        && is_within_lookback(issue.closed_at.as_ref(), report_time, lookback_hours)
    {
        return true;
    }
    issue.status == "in_progress"
        && is_within_lookback(Some(&issue.updated_at), report_time, lookback_hours)
}

pub(crate) fn truncate_bullet(text: &str) -> String {
    truncate_bullet_with_max_length(text, MAX_STANDUP_BULLET_LENGTH)
}

fn truncate_bullet_with_max_length(text: &str, max_length: usize) -> String {
    if text.chars().count() <= max_length {
        return text.to_string();
    }
    let truncated: String = text.chars().take(max_length.saturating_sub(3)).collect();
    format!("{}...", truncated.trim_end())
}

fn derive_blocked_question(summary: &str) -> String {
    let lowered = summary.to_lowercase();
    if lowered.contains("blocked on") {
        let fragment = summary
            .split("Blocked on")
            .nth(1)
            .unwrap_or(summary)
            .trim()
            .trim_end_matches('.');
        return truncate_bullet(&format!("What is the status of {fragment}?"));
    }
    truncate_bullet(&format!(
        "What is blocking progress on {}? ",
        summary.trim_end_matches('.')
    ))
}

fn derive_stale_question(identifier: &str) -> String {
    truncate_bullet(&format!("Why is {identifier} still in progress?"))
}

/// Build meeting-script profile sections from fact-feed issues.
#[allow(clippy::too_many_arguments)]
pub fn build_meeting_script_sections(
    root: &Path,
    issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    events_by_issue: &HashMap<String, Vec<Value>>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
    configuration: &ProjectConfiguration,
    rollup_settings: &StandupRollupSettings,
    explicit_scope: bool,
) -> Result<Vec<StandupSection>, KanbusError> {
    let mut yesterday_identifiers = HashSet::new();
    let mut yesterday_bullets = Vec::new();
    let mut blocker_bullets = Vec::new();
    let mut question_bullets = Vec::new();

    for issue in issues {
        let events = events_by_issue
            .get(&issue.identifier)
            .map(Vec::as_slice)
            .unwrap_or(&[]);
        let summary = right_now_texts
            .get(&issue.identifier)
            .map(String::as_str)
            .unwrap_or("");
        if qualifies_for_yesterday(issue, events, report_time, window_settings) {
            yesterday_identifiers.insert(issue.identifier.clone());
            yesterday_bullets.push(truncate_bullet(summary));
        }
        if issue.status == "blocked" {
            blocker_bullets.push(truncate_bullet(&format!("{}: {summary}", issue.identifier)));
            question_bullets.push(derive_blocked_question(summary));
        }
    }

    let mut today_issues = Vec::new();
    for issue in issues {
        if yesterday_identifiers.contains(&issue.identifier) {
            continue;
        }
        let active_statuses: &[&str] = if explicit_scope {
            &["in_progress", "blocked", "open"]
        } else {
            &["in_progress", "blocked"]
        };
        if active_statuses.contains(&issue.status.as_str()) {
            today_issues.push(issue.clone());
        }
    }

    let today_bullets = roll_up_active_bullets(
        root,
        &today_issues,
        right_now_texts,
        configuration,
        rollup_settings,
        false,
    )?;

    let close_out_bullets = build_close_out_bullets(
        issues,
        right_now_texts,
        events_by_issue,
        report_time,
        window_settings,
    );
    let close_out_identifiers = close_out_issue_identifiers(&close_out_bullets);
    for issue in issues {
        if close_out_identifiers.contains(&issue.identifier) {
            continue;
        }
        if issue.status == "in_progress"
            && is_stale_in_progress(issue, report_time, window_settings)
        {
            question_bullets.push(derive_stale_question(&issue.identifier));
        }
    }

    Ok(vec![
        StandupSection {
            name: String::from("Yesterday"),
            bullets: ensure_yesterday_bullets(&yesterday_bullets),
        },
        StandupSection {
            name: String::from("Today"),
            bullets: today_bullets,
        },
        StandupSection {
            name: String::from(CLOSE_OUT_SECTION),
            bullets: close_out_bullets,
        },
        StandupSection {
            name: String::from("Blockers"),
            bullets: blocker_bullets,
        },
        StandupSection {
            name: String::from("Likely questions"),
            bullets: question_bullets,
        },
    ])
}

/// Build director-brief profile sections from fact-feed issues.
#[allow(clippy::too_many_arguments)]
pub fn build_director_brief_sections(
    root: &Path,
    issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    events_by_issue: &HashMap<String, Vec<Value>>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
    configuration: &ProjectConfiguration,
    rollup_settings: &StandupRollupSettings,
) -> Result<Vec<StandupSection>, KanbusError> {
    let in_progress_count = issues
        .iter()
        .filter(|issue| issue.status == "in_progress")
        .count();
    let blocked_count = issues
        .iter()
        .filter(|issue| issue.status == "blocked")
        .count();
    let blocked_suffix = if blocked_count == 1 { "" } else { "s" };
    let health_bullets = vec![format!(
        "{in_progress_count} in-progress issues, {blocked_count} blocked issue{blocked_suffix}"
    )];

    let mut risk_bullets = Vec::new();
    let mut blocker_bullets = Vec::new();

    for issue in issues {
        let summary = right_now_texts
            .get(&issue.identifier)
            .map(String::as_str)
            .unwrap_or("");
        if issue.status == "blocked" {
            risk_bullets.push(truncate_bullet(&issue.identifier));
            blocker_bullets.push(truncate_bullet(&format!("{}: {summary}", issue.identifier)));
        } else if is_stale_in_progress(issue, report_time, window_settings) {
            risk_bullets.push(truncate_bullet(&format!("{}: {summary}", issue.identifier)));
        }
    }

    let momentum_issues = issues
        .iter()
        .filter(|issue| {
            let events = events_by_issue
                .get(&issue.identifier)
                .map(Vec::as_slice)
                .unwrap_or(&[]);
            qualifies_for_momentum(issue, events, report_time, window_settings)
        })
        .cloned()
        .collect::<Vec<_>>();
    let prefix_issue_identifiers = rollup_settings.mode == ROLLUP_FLAT;
    let momentum_bullets = roll_up_active_bullets(
        root,
        &momentum_issues,
        right_now_texts,
        configuration,
        rollup_settings,
        prefix_issue_identifiers,
    )?;

    let close_out_bullets = build_close_out_bullets(
        issues,
        right_now_texts,
        events_by_issue,
        report_time,
        window_settings,
    );

    Ok(vec![
        StandupSection {
            name: String::from("Health"),
            bullets: health_bullets,
        },
        StandupSection {
            name: String::from("Momentum"),
            bullets: momentum_bullets,
        },
        StandupSection {
            name: String::from("Risks"),
            bullets: risk_bullets,
        },
        StandupSection {
            name: String::from(CLOSE_OUT_SECTION),
            bullets: close_out_bullets,
        },
        StandupSection {
            name: String::from("Blockers"),
            bullets: blocker_bullets,
        },
    ])
}

/// Build a structured standup report for the requested profile.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when rollup summarization fails fail-closed.
#[allow(clippy::too_many_arguments)]
pub fn build_standup_report(
    root: &Path,
    profile: &str,
    issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    events_by_issue: &HashMap<String, Vec<Value>>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
    explicit_scope: bool,
    configuration: &ProjectConfiguration,
    rollup_settings: &StandupRollupSettings,
) -> Result<StandupReport, KanbusError> {
    let sections = if profile == DIRECTOR_BRIEF_PROFILE {
        build_director_brief_sections(
            root,
            issues,
            right_now_texts,
            events_by_issue,
            report_time,
            window_settings,
            configuration,
            rollup_settings,
        )?
    } else {
        build_meeting_script_sections(
            root,
            issues,
            right_now_texts,
            events_by_issue,
            report_time,
            window_settings,
            configuration,
            rollup_settings,
            explicit_scope,
        )?
    };
    Ok(StandupReport {
        profile: profile.to_string(),
        sections,
        source_issues: issues
            .iter()
            .map(|issue| issue.identifier.clone())
            .collect(),
        right_now_texts: right_now_texts.clone(),
    })
}

/// Serialize a standup report as JSON.
///
/// # Errors
///
/// Returns `KanbusError::Io` when serialization fails.
pub fn format_standup_json(report: &StandupReport) -> Result<String, KanbusError> {
    let sections = report
        .sections
        .iter()
        .map(|section| StandupJsonSection {
            name: section.name.as_str(),
            bullets: section.bullets.as_slice(),
        })
        .collect();
    let payload = StandupJsonPayload {
        profile: report.profile.as_str(),
        sections,
        source_issues: report.source_issues.as_slice(),
        right_now_texts: &report.right_now_texts,
    };
    let output = serde_json::to_string_pretty(&payload)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(format!("{output}\n"))
}

/// Render a standup report for terminal output.
pub fn format_standup_text(report: &StandupReport) -> String {
    let intro = if report.profile == DIRECTOR_BRIEF_PROFILE {
        EXECUTIVE_BRIEF_INTRO
    } else {
        FIRST_PERSON_INTRO
    };
    let mut lines = vec![format!("Standup ({})", report.profile), intro.to_string()];
    for section in &report.sections {
        lines.push(String::new());
        lines.push(section.name.clone());
        for bullet in &section.bullets {
            lines.push(format!("- {bullet}"));
        }
    }
    lines.push(String::new());
    lines.join("\n")
}

/// Return right-now summary text suitable for standup report output.
///
/// # Errors
///
/// Returns `KanbusError` when the summary is missing or invalid.
pub fn standup_display_summary(issue: &IssueData) -> Result<String, KanbusError> {
    let summary = require_display_right_now_summary(issue)?;
    if is_persisted_mock_right_now_summary(&summary, &issue.identifier) {
        return Ok(truncate_bullet(&format!("Progress on {}.", issue.title)));
    }
    Ok(summary)
}

/// Collect right-now summary text for fact-feed issues.
///
/// # Errors
///
/// Returns `KanbusError` when a required summary is missing.
pub fn collect_right_now_texts(
    issues: &[IssueData],
) -> Result<HashMap<String, String>, KanbusError> {
    let mut texts = HashMap::new();
    for issue in issues {
        texts.insert(issue.identifier.clone(), standup_display_summary(issue)?);
    }
    Ok(texts)
}

/// Ensure right-now summaries exist for standup fact-feed issues.
///
/// # Errors
///
/// Returns `KanbusError` when fail-closed summary generation cannot run.
pub fn ensure_standup_summaries(
    root: &Path,
    issues: &[IssueData],
) -> Result<Vec<IssueData>, KanbusError> {
    if issues.is_empty() {
        return Ok(Vec::new());
    }
    let identifiers: Vec<String> = issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    ensure_right_now_summaries(root, &identifiers, true)?;
    let mut reloaded = Vec::new();
    for issue in issues {
        match load_issue_from_project(root, &issue.identifier) {
            Ok(lookup) => reloaded.push(lookup.issue),
            Err(_) => reloaded.push(issue.clone()),
        }
    }
    Ok(reloaded)
}

static SECTION_HEADINGS: [&str; 8] = [
    "Yesterday",
    "Today",
    CLOSE_OUT_SECTION,
    "Blockers",
    "Likely questions",
    "Health",
    "Momentum",
    "Risks",
];

/// Extract rendered text for a standup section from CLI output.
pub fn extract_section_text(report_text: &str, section_name: &str) -> String {
    let mut section_lines = Vec::new();
    let mut in_section = false;
    for line in report_text.lines() {
        if line.trim() == section_name {
            in_section = true;
            continue;
        }
        if in_section {
            if SECTION_HEADINGS.contains(&line.trim()) {
                break;
            }
            if line.starts_with("Standup (") && !section_lines.is_empty() {
                break;
            }
            section_lines.push(line);
        }
    }
    section_lines.join("\n")
}

/// Return whether standup text uses first-person phrasing.
pub fn report_uses_first_person_voice(report_text: &str) -> bool {
    let pattern = Regex::new(r"(?i)\b(I|I'm|my|we|our)\b").expect("valid regex");
    pattern.is_match(report_text)
}

/// Return whether standup text uses third-person executive phrasing.
pub fn report_uses_third_person_executive_voice(report_text: &str) -> bool {
    let pattern =
        Regex::new(r"(?i)\b(in-progress issues|blocked issue|stakeholders|Executive brief)\b")
            .expect("valid regex");
    pattern.is_match(report_text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_standup_profile_defaults_to_meeting_script() {
        let profile = resolve_standup_profile(None).expect("profile");
        assert_eq!(profile, MEETING_SCRIPT_PROFILE);
    }

    #[test]
    fn resolve_standup_profile_rejects_unknown_profile() {
        let error = resolve_standup_profile(Some("unknown")).expect_err("error");
        assert_eq!(
            error.to_string(),
            "unknown standup profile: unknown".to_string()
        );
    }

    #[test]
    fn truncate_bullet_adds_ellipsis_when_needed() {
        let text = "x".repeat(130);
        let truncated = truncate_bullet_with_max_length(&text, 120);
        assert!(truncated.ends_with("..."));
        assert!(truncated.chars().count() <= 120);
    }
}
