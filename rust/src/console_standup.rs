//! Console standup API service.

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::console_backend::FileStore;
use crate::error::KanbusError;
use crate::standup::{
    build_standup_report, collect_right_now_texts, ensure_standup_summaries, format_standup_text,
    load_issue_event_records, load_standup_configuration, resolve_standup_profile,
};
use crate::standup_command::{select_standup_fact_feed, StandupCommandOptions};
use crate::standup_rollup::{expand_issues_with_ancestors, resolve_standup_rollup};
use crate::standup_window::{
    resolve_standup_report_time, resolve_standup_window_settings, StandupWindowOverrides,
};

/// Request body for generating a standup report from the console API.
///
/// # Fields
/// * `profile` - Optional standup profile identifier (`meeting-script` or `director-brief`)
/// * `window` - Optional standup window mode override
/// * `lookback` - Optional rolling lookback duration override
/// * `skip_weekends` - Optional skip-weekends override
#[derive(Debug, Clone, Deserialize)]
pub struct StandupGenerateRequest {
    pub profile: Option<String>,
    pub window: Option<String>,
    pub lookback: Option<String>,
    pub skip_weekends: Option<bool>,
}

/// A standup report section in console API responses.
///
/// # Fields
/// * `name` - Section heading
/// * `bullets` - Bullet text lines without leading markers
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct StandupSectionResponse {
    pub name: String,
    pub bullets: Vec<String>,
}

/// Response payload for console standup generation.
///
/// # Fields
/// * `profile` - Standup profile identifier
/// * `sections` - Ordered report sections
/// * `text` - Human-readable standup report text
/// * `source_issues` - Fact-feed issue identifiers in display order
/// * `right_now_texts` - Right-now summary text keyed by issue identifier
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct StandupGenerateResponse {
    pub profile: String,
    pub sections: Vec<StandupSectionResponse>,
    pub text: String,
    pub source_issues: Vec<String>,
    pub right_now_texts: HashMap<String, String>,
}

/// Generate a board-wide standup report for the console API.
///
/// # Arguments
/// * `store` - Console file store for the active repository
/// * `request` - Standup generation request
///
/// # Errors
///
/// Returns `KanbusError` when profile resolution, selection, or generation fails.
pub fn generate_standup_report(
    store: &FileStore,
    request: &StandupGenerateRequest,
) -> Result<StandupGenerateResponse, KanbusError> {
    let root = store.root();
    let profile = resolve_standup_profile(request.profile.as_deref())?;
    let configuration = load_standup_configuration(root)?;
    let window_overrides = StandupWindowOverrides {
        window: request.window.clone(),
        lookback: request.lookback.clone(),
        skip_weekends: request.skip_weekends,
    };
    let window_settings =
        resolve_standup_window_settings(&configuration, Some(&profile), &window_overrides)?;
    let options = StandupCommandOptions::default();
    let rollup_settings = resolve_standup_rollup(None, &configuration, false)?;
    let issues = select_standup_fact_feed(root, &options)?;
    let issues_for_summaries = expand_issues_with_ancestors(root, &issues)?;
    let issues_for_summaries = ensure_standup_summaries(root, &issues_for_summaries)?;
    let right_now_texts = collect_right_now_texts(&issues_for_summaries)?;
    let mut events_by_issue = HashMap::new();
    for issue in &issues {
        events_by_issue.insert(
            issue.identifier.clone(),
            load_issue_event_records(root, &issue.identifier),
        );
    }
    let report_time = resolve_standup_report_time()?;
    let report = build_standup_report(
        root,
        &profile,
        &issues,
        &right_now_texts,
        &events_by_issue,
        report_time,
        &window_settings,
        false,
        &configuration,
        &rollup_settings,
    )?;
    let text = format_standup_text(&report);
    Ok(StandupGenerateResponse {
        profile: report.profile.clone(),
        sections: report
            .sections
            .iter()
            .map(|section| StandupSectionResponse {
                name: section.name.clone(),
                bullets: section.bullets.clone(),
            })
            .collect(),
        text,
        source_issues: report.source_issues.clone(),
        right_now_texts: report.right_now_texts.clone(),
    })
}

/// Generate a board-wide standup report from a repository root path.
///
/// # Arguments
/// * `root` - Repository root path
/// * `request` - Standup generation request
///
/// # Errors
///
/// Returns `KanbusError` when profile resolution, selection, or generation fails.
pub fn generate_standup_report_for_root(
    root: &Path,
    request: &StandupGenerateRequest,
) -> Result<StandupGenerateResponse, KanbusError> {
    let store = FileStore::new(root);
    generate_standup_report(&store, request)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::standup::MEETING_SCRIPT_PROFILE;

    #[test]
    fn standup_generate_request_deserializes_profile() {
        let request: StandupGenerateRequest =
            serde_json::from_str("{\"profile\":\"director-brief\"}").expect("deserialize");
        assert_eq!(request.profile.as_deref(), Some("director-brief"));
    }

    #[test]
    fn standup_generate_response_serializes_text_field() {
        let response = StandupGenerateResponse {
            profile: MEETING_SCRIPT_PROFILE.to_string(),
            sections: vec![StandupSectionResponse {
                name: "Today".to_string(),
                bullets: vec!["Work".to_string()],
            }],
            text: "Standup (meeting-script)\n".to_string(),
            source_issues: vec!["kanbus-abc".to_string()],
            right_now_texts: HashMap::from([("kanbus-abc".to_string(), "Work".to_string())]),
        };
        let payload = serde_json::to_value(&response).expect("serialize");
        assert_eq!(
            payload.get("text").and_then(|value| value.as_str()),
            Some("Standup (meeting-script)\n")
        );
    }
}
