//! Issue lookup helpers for project directories.

use std::path::{Path, PathBuf};

use crate::error::TaskulusError;
use crate::file_io::load_project_directory;
use crate::issue_files::{issue_path_for_identifier, read_issue_from_file};
use crate::models::IssueData;

/// Issue lookup result.
#[derive(Debug)]
pub struct IssueLookupResult {
    pub issue: IssueData,
    pub issue_path: PathBuf,
    pub project_dir: PathBuf,
}

/// Load an issue by identifier from a project directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if the issue cannot be found.
pub fn load_issue_from_project(
    root: &Path,
    identifier: &str,
) -> Result<IssueLookupResult, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let issue_path = issue_path_for_identifier(&issues_dir, identifier);
    if !issue_path.exists() {
        return Err(TaskulusError::IssueOperation("not found".to_string()));
    }
    let issue = read_issue_from_file(&issue_path)?;
    Ok(IssueLookupResult {
        issue,
        issue_path,
        project_dir,
    })
}
