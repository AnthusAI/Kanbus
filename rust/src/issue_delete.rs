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
    let issue_id = lookup.issue.identifier.clone();

    std::fs::remove_file(&lookup.issue_path).map_err(|error| KanbusError::Io(error.to_string()))?;

    // Publish real-time notification
    use crate::notification_events::NotificationEvent;
    use crate::notification_publisher::publish_notification;
    let _ = publish_notification(root, NotificationEvent::IssueDeleted { issue_id });

    Ok(())
}
