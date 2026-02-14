//! Environment diagnostics for Taskulus.

use std::path::{Path, PathBuf};

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::file_io::{ensure_git_repository, load_project_directory};

/// Result of running doctor checks.
#[derive(Debug, Clone)]
pub struct DoctorResult {
    pub project_dir: PathBuf,
}

/// Run diagnostic checks for Taskulus.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `TaskulusError` if any check fails.
pub fn run_doctor(root: &Path) -> Result<DoctorResult, TaskulusError> {
    ensure_git_repository(root)?;
    let project_dir = load_project_directory(root)?;
    load_project_configuration(&project_dir.join("taskulus.yml"))?;
    Ok(DoctorResult { project_dir })
}
