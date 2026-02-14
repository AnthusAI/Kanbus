//! Issue close workflow.

use std::path::Path;

use crate::error::KanbusError;
use crate::issue_update::update_issue;
use crate::models::IssueData;

/// Close an issue by transitioning it to closed status.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `KanbusError` if closing fails.
pub fn close_issue(root: &Path, identifier: &str) -> Result<IssueData, KanbusError> {
    update_issue(
        root,
        identifier,
        None,
        None,
        Some("closed"),
        None,
        false,
        true,
    )
}
