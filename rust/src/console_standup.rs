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
    use chrono::{Duration, Utc};
    use serde_json::json;
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::sync::{Mutex, MutexGuard};
    use tempfile::TempDir;

    static DAEMON_ENV_LOCK: Mutex<()> = Mutex::new(());

    struct DaemonDisabledEnv {
        _lock: MutexGuard<'static, ()>,
        previous: Option<std::ffi::OsString>,
    }

    impl DaemonDisabledEnv {
        fn new() -> Self {
            let lock = DAEMON_ENV_LOCK
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            let previous = std::env::var_os("KANBUS_NO_DAEMON");
            std::env::set_var("KANBUS_NO_DAEMON", "1");
            Self {
                _lock: lock,
                previous,
            }
        }
    }

    impl Drop for DaemonDisabledEnv {
        fn drop(&mut self) {
            if let Some(value) = self.previous.as_ref() {
                std::env::set_var("KANBUS_NO_DAEMON", value);
            } else {
                std::env::remove_var("KANBUS_NO_DAEMON");
            }
        }
    }

    fn initialized_project() -> (TempDir, PathBuf) {
        let temp = TempDir::new().expect("temporary project");
        let root = temp.path().to_path_buf();
        let configuration = crate::config::default_project_configuration();
        fs::write(
            root.join(".kanbus.yml"),
            serde_yaml::to_string(&configuration).expect("serialize project config"),
        )
        .expect("write project config");
        fs::create_dir_all(root.join("project/issues")).expect("create issue directory");
        (temp, root)
    }

    fn write_in_progress_issue(root: &Path, identifier: &str) {
        let now = Utc::now();
        let issue = crate::models::IssueData {
            identifier: identifier.to_string(),
            title: "Build the coordination endpoint".to_string(),
            description: "Expose durable coordination state to workers.".to_string(),
            issue_type: "task".to_string(),
            status: "in_progress".to_string(),
            priority: 2,
            assignee: None,
            creator: Some("worker".to_string()),
            parent: None,
            labels: vec!["coordination".to_string()],
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now - Duration::hours(2),
            updated_at: now - Duration::hours(1),
            closed_at: None,
            agent: None,
            right_now_summary: Some("Implementing the coordination API".to_string()),
            right_now_updated_at: Some(now - Duration::minutes(30)),
            custom: Default::default(),
        };
        fs::write(
            root.join("project/issues")
                .join(format!("{identifier}.json")),
            serde_json::to_vec_pretty(&issue).expect("serialize issue"),
        )
        .expect("write issue");
    }

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

    #[test]
    fn root_api_generates_report_for_a_project_with_issue_and_event_history() {
        let _daemon_env = DaemonDisabledEnv::new();
        let (_temp, root) = initialized_project();
        let identifier = "kanbus-standup";
        write_in_progress_issue(&root, identifier);

        let event_dir = root.join("project/events");
        fs::create_dir_all(&event_dir).expect("create event history");
        let event = crate::event_history::EventRecord::new(
            identifier,
            crate::event_history::EventType::IssueCreated,
            "worker",
            json!({"status": "open", "title": "Build the coordination endpoint"}),
            Utc::now().to_rfc3339(),
        );
        fs::write(
            event_dir.join("created.json"),
            serde_json::to_vec(&event).expect("serialize event"),
        )
        .expect("write event history");

        let response = generate_standup_report_for_root(
            &root,
            &StandupGenerateRequest {
                profile: Some(MEETING_SCRIPT_PROFILE.to_string()),
                window: None,
                lookback: None,
                skip_weekends: None,
            },
        )
        .expect("generate standup report");

        assert_eq!(response.profile, MEETING_SCRIPT_PROFILE);
        assert_eq!(response.source_issues, vec![identifier]);
        assert_eq!(
            response.right_now_texts.get(identifier).map(String::as_str),
            Some("Implementing the coordination API")
        );
        assert!(response
            .sections
            .iter()
            .any(|section| section.name == "Today"));
        assert!(response.text.contains("Standup (meeting-script)"));
        assert!(response.text.contains("coordination API"));
    }

    #[test]
    fn empty_project_generates_a_well_formed_default_report() {
        let _daemon_env = DaemonDisabledEnv::new();
        let (_temp, root) = initialized_project();
        let response = generate_standup_report(
            &FileStore::new(&root),
            &StandupGenerateRequest {
                profile: None,
                window: None,
                lookback: None,
                skip_weekends: None,
            },
        )
        .expect("generate empty-board report");

        assert_eq!(response.profile, MEETING_SCRIPT_PROFILE);
        assert!(response.source_issues.is_empty());
        assert!(response.right_now_texts.is_empty());
        assert_eq!(response.sections.len(), 5);
        assert!(response.text.starts_with("Standup (meeting-script)"));
    }
}
