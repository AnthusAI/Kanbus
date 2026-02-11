use std::collections::BTreeMap;

use taskulus::hierarchy::{get_allowed_child_types, validate_parent_child_relationship};
use taskulus::models::ProjectConfiguration;

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

#[test]
fn get_allowed_child_types_returns_next_hierarchical_and_types() {
    let configuration = build_configuration();
    let allowed = get_allowed_child_types(&configuration, "epic");
    assert_eq!(allowed, vec!["task", "bug", "story", "chore"]);
}

#[test]
fn get_allowed_child_types_returns_empty_for_non_hierarchical_parent() {
    let configuration = build_configuration();
    assert!(get_allowed_child_types(&configuration, "bug").is_empty());
}

#[test]
fn validate_parent_child_relationship_allows_valid_pair() {
    let configuration = build_configuration();
    validate_parent_child_relationship(&configuration, "epic", "task")
        .expect("valid parent-child pair");
}

#[test]
fn validate_parent_child_relationship_rejects_invalid_pair() {
    let configuration = build_configuration();
    let error = validate_parent_child_relationship(&configuration, "task", "epic")
        .expect_err("invalid parent-child pair");
    assert_eq!(
        error.to_string(),
        "invalid parent-child relationship: 'task' cannot have child 'epic'"
    );
}
