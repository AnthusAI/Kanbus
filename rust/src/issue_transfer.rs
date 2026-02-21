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
    let events_dir = events_dir_for_project(&project_dir);
    match write_events_batch(&events_dir, &[event]) {
        Ok(_paths) => {}
        Err(error) => {
            fs::rename(&target_path, &local_issue_path)
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Err(error);
        }
    }
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
    Ok(issue)
}
