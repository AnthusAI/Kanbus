//! Project discovery helpers.

use std::path::{Path, PathBuf};

use crate::error::TaskulusError;
use crate::file_io::{
    discover_project_directories as discover_project_directories_inner, discover_taskulus_projects,
    load_project_directory as load_project_directory_inner,
};

/// Discover all Taskulus project directories from the root.
///
/// # Arguments
/// * `root` - Root directory used for discovery.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if a configured project path is missing.
pub fn discover_project_directories(root: &Path) -> Result<Vec<PathBuf>, TaskulusError> {
    let mut projects = Vec::new();
    discover_project_directories_inner(root, &mut projects)?;
    let mut dotfile_projects = discover_taskulus_projects(root)?;
    projects.append(&mut dotfile_projects);
    let mut normalized = Vec::new();
    for path in projects {
        let canonical = path
            .canonicalize()
            .map_err(|error| TaskulusError::Io(error.to_string()))?;
        normalized.push(canonical);
    }
    normalized.sort();
    normalized.dedup();
    Ok(normalized)
}

/// Load a single Taskulus project directory by downward discovery.
///
/// # Arguments
/// * `root` - Root directory used for discovery.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if no project or multiple projects are found.
pub fn load_project_directory(root: &Path) -> Result<PathBuf, TaskulusError> {
    load_project_directory_inner(root)
}
