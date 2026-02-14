//! Issue deletion workflow.

use std::path::Path;

use crate::error::KanbusError;
use crate::issue_lookup::load_issue_from_project;

/// Delete an issue file from disk.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `KanbusError` if deletion fails.
pub fn delete_issue(root: &Path, identifier: &str) -> Result<(), KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    std::fs::remove_file(&lookup.issue_path).map_err(|error| KanbusError::Io(error.to_string()))
}
