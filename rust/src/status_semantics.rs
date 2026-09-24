//! Semantic status categories for workflow business logic.

use crate::error::KanbusError;
use crate::models::ProjectConfiguration;

/// Semantic category for statuses that are not yet started.
pub const SEMANTIC_TODO: &str = "todo";
/// Semantic category for statuses representing active work.
pub const SEMANTIC_IN_PROGRESS: &str = "in_progress";
/// Semantic category for completed statuses.
pub const SEMANTIC_DONE: &str = "done";

const VALID_SEMANTIC_CATEGORIES: &[&str] = &[SEMANTIC_TODO, SEMANTIC_IN_PROGRESS, SEMANTIC_DONE];

/// Validate a semantic category value.
///
/// # Arguments
/// * `semantic_category` - Category string from configuration.
///
/// # Errors
/// Returns `KanbusError::Configuration` when the value is not recognized.
pub fn validate_semantic_category(semantic_category: &str) -> Result<(), KanbusError> {
    if VALID_SEMANTIC_CATEGORIES.contains(&semantic_category) {
        Ok(())
    } else {
        Err(KanbusError::Configuration(format!(
            "invalid semantic_category '{}': must be one of todo, in_progress, done",
            semantic_category
        )))
    }
}

/// Return the first configured status key for a semantic category.
///
/// When multiple statuses share a category, the first entry in the configured
/// `statuses` list wins.
///
/// # Arguments
/// * `configuration` - Project configuration.
/// * `semantic_category` - Semantic category to resolve.
///
/// # Errors
/// Returns `KanbusError::Configuration` when no status matches the category.
pub fn resolve_primary_status_key_for_semantic_category(
    configuration: &ProjectConfiguration,
    semantic_category: &str,
) -> Result<String, KanbusError> {
    validate_semantic_category(semantic_category)?;
    configuration
        .statuses
        .iter()
        .find(|status| status.semantic_category == semantic_category)
        .map(|status| status.key.clone())
        .ok_or_else(|| {
            KanbusError::Configuration(format!(
                "no status configured with semantic_category '{}'",
                semantic_category
            ))
        })
}

/// Return a configured status key within a semantic category, preferring named keys.
///
/// # Arguments
/// * `configuration` - Project configuration.
/// * `semantic_category` - Semantic category to resolve.
/// * `preferred_keys` - Status keys to try in order before the primary category key.
///
/// # Errors
/// Returns `KanbusError::Configuration` when no status matches the category.
pub fn resolve_preferred_status_key_for_semantic_category(
    configuration: &ProjectConfiguration,
    semantic_category: &str,
    preferred_keys: &[&str],
) -> Result<String, KanbusError> {
    validate_semantic_category(semantic_category)?;
    for preferred_key in preferred_keys {
        if configuration.statuses.iter().any(|status| {
            status.key == *preferred_key && status.semantic_category == semantic_category
        }) {
            return Ok(preferred_key.to_string());
        }
    }
    resolve_primary_status_key_for_semantic_category(configuration, semantic_category)
}

/// Return every configured status key for a semantic category.
///
/// # Arguments
/// * `configuration` - Project configuration.
/// * `semantic_category` - Semantic category to resolve.
///
/// # Errors
/// Returns `KanbusError::Configuration` when the category value is invalid.
pub fn status_keys_for_semantic_category(
    configuration: &ProjectConfiguration,
    semantic_category: &str,
) -> Result<Vec<String>, KanbusError> {
    validate_semantic_category(semantic_category)?;
    Ok(configuration
        .statuses
        .iter()
        .filter(|status| status.semantic_category == semantic_category)
        .map(|status| status.key.clone())
        .collect())
}

/// Return the semantic category for a configured status key.
///
/// # Arguments
/// * `configuration` - Project configuration.
/// * `status_key` - Status key to look up.
///
/// # Returns
/// The semantic category when the status exists, otherwise `None`.
pub fn semantic_category_for_status_key(
    configuration: &ProjectConfiguration,
    status_key: &str,
) -> Option<String> {
    configuration
        .statuses
        .iter()
        .find(|status| status.key == status_key)
        .map(|status| status.semantic_category.clone())
}

/// Default terminal color name for a semantic category.
///
/// # Arguments
/// * `semantic_category` - Semantic category value.
///
/// # Returns
/// A color name suitable for CLI output.
pub fn default_color_for_semantic_category(semantic_category: &str) -> &'static str {
    match semantic_category {
        SEMANTIC_TODO => "cyan",
        SEMANTIC_IN_PROGRESS => "blue",
        SEMANTIC_DONE => "green",
        _ => "white",
    }
}

/// Assign a semantic category when importing Beads status keys.
///
/// # Arguments
/// * `status_key` - Normalized Kanbus status key from Beads import.
///
/// # Returns
/// A semantic category string for the imported status.
pub fn semantic_category_for_beads_status_key(status_key: &str) -> &'static str {
    match status_key {
        "in_progress" | "blocked" => SEMANTIC_IN_PROGRESS,
        "closed" | "done" => SEMANTIC_DONE,
        _ => SEMANTIC_TODO,
    }
}

/// Map a Beads status value to a Kanbus status key using semantic categories.
///
/// # Arguments
/// * `configuration` - Project configuration containing semantic categories.
/// * `raw_status` - Status value from Beads.
///
/// # Errors
/// Returns `KanbusError::Configuration` when a semantic category cannot be resolved.
pub fn map_beads_status(
    configuration: &ProjectConfiguration,
    raw_status: &str,
) -> Result<String, KanbusError> {
    if raw_status == "in-progress" {
        return resolve_primary_status_key_for_semantic_category(
            configuration,
            SEMANTIC_IN_PROGRESS,
        );
    }
    Ok(raw_status.to_string())
}

/// Map a Jira status name to a Kanbus status key using semantic categories.
///
/// # Arguments
/// * `configuration` - Project configuration containing semantic categories.
/// * `jira_status` - Status name from Jira.
///
/// # Errors
/// Returns `KanbusError::Configuration` when a semantic category cannot be resolved.
pub fn map_jira_status_to_key(
    configuration: &ProjectConfiguration,
    jira_status: &str,
) -> Result<String, KanbusError> {
    match jira_status.to_lowercase().as_str() {
        "to do" | "open" | "new" => resolve_preferred_status_key_for_semantic_category(
            configuration,
            SEMANTIC_TODO,
            &["open"],
        ),
        "backlog" => resolve_preferred_status_key_for_semantic_category(
            configuration,
            SEMANTIC_TODO,
            &["backlog", "open"],
        ),
        "in progress" | "in review" | "in development" => {
            resolve_primary_status_key_for_semantic_category(configuration, SEMANTIC_IN_PROGRESS)
        }
        "done" | "closed" | "resolved" | "complete" | "completed" => {
            resolve_preferred_status_key_for_semantic_category(
                configuration,
                SEMANTIC_DONE,
                &["closed"],
            )
        }
        "blocked" | "impediment" => resolve_preferred_status_key_for_semantic_category(
            configuration,
            SEMANTIC_IN_PROGRESS,
            &["blocked"],
        ),
        _ => resolve_preferred_status_key_for_semantic_category(
            configuration,
            SEMANTIC_TODO,
            &["open"],
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;

    #[test]
    fn semantic_categories_validate_known_values_and_reject_unknown_values() {
        for category in [SEMANTIC_TODO, SEMANTIC_IN_PROGRESS, SEMANTIC_DONE] {
            validate_semantic_category(category).expect("known semantic category");
        }
        assert_eq!(
            validate_semantic_category("paused")
                .unwrap_err()
                .to_string(),
            "invalid semantic_category 'paused': must be one of todo, in_progress, done"
        );
    }

    #[test]
    fn resolve_primary_status_key_returns_first_match() {
        let configuration = default_project_configuration();
        let key =
            resolve_primary_status_key_for_semantic_category(&configuration, SEMANTIC_IN_PROGRESS)
                .expect("key");
        assert_eq!(key, "in_progress");
    }

    #[test]
    fn status_keys_for_semantic_category_returns_all_matches() {
        let configuration = default_project_configuration();
        let keys =
            status_keys_for_semantic_category(&configuration, SEMANTIC_IN_PROGRESS).expect("keys");
        assert_eq!(keys, vec!["in_progress".to_string(), "blocked".to_string()]);
    }

    #[test]
    fn map_jira_status_resolves_semantic_category() {
        let configuration = default_project_configuration();
        let status = map_jira_status_to_key(&configuration, "In Development").expect("status");
        assert_eq!(status, "in_progress");
    }

    #[test]
    fn preferred_status_keys_must_belong_to_the_requested_category() {
        let configuration = default_project_configuration();
        assert_eq!(
            resolve_preferred_status_key_for_semantic_category(
                &configuration,
                SEMANTIC_IN_PROGRESS,
                &["open", "blocked"],
            )
            .expect("matching preferred status"),
            "blocked"
        );
        assert_eq!(
            resolve_preferred_status_key_for_semantic_category(
                &configuration,
                SEMANTIC_IN_PROGRESS,
                &["open"],
            )
            .expect("primary fallback"),
            "in_progress"
        );
        assert!(resolve_preferred_status_key_for_semantic_category(
            &configuration,
            "paused",
            &["open"]
        )
        .is_err());
    }

    #[test]
    fn missing_semantic_categories_and_unknown_status_keys_are_reported() {
        let mut configuration = default_project_configuration();
        configuration.statuses.clear();
        assert_eq!(
            resolve_primary_status_key_for_semantic_category(&configuration, SEMANTIC_TODO)
                .unwrap_err()
                .to_string(),
            "no status configured with semantic_category 'todo'"
        );
        assert!(status_keys_for_semantic_category(&configuration, "paused").is_err());
        assert_eq!(
            semantic_category_for_status_key(&configuration, "missing"),
            None
        );
    }

    #[test]
    fn semantic_color_and_beads_mappings_cover_known_and_fallback_values() {
        assert_eq!(default_color_for_semantic_category(SEMANTIC_TODO), "cyan");
        assert_eq!(
            default_color_for_semantic_category(SEMANTIC_IN_PROGRESS),
            "blue"
        );
        assert_eq!(default_color_for_semantic_category(SEMANTIC_DONE), "green");
        assert_eq!(default_color_for_semantic_category("custom"), "white");

        for status in ["in_progress", "blocked"] {
            assert_eq!(
                semantic_category_for_beads_status_key(status),
                SEMANTIC_IN_PROGRESS
            );
        }
        for status in ["closed", "done"] {
            assert_eq!(
                semantic_category_for_beads_status_key(status),
                SEMANTIC_DONE
            );
        }
        assert_eq!(
            semantic_category_for_beads_status_key("backlog"),
            SEMANTIC_TODO
        );
    }

    #[test]
    fn beads_and_jira_status_mappings_handle_passthrough_preference_and_missing_categories() {
        let configuration = default_project_configuration();
        assert_eq!(
            map_beads_status(&configuration, "in-progress").expect("semantic mapping"),
            "in_progress"
        );
        assert_eq!(
            map_beads_status(&configuration, "custom-status").expect("passthrough"),
            "custom-status"
        );
        assert_eq!(
            map_jira_status_to_key(&configuration, "BACKLOG").expect("backlog preference"),
            "backlog"
        );
        assert_eq!(
            map_jira_status_to_key(&configuration, "Blocked").expect("blocked preference"),
            "blocked"
        );
        assert_eq!(
            map_jira_status_to_key(&configuration, "Done").expect("closed preference"),
            "closed"
        );
        assert_eq!(
            map_jira_status_to_key(&configuration, "Some unknown status")
                .expect("unknown statuses map to the todo preference"),
            "open"
        );

        let mut incomplete = configuration;
        incomplete
            .statuses
            .retain(|status| status.semantic_category != SEMANTIC_IN_PROGRESS);
        assert!(map_beads_status(&incomplete, "in-progress").is_err());
        assert!(map_jira_status_to_key(&incomplete, "in progress").is_err());
    }
    #[test]
    fn missing_categories_are_derived_from_the_key_and_name() {
        for (key, name, expected) in [
            ("open", "Discovery", "todo"),
            ("backlog", "Backlog", "todo"),
            ("idea", "Idea", "todo"),
            ("Discovery", "Discovery", "todo"),
            ("closed", "Done", "done"),
            ("published", "Published", "done"),
            ("accepted", "Accepted", "done"),
            ("in_progress", "In Progress", "in_progress"),
            ("blocked", "Blocked", "in_progress"),
            ("assignment", "Assignment", "in_progress"),
            ("awaiting-review", "Awaiting review", "in_progress"),
        ] {
            assert_eq!(derive_semantic_category(key, name), expected, "{key}");
        }
        assert_eq!(derive_semantic_category("ready_and_shipped", ""), "done");
    }
}

const DONE_WORDS: &[&str] = &[
    "closed",
    "done",
    "complete",
    "completed",
    "resolved",
    "published",
    "shipped",
    "released",
    "archived",
    "cancelled",
    "canceled",
    "rejected",
    "accepted",
    "wontfix",
];
const TODO_WORDS: &[&str] = &[
    "open",
    "backlog",
    "todo",
    "new",
    "idea",
    "ideas",
    "proposed",
    "planned",
    "inbox",
    "queued",
    "queue",
    "ready",
    "discovery",
    "triage",
];

/// Infer `todo`, `in_progress` or `done` for a status that declares no
/// semantic category.
///
/// Older configurations predate `semantic_category`; rather than refuse to load
/// them, infer a category from the status key and name. Any word that reads as a
/// finished state gives `done`, then any that reads as not started gives `todo`;
/// every other status (including `blocked`) is work in progress. An explicit
/// value in the configuration always wins.
pub fn derive_semantic_category(key: &str, name: &str) -> &'static str {
    let lowered = format!("{key} {name}").to_lowercase();
    let words: Vec<&str> = lowered
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|word| !word.is_empty())
        .collect();
    if words.iter().any(|word| DONE_WORDS.contains(word)) {
        SEMANTIC_DONE
    } else if words.iter().any(|word| TODO_WORDS.contains(word)) {
        SEMANTIC_TODO
    } else {
        SEMANTIC_IN_PROGRESS
    }
}
