//! Canonical write-side gate for issue mutations.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use chrono::Utc;

use crate::error::KanbusError;
use crate::event_history::{
    delete_events_for_issues, events_dir_for_issue_path, events_enabled_for_events_directory,
    issue_deleted_payload, now_timestamp, write_events_batch, write_events_batch_with_setting,
    EventRecord, EventType,
};
use crate::issue_files::{delete_issue_file, read_issue_from_file, write_issue_to_file};
use crate::models::IssueData;
use crate::overlay::{overlay_root, replace_overlay_issue_if_present};
use fs2::FileExt;

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

struct IssueWriteLock {
    _file: std::fs::File,
}

fn acquire_issue_write_lock(
    project_dir: &Path,
    issue_identifier: &str,
) -> Result<IssueWriteLock, KanbusError> {
    let lock_directory = overlay_root(project_dir).join("locks");
    std::fs::create_dir_all(&lock_directory).map_err(|error| KanbusError::Io(error.to_string()))?;
    let file = std::fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(lock_directory.join(format!("{issue_identifier}.lock")))
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    file.lock_exclusive()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(IssueWriteLock { _file: file })
}

fn refuse_if_issue_changed_since_read(
    issue_path: &Path,
    before_issue: &IssueData,
) -> Result<(), KanbusError> {
    if !issue_path.exists() {
        return Ok(());
    }
    let on_disk = read_issue_from_file(issue_path)?;
    if on_disk.updated_at != before_issue.updated_at {
        return Err(KanbusError::IssueOperation(format!(
            "concurrent modification: {} changed since it was read; retry the command",
            before_issue.identifier
        )));
    }
    Ok(())
}

/// Persist an issue mutation with updated_at and event history.
///
/// When `before_issue` is absent, a failed event write removes the newly
/// written issue file instead of restoring a previous snapshot.
///
/// # Arguments
/// * `request` - Mutation request including issue, path, and events.
///
/// # Errors
/// Returns `KanbusError` if persistence or event writing fails.
pub fn persist_issue_mutation(
    request: &PersistIssueMutationRequest,
) -> Result<PersistIssueMutationResult, KanbusError> {
    let events_dir = events_dir_for_issue_path(
        &request.project_dir,
        request.relocate_to.as_ref().unwrap_or(&request.issue_path),
    )?;
    let events_enabled = events_enabled_for_events_directory(&events_dir)?;
    persist_issue_mutation_with_events_setting(request, events_enabled)
}

/// Persist an issue mutation using the events setting of an already loaded configuration.
///
/// # Arguments
/// * `request` - Mutation request including issue, path, and events.
/// * `events_enabled` - The `events` setting from the loaded configuration.
///
/// # Errors
/// Returns `KanbusError` if persistence or event writing fails.
pub fn persist_issue_mutation_with_events_setting(
    request: &PersistIssueMutationRequest,
    events_enabled: bool,
) -> Result<PersistIssueMutationResult, KanbusError> {
    let current_time = Utc::now();
    let mut persisted_issue = request.issue.clone();
    persisted_issue.updated_at = current_time;
    let target_path = request.relocate_to.as_ref().unwrap_or(&request.issue_path);
    let _write_lock = acquire_issue_write_lock(&request.project_dir, &persisted_issue.identifier)?;
    if let Some(before_issue) = &request.before_issue {
        refuse_if_issue_changed_since_read(&request.issue_path, before_issue)?;
    }
    write_issue_to_file(&persisted_issue, target_path)?;
    replace_overlay_issue_if_present(&request.project_dir, &persisted_issue)?;
    let final_issue_path = target_path.clone();
    if request.relocate_to.is_some() {
        delete_issue_file(&request.issue_path)?;
    }
    let events_dir = events_dir_for_issue_path(&request.project_dir, &final_issue_path)?;
    match write_events_batch_with_setting(&events_dir, &request.events, events_enabled) {
        Ok(_paths) => Ok(PersistIssueMutationResult {
            issue: persisted_issue,
            events: request.events.clone(),
        }),
        Err(error) => {
            if request.relocate_to.is_some() && final_issue_path.exists() {
                let _ = write_issue_to_file(&persisted_issue, &request.issue_path);
                let _ = delete_issue_file(&final_issue_path);
            }
            if let Some(before_issue) = &request.before_issue {
                write_issue_to_file(before_issue, &request.issue_path)?;
                let _ = replace_overlay_issue_if_present(&request.project_dir, before_issue);
            } else if request.issue_path.exists() {
                let _ = delete_issue_file(&request.issue_path);
            }
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
    delete_issue_file(issue_path)?;
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event_history::{now_timestamp, EventRecord, EventType};
    use crate::issue_files::{read_issue_from_file, write_issue_to_file};
    use crate::models::IssueData;
    use chrono::Utc;
    use serde_json::json;
    use std::collections::BTreeMap;
    use std::fs;

    fn make_issue(id: &str, title: &str) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: title.to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        }
    }

    fn event(issue_id: &str) -> EventRecord {
        EventRecord::new(
            issue_id,
            EventType::IssueCreated,
            "dev",
            json!({"ok": true}),
            now_timestamp(),
        )
    }

    #[test]
    fn persist_issue_mutation_writes_issue_and_events() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        let issue = make_issue("kanbus-1", "Created");
        let request = PersistIssueMutationRequest {
            project_dir: project_dir.clone(),
            issue_path: issue_path.clone(),
            issue,
            actor_id: "dev".to_string(),
            events: vec![event("kanbus-1")],
            before_issue: None,
            relocate_to: None,
        };
        persist_issue_mutation(&request).expect("persist");
        let stored = read_issue_from_file(&issue_path).expect("read");
        assert_eq!(stored.title, "Created");
        assert!(project_dir
            .join("events")
            .read_dir()
            .expect("events")
            .next()
            .is_some());
    }

    fn mutation_request(
        project_dir: &Path,
        issue_path: &Path,
        before_issue: &IssueData,
        title: &str,
    ) -> PersistIssueMutationRequest {
        let mut updated = before_issue.clone();
        updated.title = title.to_string();
        PersistIssueMutationRequest {
            project_dir: project_dir.to_path_buf(),
            issue_path: issue_path.to_path_buf(),
            issue: updated,
            actor_id: "dev".to_string(),
            events: vec![event(&before_issue.identifier)],
            before_issue: Some(before_issue.clone()),
            relocate_to: None,
        }
    }

    #[test]
    fn second_writer_with_stale_snapshot_is_refused() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        write_issue_to_file(&make_issue("kanbus-1", "Original"), &issue_path).expect("seed");
        let snapshot_read_by_both = read_issue_from_file(&issue_path).expect("read");

        persist_issue_mutation(&mutation_request(
            &project_dir,
            &issue_path,
            &snapshot_read_by_both,
            "First writer",
        ))
        .expect("first writer wins");
        let refused = persist_issue_mutation(&mutation_request(
            &project_dir,
            &issue_path,
            &snapshot_read_by_both,
            "Second writer",
        ))
        .expect_err("second writer must be refused");

        assert!(refused.to_string().contains("concurrent modification"));
        assert_eq!(
            read_issue_from_file(&issue_path).expect("read").title,
            "First writer"
        );
    }

    #[test]
    fn concurrent_writers_never_silently_overwrite_each_other() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        write_issue_to_file(&make_issue("kanbus-1", "Original"), &issue_path).expect("seed");
        let snapshot_read_by_both = read_issue_from_file(&issue_path).expect("read");

        let outcomes: Vec<bool> = (0..2)
            .map(|writer| {
                let project_dir = project_dir.clone();
                let issue_path = issue_path.clone();
                let snapshot = snapshot_read_by_both.clone();
                std::thread::spawn(move || {
                    persist_issue_mutation(&mutation_request(
                        &project_dir,
                        &issue_path,
                        &snapshot,
                        &format!("Writer {writer}"),
                    ))
                    .is_ok()
                })
            })
            .collect::<Vec<_>>()
            .into_iter()
            .map(|handle| handle.join().expect("join"))
            .collect();

        assert_eq!(outcomes.iter().filter(|accepted| **accepted).count(), 1);
    }

    #[test]
    fn persist_issue_mutation_unlinks_create_when_events_fail() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-new.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        fs::write(project_dir.join("events"), "not-a-directory").expect("block events");
        let issue = make_issue("kanbus-new", "Created");
        let request = PersistIssueMutationRequest {
            project_dir: project_dir.clone(),
            issue_path: issue_path.clone(),
            issue,
            actor_id: "dev".to_string(),
            events: vec![event("kanbus-new")],
            before_issue: None,
            relocate_to: None,
        };
        persist_issue_mutation(&request).expect_err("event write should fail");
        assert!(!issue_path.exists());
    }

    #[test]
    fn persist_issue_mutation_restores_before_issue_when_events_fail() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        let before = make_issue("kanbus-1", "Before");
        write_issue_to_file(&before, &issue_path).expect("write before");
        fs::write(project_dir.join("events"), "not-a-directory").expect("block events");
        let after = make_issue("kanbus-1", "After");
        let request = PersistIssueMutationRequest {
            project_dir: project_dir.clone(),
            issue_path: issue_path.clone(),
            issue: after,
            actor_id: "dev".to_string(),
            events: vec![event("kanbus-1")],
            before_issue: Some(before),
            relocate_to: None,
        };
        persist_issue_mutation(&request).expect_err("event write should fail");
        let restored = read_issue_from_file(&issue_path).expect("read restored");
        assert_eq!(restored.title, "Before");
    }

    #[test]
    fn persist_issue_deletion_removes_file_and_writes_audit() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        let issue = make_issue("kanbus-1", "Delete me");
        write_issue_to_file(&issue, &issue_path).expect("write issue");
        persist_issue_deletion(&project_dir, &issue_path, &issue, "dev", true).expect("delete");
        assert!(!issue_path.exists());
        assert!(project_dir
            .join("events")
            .read_dir()
            .expect("events")
            .next()
            .is_some());
    }

    #[test]
    fn persist_issue_deletion_restores_file_when_events_fail() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        let issue = make_issue("kanbus-1", "Keep me");
        write_issue_to_file(&issue, &issue_path).expect("write issue");
        fs::write(project_dir.join("events"), "not-a-directory").expect("block events");
        persist_issue_deletion(&project_dir, &issue_path, &issue, "dev", true)
            .expect_err("audit write should fail");
        let restored = read_issue_from_file(&issue_path).expect("restored");
        assert_eq!(restored.title, "Keep me");
    }
}
