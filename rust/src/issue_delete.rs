//! Issue deletion workflow.

use std::path::Path;

use crate::error::KanbusError;
use crate::event_history::{
    events_dir_for_issue_path, issue_deleted_payload, now_timestamp, write_events_batch,
    EventRecord, EventType,
};
use crate::issue_files::write_issue_to_file;
use crate::issue_lookup::load_issue_from_project;
use crate::users::get_current_user;

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

    let occurred_at = now_timestamp();
    let actor_id = get_current_user();
    let event = EventRecord::new(
        issue_id.clone(),
        EventType::IssueDeleted,
        actor_id,
        issue_deleted_payload(&lookup.issue),
        occurred_at,
    );
    let events_dir = events_dir_for_issue_path(&lookup.project_dir, &lookup.issue_path)?;
    match write_events_batch(&events_dir, &[event]) {
        Ok(_paths) => {}
        Err(error) => {
            write_issue_to_file(&lookup.issue, &lookup.issue_path)?;
            return Err(error);
        }
    }

    // Publish real-time notification
    use crate::notification_events::NotificationEvent;
    use crate::notification_publisher::publish_notification;
    let _ = publish_notification(root, NotificationEvent::IssueDeleted { issue_id });

    Ok(())
}
