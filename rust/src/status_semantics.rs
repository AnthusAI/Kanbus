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
}
