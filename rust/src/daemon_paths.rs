//! Daemon socket and cache paths.

use std::path::{Path, PathBuf};

use crate::file_io::{get_configuration_path, load_project_directory, resolve_labeled_projects};

/// Return the daemon socket path for a repository.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if the project marker is missing.
pub fn get_daemon_socket_path(root: &Path) -> Result<PathBuf, crate::error::KanbusError> {
    if get_configuration_path(root).is_ok() {
        let _ = resolve_labeled_projects(root)?;
    }
    let project_dir = load_project_directory(root)?;
    Ok(project_dir.join(".cache").join("kanbus.sock"))
}

/// Return the index cache path for a repository.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if the project marker is missing.
pub fn get_index_cache_path(root: &Path) -> Result<PathBuf, crate::error::KanbusError> {
    let project_dir = load_project_directory(root)?;
    Ok(project_dir.join(".cache").join("index.json"))
}

/// Return the console UI state cache path for a repository.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if the project marker is missing.
pub fn get_console_state_path(root: &Path) -> Result<PathBuf, crate::error::KanbusError> {
    let project_dir = load_project_directory(root)?;
    Ok(project_dir.join(".cache").join("console_state.json"))
}
