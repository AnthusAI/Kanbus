//! Canonical write-side gate for issue mutations.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use chrono::Utc;

use crate::error::KanbusError;
use crate::event_history::{
    delete_events_for_issues, events_dir_for_issue_path, issue_deleted_payload, now_timestamp,
    write_events_batch, EventRecord, EventType,
};
use crate::issue_files::write_issue_to_file;
use crate::models::IssueData;

/// Request to persist an issue mutation through the write gate.
#[derive(Debug, Clone)]
pub struct PersistIssueMutationRequest {
    pub project_dir: PathBuf,
    pub issue_path: PathBuf,
    pub issue: IssueData,
    pub actor_id: String,
    pub events: Vec<EventRecord>,
    pub before_issue: Option<IssueData>,
    pub relocate_to: Option<PathBuf>,
}

/// Result of persisting an issue mutation.
#[derive(Debug, Clone)]
pub struct PersistIssueMutationResult {
    pub issue: IssueData,
    pub events: Vec<EventRecord>,
}

/// Result of persisting an issue deletion.
#[derive(Debug, Clone)]
pub struct PersistIssueDeletionResult {
    pub event: Option<EventRecord>,
}

/// Persist an issue mutation with updated_at and event history.
///
/// # Arguments
/// * `request` - Mutation request including issue, path, and events.
///
/// # Errors
/// Returns `KanbusError` if persistence or event writing fails.
pub fn persist_issue_mutation(
    request: &PersistIssueMutationRequest,
) -> Result<PersistIssueMutationResult, KanbusError> {
    let current_time = Utc::now();
    let mut persisted_issue = request.issue.clone();
    persisted_issue.updated_at = current_time;
    let rollback_issue = request
        .before_issue
        .as_ref()
        .unwrap_or(&request.issue)
        .clone();
    write_issue_to_file(&persisted_issue, &request.issue_path)?;
    let mut final_issue_path = request.issue_path.clone();
    if let Some(relocate_to) = &request.relocate_to {
        fs::rename(&request.issue_path, relocate_to)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        final_issue_path = relocate_to.clone();
    }
    let events_dir = events_dir_for_issue_path(&request.project_dir, &final_issue_path)?;
    match write_events_batch(&events_dir, &request.events) {
        Ok(_paths) => Ok(PersistIssueMutationResult {
            issue: persisted_issue,
            events: request.events.clone(),
        }),
        Err(error) => {
            if let Some(_relocate_to) = &request.relocate_to {
                if final_issue_path.exists() {
                    let _ = fs::rename(&final_issue_path, &request.issue_path);
                }
            }
            write_issue_to_file(&rollback_issue, &request.issue_path)?;
            Err(error)
        }
    }
}

/// Delete an issue and optionally retain an issue_deleted audit event.
///
/// # Arguments
/// * `project_dir` - Shared project directory.
/// * `issue_path` - Path to the issue JSON file.
/// * `issue` - Issue data being deleted.
/// * `actor_id` - Identifier of the actor performing the deletion.
/// * `retain_audit_event` - Whether to keep a final issue_deleted event.
///
/// # Errors
/// Returns `KanbusError` if deletion or event cleanup fails.
pub fn persist_issue_deletion(
    project_dir: &Path,
    issue_path: &Path,
    issue: &IssueData,
    actor_id: &str,
    retain_audit_event: bool,
) -> Result<PersistIssueDeletionResult, KanbusError> {
    let occurred_at = now_timestamp();
    let deletion_event = EventRecord::new(
        issue.identifier.clone(),
        EventType::IssueDeleted,
        actor_id,
        issue_deleted_payload(issue),
        occurred_at,
    );
    let events_dir = events_dir_for_issue_path(project_dir, issue_path)?;
    fs::remove_file(issue_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut issue_ids = HashSet::new();
    issue_ids.insert(issue.identifier.clone());
    if let Err(error) = delete_events_for_issues(&events_dir, &issue_ids) {
        write_issue_to_file(issue, issue_path)?;
        return Err(error);
    }
    if retain_audit_event {
        match write_events_batch(&events_dir, std::slice::from_ref(&deletion_event)) {
            Ok(_paths) => Ok(PersistIssueDeletionResult {
                event: Some(deletion_event),
            }),
            Err(error) => {
                write_issue_to_file(issue, issue_path)?;
                Err(error)
            }
        }
    } else {
        Ok(PersistIssueDeletionResult { event: None })
    }
}
