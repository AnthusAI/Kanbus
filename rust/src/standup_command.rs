//! Standup CLI command orchestration.

use std::collections::HashMap;
use std::path::Path;

use chrono::Utc;

use crate::config_loader::load_repository_environment;
use crate::error::KanbusError;
use crate::models::IssueData;
use crate::right_now_command::{select_right_now_issues_for_command, RightNowCommandOptions};
use crate::standup::{
    build_standup_report, collect_right_now_texts, ensure_standup_summaries, format_standup_json,
    format_standup_text, load_issue_event_records, load_standup_configuration,
    resolve_standup_lookback_hours, resolve_standup_profile, DEFAULT_STANDUP_LOOKBACK_HOURS,
};

pub const STANDUP_DEFAULT_STATUS_FILTER: &str = "in_progress,blocked";
pub const NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS: &str =
    "--no-recursive requires one or more issue identifiers";

/// Options for the standup CLI command.
#[derive(Debug, Clone)]
pub struct StandupCommandOptions {
    /// Optional issue identifiers to scope the report.
    pub issue_ids: Vec<String>,
    /// Optional standup profile name.
    pub profile: Option<String>,
    /// Whether to emit JSON output.
    pub as_json: bool,
    /// Whether to include descendants of selected issues.
    pub recursive: bool,
}

/// Default standup command options: board-wide recursive meeting script.
impl Default for StandupCommandOptions {
    fn default() -> Self {
        Self {
            issue_ids: Vec::new(),
            profile: None,
            as_json: false,
            recursive: true,
        }
    }
}

/// Validate standup CLI options.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when options are invalid.
pub fn validate_standup_options(options: &StandupCommandOptions) -> Result<(), KanbusError> {
    if !options.recursive && options.issue_ids.is_empty() {
        return Err(KanbusError::IssueOperation(
            NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS.to_string(),
        ));
    }
    Ok(())
}

/// Build right-now selection options for standup fact-feed gathering.
pub fn build_standup_right_now_options(options: &StandupCommandOptions) -> RightNowCommandOptions {
    let status = if options.issue_ids.is_empty() {
        Some(STANDUP_DEFAULT_STATUS_FILTER.to_string())
    } else {
        None
    };
    RightNowCommandOptions {
        limit: None,
        tree: false,
        expanded: false,
        collapsed: false,
        raw: false,
        as_json: false,
        show_all: false,
        recursive: options.recursive,
        issue_ids: options.issue_ids.clone(),
        status,
        purge: false,
    }
}

/// Select standup fact-feed issues using right-now congregation scope.
///
/// # Errors
///
/// Returns `KanbusError` when selection fails.
pub fn select_standup_fact_feed(
    root: &Path,
    options: &StandupCommandOptions,
) -> Result<Vec<IssueData>, KanbusError> {
    let right_now_options = build_standup_right_now_options(options);
    select_right_now_issues_for_command(root, &right_now_options)
}

/// Generate an on-demand standup report.
///
/// # Errors
///
/// Returns `KanbusError` when options, selection, or report generation fail.
pub fn run_standup_command(
    root: &Path,
    options: &StandupCommandOptions,
) -> Result<String, KanbusError> {
    validate_standup_options(options)?;
    load_repository_environment(root);
    let profile = resolve_standup_profile(options.profile.as_deref())?;
    let configuration = load_standup_configuration(root)?;
    let mut lookback_hours = resolve_standup_lookback_hours(&configuration);
    if lookback_hours == 0 {
        lookback_hours = DEFAULT_STANDUP_LOOKBACK_HOURS;
    }
    let issues = select_standup_fact_feed(root, options)?;
    let issues = ensure_standup_summaries(root, &issues)?;
    let right_now_texts = collect_right_now_texts(&issues)?;
    let mut events_by_issue = HashMap::new();
    for issue in &issues {
        events_by_issue.insert(
            issue.identifier.clone(),
            load_issue_event_records(root, &issue.identifier),
        );
    }
    let report_time = Utc::now();
    let report = build_standup_report(
        &profile,
        &issues,
        &right_now_texts,
        &events_by_issue,
        report_time,
        lookback_hours,
    );
    if options.as_json {
        format_standup_json(&report)
    } else {
        Ok(format_standup_text(&report))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validate_standup_options_requires_issue_ids_without_recursive() {
        let options = StandupCommandOptions {
            recursive: false,
            ..StandupCommandOptions::default()
        };
        let error = validate_standup_options(&options).expect_err("error");
        assert_eq!(
            error.to_string(),
            NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS.to_string()
        );
    }

    #[test]
    fn build_standup_right_now_options_uses_default_status_filter() {
        let options = StandupCommandOptions::default();
        let right_now_options = build_standup_right_now_options(&options);
        assert_eq!(
            right_now_options.status.as_deref(),
            Some(STANDUP_DEFAULT_STATUS_FILTER)
        );
        assert!(!right_now_options.tree);
    }

    #[test]
    fn build_standup_right_now_options_omits_status_when_issue_ids_present() {
        let options = StandupCommandOptions {
            issue_ids: vec![String::from("kanbus-abc")],
            ..StandupCommandOptions::default()
        };
        let right_now_options = build_standup_right_now_options(&options);
        assert!(right_now_options.status.is_none());
    }
}
