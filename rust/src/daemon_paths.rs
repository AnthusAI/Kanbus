//! Daemon socket and cache paths.

use std::path::{Path, PathBuf};

use crate::file_io::load_project_directory;

/// Return the daemon socket path for a repository.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if the project marker is missing.
pub fn get_daemon_socket_path(root: &Path) -> Result<PathBuf, crate::error::KanbusError> {
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
