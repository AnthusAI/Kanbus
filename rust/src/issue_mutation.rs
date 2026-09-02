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
use crate::right_now::{
    regenerate_right_now_ancestors, regenerate_right_now_for_issue_and_ancestors,
};

/// Request to persist an issue mutation through the write gate.
#[derive(Debug, Clone)]
pub struct PersistIssueMutationRequest {
    pub project_dir: PathBuf,
    pub issue_path: PathBuf,
    pub issue: IssueData,
    pub actor_id: String,
    pub events: Vec<EventRecord>,
    pub root: PathBuf,
    pub before_issue: Option<IssueData>,
    pub relocate_to: Option<PathBuf>,
    pub regenerate_right_now: bool,
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
    let current_time = Utc::now();
    let mut persisted_issue = request.issue.clone();
    persisted_issue.updated_at = current_time;
    write_issue_to_file(&persisted_issue, &request.issue_path)?;
    let mut final_issue_path = request.issue_path.clone();
    if let Some(relocate_to) = &request.relocate_to {
        fs::rename(&request.issue_path, relocate_to)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        final_issue_path = relocate_to.clone();
    }
    let events_dir = events_dir_for_issue_path(&request.project_dir, &final_issue_path)?;
    match write_events_batch(&events_dir, &request.events) {
        Ok(_paths) => {
            if request.regenerate_right_now {
                regenerate_right_now_for_issue_and_ancestors(
                    &request.root,
                    &persisted_issue.identifier,
                );
            }
            Ok(PersistIssueMutationResult {
                issue: persisted_issue,
                events: request.events.clone(),
            })
        }
        Err(error) => {
            if request.relocate_to.is_some() && final_issue_path.exists() {
                let _ = fs::rename(&final_issue_path, &request.issue_path);
            }
            if let Some(before_issue) = &request.before_issue {
                write_issue_to_file(before_issue, &request.issue_path)?;
            } else if request.issue_path.exists() {
                let _ = fs::remove_file(&request.issue_path);
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
    root: &Path,
    project_dir: &Path,
    issue_path: &Path,
    issue: &IssueData,
    actor_id: &str,
    retain_audit_event: bool,
    regenerate_right_now: bool,
) -> Result<PersistIssueDeletionResult, KanbusError> {
    let parent_identifier = issue.parent.clone();
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
            Ok(_paths) => {
                if regenerate_right_now {
                    regenerate_right_now_ancestors(root, parent_identifier.as_deref());
                }
                Ok(PersistIssueDeletionResult {
                    event: Some(deletion_event),
                })
            }
            Err(error) => {
                write_issue_to_file(issue, issue_path)?;
                Err(error)
            }
        }
    } else {
        if regenerate_right_now {
            regenerate_right_now_ancestors(root, parent_identifier.as_deref());
        }
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
            root: temp.path().to_path_buf(),
            before_issue: None,
            relocate_to: None,
            regenerate_right_now: false,
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
            root: temp.path().to_path_buf(),
            before_issue: None,
            relocate_to: None,
            regenerate_right_now: false,
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
            root: temp.path().to_path_buf(),
            before_issue: Some(before),
            relocate_to: None,
            regenerate_right_now: false,
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
        persist_issue_deletion(
            temp.path(),
            &project_dir,
            &issue_path,
            &issue,
            "dev",
            true,
            false,
        )
        .expect("delete");
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
        persist_issue_deletion(
            temp.path(),
            &project_dir,
            &issue_path,
            &issue,
            "dev",
            true,
            false,
        )
        .expect_err("audit write should fail");
        let restored = read_issue_from_file(&issue_path).expect("restored");
        assert_eq!(restored.title, "Keep me");
    }
}
