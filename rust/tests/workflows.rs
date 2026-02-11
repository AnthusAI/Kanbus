use chrono::{TimeZone, Utc};
use std::collections::BTreeMap;

use taskulus::models::IssueData;
use taskulus::models::ProjectConfiguration;
use taskulus::workflows::{apply_transition_side_effects, validate_status_transition};

fn build_configuration() -> ProjectConfiguration {
    let workflows = BTreeMap::from([
        (
            "default".to_string(),
            BTreeMap::from([
                (
                    "open".to_string(),
                    vec![
                        "in_progress".to_string(),
                        "closed".to_string(),
                        "deferred".to_string(),
                    ],
                ),
                (
                    "in_progress".to_string(),
                    vec![
                        "open".to_string(),
                        "blocked".to_string(),
                        "closed".to_string(),
                    ],
                ),
                (
                    "blocked".to_string(),
                    vec!["in_progress".to_string(), "closed".to_string()],
                ),
                ("closed".to_string(), vec!["open".to_string()]),
                (
                    "deferred".to_string(),
                    vec!["open".to_string(), "closed".to_string()],
                ),
            ]),
        ),
        (
            "epic".to_string(),
            BTreeMap::from([
                (
                    "open".to_string(),
                    vec!["in_progress".to_string(), "closed".to_string()],
                ),
                (
                    "in_progress".to_string(),
                    vec!["open".to_string(), "closed".to_string()],
                ),
                ("closed".to_string(), vec!["open".to_string()]),
            ]),
        ),
    ]);

    let priorities = BTreeMap::from([
        (0, "critical".to_string()),
        (1, "high".to_string()),
        (2, "medium".to_string()),
        (3, "low".to_string()),
        (4, "trivial".to_string()),
    ]);

    ProjectConfiguration {
        prefix: "tsk".to_string(),
        hierarchy: vec![
            "initiative".to_string(),
            "epic".to_string(),
            "task".to_string(),
            "sub-task".to_string(),
        ],
        types: vec!["bug".to_string(), "story".to_string(), "chore".to_string()],
        workflows,
        initial_status: "open".to_string(),
        priorities,
        default_priority: 2,
    }
}

fn build_issue_data(status: &str, closed_at: Option<chrono::DateTime<Utc>>) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: "tsk-test01".to_string(),
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type: "task".to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at,
        custom: BTreeMap::new(),
    }
}

#[test]
fn validate_status_transition_allows_valid_transition() {
    let configuration = build_configuration();
    validate_status_transition(&configuration, "task", "open", "in_progress")
        .expect("valid transition");
}

#[test]
fn validate_status_transition_rejects_invalid_transition() {
    let configuration = build_configuration();
    let error = validate_status_transition(&configuration, "task", "open", "blocked")
        .expect_err("invalid transition");
    assert_eq!(
        error.to_string(),
        "invalid transition from 'open' to 'blocked' for type 'task'"
    );
}

#[test]
fn apply_transition_side_effects_sets_closed_at_on_close() {
    let now = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = build_issue_data("open", None);
    let updated = apply_transition_side_effects(&issue, "closed", now);
    assert_eq!(updated.closed_at, Some(now));
}

#[test]
fn apply_transition_side_effects_clears_closed_at_on_reopen() {
    let now = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let closed_at = Utc.with_ymd_and_hms(2026, 2, 10, 0, 0, 0).unwrap();
    let issue = build_issue_data("closed", Some(closed_at));
    let updated = apply_transition_side_effects(&issue, "open", now);
    assert_eq!(updated.closed_at, None);
}
