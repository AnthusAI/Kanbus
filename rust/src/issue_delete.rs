//! Issue deletion workflow.

use std::path::Path;

use crate::error::TaskulusError;
use crate::issue_lookup::load_issue_from_project;

/// Delete an issue file from disk.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `TaskulusError` if deletion fails.
pub fn delete_issue(root: &Path, identifier: &str) -> Result<(), TaskulusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    std::fs::remove_file(&lookup.issue_path).map_err(|error| TaskulusError::Io(error.to_string()))
}
