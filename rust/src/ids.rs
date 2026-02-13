//! Issue identifier generation.

use std::collections::HashSet;
use uuid::Uuid;

use crate::error::TaskulusError;

/// Request to generate a unique issue identifier.
#[derive(Debug, Clone)]
pub struct IssueIdentifierRequest {
    /// Issue title.
    pub title: String,
    /// Existing identifiers to avoid collisions.
    pub existing_ids: HashSet<String>,
    /// ID project key (prefix).
    pub prefix: String,
}

/// Generated issue identifier.
#[derive(Debug, Clone)]
pub struct IssueIdentifierResult {
    /// Unique issue identifier.
    pub identifier: String,
}

/// Produce a display-friendly issue key.
///
/// # Arguments
/// * `identifier` - Full issue identifier (may include project key and UUID).
/// * `project_context` - When true, omit the project key.
///
/// # Returns
/// Formatted key with optional project key and abbreviated hash.
pub fn format_issue_key(identifier: &str, project_context: bool) -> String {
    if identifier.chars().all(|ch| ch.is_ascii_digit()) {
        return identifier.to_string();
    }

    let (key_part, remainder) = if let Some((key, rest)) = identifier.split_once('-') {
        if key.is_empty() || rest.is_empty() {
            (None, identifier)
        } else {
            (Some(key), rest)
        }
    } else {
        (None, identifier)
    };

    let (base, suffix) = if let Some((head, tail)) = remainder.split_once('.') {
        (head, Some(tail))
    } else {
        (remainder, None)
    };

    let truncated: String = base.chars().take(6).collect();

    if project_context {
        return match suffix {
            Some(tail) => format!("{}.{}", truncated, tail),
            None => truncated,
        };
    }

    if let Some(key) = key_part {
        return match suffix {
            Some(tail) => format!("{}-{}.{}", key, truncated, tail),
            None => format!("{}-{}", key, truncated),
        };
    }

    match suffix {
        Some(tail) => format!("{}.{}", truncated, tail),
        None => truncated,
    }
}

/// Generate a unique issue ID using a UUID.
///
/// # Arguments
///
/// * `request` - Validated request containing title and existing IDs.
///
/// # Returns
///
/// A unique ID string with format '{prefix}-{uuid}'.
///
/// # Errors
///
/// Returns `TaskulusError::IdGenerationFailed` if unable to generate unique ID after 10 attempts.
pub fn generate_issue_identifier(
    request: &IssueIdentifierRequest,
) -> Result<IssueIdentifierResult, TaskulusError> {
    for _ in 0..10 {
        let identifier = format!("{}-{}", request.prefix, Uuid::new_v4());
        if !request.existing_ids.contains(&identifier) {
            return Ok(IssueIdentifierResult { identifier });
        }
    }

    Err(TaskulusError::IdGenerationFailed(
        "unable to generate unique id after 10 attempts".to_string(),
    ))
}

/// Generate multiple identifiers for uniqueness checks.
///
/// # Arguments
///
/// * `title` - Base title for hashing.
/// * `prefix` - ID prefix.
/// * `count` - Number of IDs to generate.
///
/// # Returns
///
/// Set of generated identifiers.
///
/// # Errors
///
/// Returns `TaskulusError` if ID generation fails.
pub fn generate_many_identifiers(
    title: &str,
    prefix: &str,
    count: usize,
) -> Result<HashSet<String>, TaskulusError> {
    let mut existing = HashSet::new();
    for _ in 0..count {
        let request = IssueIdentifierRequest {
            title: title.to_string(),
            existing_ids: existing.clone(),
            prefix: prefix.to_string(),
        };
        let result = generate_issue_identifier(&request)?;
        existing.insert(result.identifier);
    }
    Ok(existing)
}
