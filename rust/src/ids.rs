//! Issue identifier generation.

use chrono::{DateTime, Utc};
use rand::RngCore;
use sha2::{Digest, Sha256};
use std::collections::HashSet;

use crate::error::TaskulusError;

/// Request to generate a unique issue identifier.
#[derive(Debug, Clone)]
pub struct IssueIdentifierRequest {
    /// Issue title.
    pub title: String,
    /// Existing identifiers to avoid collisions.
    pub existing_ids: HashSet<String>,
    /// ID prefix.
    pub prefix: String,
    /// Timestamp used as part of the hash.
    pub created_at: DateTime<Utc>,
}

/// Generated issue identifier.
#[derive(Debug, Clone)]
pub struct IssueIdentifierResult {
    /// Unique issue identifier.
    pub identifier: String,
}

fn hash_identifier_material(title: &str, created_at: DateTime<Utc>, random_bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(title.as_bytes());
    hasher.update(created_at.to_rfc3339().as_bytes());
    hasher.update(random_bytes);
    let digest = hasher.finalize();
    format!("{:x}", digest)[..6].to_string()
}

/// Generate a unique issue ID using SHA256 hash.
///
/// # Arguments
///
/// * `request` - Validated request containing title and existing IDs.
///
/// # Returns
///
/// A unique ID string with format '{prefix}-{6hex}'.
///
/// # Errors
///
/// Returns `TaskulusError::IdGenerationFailed` if unable to generate unique ID after 10 attempts.
pub fn generate_issue_identifier(
    request: &IssueIdentifierRequest,
) -> Result<IssueIdentifierResult, TaskulusError> {
    let mut rng = rand::thread_rng();
    for _ in 0..10 {
        let mut random_bytes = [0u8; 8];
        rng.fill_bytes(&mut random_bytes);
        let digest = hash_identifier_material(&request.title, request.created_at, &random_bytes);
        let identifier = format!("{}-{}", request.prefix, digest);
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
            created_at: Utc::now(),
        };
        let result = generate_issue_identifier(&request)?;
        existing.insert(result.identifier);
    }
    Ok(existing)
}
