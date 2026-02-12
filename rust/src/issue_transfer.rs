//! Local and shared issue transfer helpers.

use std::fs;
use std::path::Path;

use crate::error::TaskulusError;
use crate::file_io::{ensure_project_local_directory, find_project_local_directory, load_project_directory};
use crate::issue_files::read_issue_from_file;
use crate::models::IssueData;

/// Promote a local issue into the shared project directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if promotion fails.
pub fn promote_issue(root: &Path, identifier: &str) -> Result<IssueData, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let local_dir = find_project_local_directory(&project_dir)
        .ok_or_else(|| TaskulusError::IssueOperation("project-local not initialized".to_string()))?;

    let local_issue_path = local_dir.join("issues").join(format!("{identifier}.json"));
    if !local_issue_path.exists() {
        return Err(TaskulusError::IssueOperation("not found".to_string()));
    }

    let target_path = project_dir.join("issues").join(format!("{identifier}.json"));
    if target_path.exists() {
        return Err(TaskulusError::IssueOperation("already exists".to_string()));
    }

    let issue = read_issue_from_file(&local_issue_path)?;
    fs::rename(&local_issue_path, &target_path)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(issue)
}

/// Move a shared issue into the project-local directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if localization fails.
pub fn localize_issue(root: &Path, identifier: &str) -> Result<IssueData, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let shared_issue_path = project_dir.join("issues").join(format!("{identifier}.json"));
    if !shared_issue_path.exists() {
        return Err(TaskulusError::IssueOperation("not found".to_string()));
    }

    let local_dir = ensure_project_local_directory(&project_dir)?;
    let target_path = local_dir.join("issues").join(format!("{identifier}.json"));
    if target_path.exists() {
        return Err(TaskulusError::IssueOperation("already exists".to_string()));
    }

    let issue = read_issue_from_file(&shared_issue_path)?;
    fs::rename(&shared_issue_path, &target_path)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(issue)
}
