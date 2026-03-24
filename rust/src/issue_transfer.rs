//! Local and shared issue transfer helpers.

use std::fs;
use std::path::Path;

use crate::error::KanbusError;
use crate::event_history::{
    events_dir_for_local, events_dir_for_project, now_timestamp, transfer_payload,
    write_events_batch, EventRecord, EventType,
};
use crate::file_io::{ensure_project_local_directory, find_project_local_directory};
use crate::issue_files::read_issue_from_file;
use crate::issue_lookup::load_issue_from_project;
use crate::models::IssueData;
use crate::users::get_current_user;

/// Promote a local issue into the shared project directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if promotion fails.
pub fn promote_issue(root: &Path, identifier: &str) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let project_dir = lookup.project_dir;

    let local_dir = find_project_local_directory(&project_dir)
        .ok_or_else(|| KanbusError::IssueOperation("project-local not initialized".to_string()))?;

    let local_issue_path = local_dir.join("issues").join(format!("{identifier}.json"));
    if !local_issue_path.exists() {
        return Err(KanbusError::IssueOperation(
            "issue is not in project-local".to_string(),
        ));
    }

    let target_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    if target_path.exists() {
        return Err(KanbusError::IssueOperation("already exists".to_string()));
    }

    let issue = read_issue_from_file(&local_issue_path)?;
    fs::rename(&local_issue_path, &target_path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    let occurred_at = now_timestamp();
    let actor_id = get_current_user();
    let event = EventRecord::new(
        issue.identifier.clone(),
        EventType::IssuePromoted,
        actor_id,
        transfer_payload("local", "shared"),
        occurred_at,
    );
    let event_id = event.event_id.clone();
    let events_dir = events_dir_for_project(&project_dir);
    match write_events_batch(&events_dir, &[event]) {
        Ok(_paths) => {}
        Err(error) => {
            fs::rename(&target_path, &local_issue_path)
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Err(error);
        }
    }
    crate::gossip::publish_issue_mutation(
        root,
        &project_dir,
        &issue,
        Some(event_id),
        "issue.mutated",
    );
    Ok(issue)
}

/// Move a shared issue into the project-local directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if localization fails.
pub fn localize_issue(root: &Path, identifier: &str) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let project_dir = lookup.project_dir;
    let shared_issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    if !shared_issue_path.exists() {
        return Err(KanbusError::IssueOperation(
            "issue is not in shared project".to_string(),
        ));
    }

    let local_dir = ensure_project_local_directory(&project_dir)?;
    let target_path = local_dir.join("issues").join(format!("{identifier}.json"));
    if target_path.exists() {
        return Err(KanbusError::IssueOperation("already exists".to_string()));
    }

    let issue = read_issue_from_file(&shared_issue_path)?;
    fs::rename(&shared_issue_path, &target_path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    let occurred_at = now_timestamp();
    let actor_id = get_current_user();
    let event = EventRecord::new(
        issue.identifier.clone(),
        EventType::IssueLocalized,
        actor_id,
        transfer_payload("shared", "local"),
        occurred_at,
    );
    let event_id = event.event_id.clone();
    let events_dir = match events_dir_for_local(&project_dir) {
        Ok(path) => path,
        Err(error) => {
            fs::rename(&target_path, &shared_issue_path)
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Err(error);
        }
    };
    match write_events_batch(&events_dir, &[event]) {
        Ok(_paths) => {}
        Err(error) => {
            fs::rename(&target_path, &shared_issue_path)
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Err(error);
        }
    }
    crate::gossip::publish_issue_deleted(root, &project_dir, &issue.identifier, Some(event_id));
    Ok(issue)
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::collections::BTreeMap;

    fn write_project_config(root: &Path) {
        fs::write(
            root.join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\n",
        )
        .expect("write config");
        fs::create_dir_all(root.join("project/issues")).expect("create shared issues dir");
    }

    fn make_issue(id: &str) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: format!("Issue {id}"),
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
            custom: BTreeMap::new(),
        }
    }

    fn write_issue(path: &Path, id: &str) {
        let issue = make_issue(id);
        fs::create_dir_all(path.parent().expect("issue parent")).expect("create issue parent");
        fs::write(
            path,
            serde_json::to_string_pretty(&issue).expect("serialize issue"),
        )
        .expect("write issue");
    }

    #[test]
    fn localize_issue_moves_shared_issue_to_project_local() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        let shared_path = temp.path().join("project/issues/kanbus-1.json");
        write_issue(&shared_path, "kanbus-1");

        let localized = localize_issue(temp.path(), "kanbus-1").expect("localize issue");
        assert_eq!(localized.identifier, "kanbus-1");
        assert!(!shared_path.exists());
        assert!(temp
            .path()
            .join("project-local/issues/kanbus-1.json")
            .exists());
    }

    #[test]
    fn promote_issue_moves_local_issue_to_shared_project() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        let local_path = temp.path().join("project-local/issues/kanbus-1.json");
        write_issue(&local_path, "kanbus-1");

        let promoted = promote_issue(temp.path(), "kanbus-1").expect("promote issue");
        assert_eq!(promoted.identifier, "kanbus-1");
        assert!(!local_path.exists());
        assert!(temp.path().join("project/issues/kanbus-1.json").exists());
    }

    #[test]
    fn localize_issue_rejects_when_target_already_exists() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        write_issue(
            &temp.path().join("project/issues/kanbus-1.json"),
            "kanbus-1",
        );
        write_issue(
            &temp.path().join("project-local/issues/kanbus-1.json"),
            "kanbus-1",
        );

        let result = localize_issue(temp.path(), "kanbus-1");
        match result {
            Err(KanbusError::IssueOperation(message)) => assert_eq!(message, "already exists"),
            other => panic!("expected already exists error, got {other:?}"),
        }
    }

    #[test]
    fn promote_issue_rejects_when_target_already_exists() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        write_issue(
            &temp.path().join("project/issues/kanbus-1.json"),
            "kanbus-1",
        );
        write_issue(
            &temp.path().join("project-local/issues/kanbus-1.json"),
            "kanbus-1",
        );

        let result = promote_issue(temp.path(), "kanbus-1");
        match result {
            Err(KanbusError::IssueOperation(message)) => assert_eq!(message, "already exists"),
            other => panic!("expected already exists error, got {other:?}"),
        }
    }

    #[test]
    fn localize_issue_rejects_when_issue_is_only_in_project_local() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        write_issue(
            &temp.path().join("project-local/issues/kanbus-1.json"),
            "kanbus-1",
        );

        let result = localize_issue(temp.path(), "kanbus-1");
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "issue is not in shared project")
            }
            other => panic!("expected shared project error, got {other:?}"),
        }
    }

    #[test]
    fn promote_issue_rejects_when_identifier_is_missing() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());

        let result = promote_issue(temp.path(), "kanbus-1");
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "not found")
            }
            other => panic!("expected not found error, got {other:?}"),
        }
    }

    #[test]
    fn promote_issue_rejects_when_issue_not_in_project_local() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        fs::create_dir_all(temp.path().join("project-local/issues")).expect("create local issues");
        write_issue(
            &temp.path().join("project/issues/kanbus-1.json"),
            "kanbus-1",
        );

        let result = promote_issue(temp.path(), "kanbus-1");
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "issue is not in project-local")
            }
            other => panic!("expected local source error, got {other:?}"),
        }
    }

    #[test]
    fn localize_and_promote_return_io_error_for_invalid_issue_json() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        fs::create_dir_all(temp.path().join("project/issues")).expect("create shared issues");
        fs::create_dir_all(temp.path().join("project-local/issues")).expect("create local issues");

        fs::write(
            temp.path().join("project/issues/kanbus-shared.json"),
            "{bad json",
        )
        .expect("write invalid shared issue");
        fs::write(
            temp.path().join("project-local/issues/kanbus-local.json"),
            "{bad json",
        )
        .expect("write invalid local issue");

        let localize = localize_issue(temp.path(), "kanbus-shared")
            .expect_err("localize should fail for invalid json");
        assert!(matches!(localize, KanbusError::Io(_)));

        let promote = promote_issue(temp.path(), "kanbus-local")
            .expect_err("promote should fail for invalid json");
        assert!(matches!(promote, KanbusError::Io(_)));
    }
}
