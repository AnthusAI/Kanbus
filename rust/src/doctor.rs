//! Environment diagnostics for Kanbus.

use std::path::{Path, PathBuf};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{ensure_git_repository, get_configuration_path, load_project_directory};

/// Result of running doctor checks.
#[derive(Debug, Clone)]
pub struct DoctorResult {
    pub project_dir: PathBuf,
}

/// Run diagnostic checks for Kanbus.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if any check fails.
pub fn run_doctor(root: &Path) -> Result<DoctorResult, KanbusError> {
    ensure_git_repository(root)?;
    let project_dir = load_project_directory(root)?;
    let configuration_path = get_configuration_path(project_dir.as_path())?;
    load_project_configuration(&configuration_path)?;
    Ok(DoctorResult { project_dir })
}
