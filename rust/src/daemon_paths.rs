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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use tempfile::tempdir;

    struct ProjectRoot {
        _temp: tempfile::TempDir,
        root: std::path::PathBuf,
    }

    fn setup_project_root() -> ProjectRoot {
        let temp = tempdir().unwrap();
        let root = temp.path().join("repo");
        std::fs::create_dir_all(root.join("project")).unwrap();
        let config = default_project_configuration();
        let contents = serde_yaml::to_string(&config).unwrap();
        std::fs::write(root.join(".kanbus.yml"), contents).unwrap();
        ProjectRoot { _temp: temp, root }
    }

    #[test]
    fn resolves_daemon_socket_path() {
        let project = setup_project_root();
        let path = get_daemon_socket_path(&project.root).unwrap();
        assert!(path.ends_with(".cache/kanbus.sock"));
    }

    #[test]
    fn resolves_index_cache_path() {
        let project = setup_project_root();
        let path = get_index_cache_path(&project.root).unwrap();
        assert!(path.ends_with(".cache/index.json"));
    }

    #[test]
    fn resolves_console_state_path() {
        let project = setup_project_root();
        let path = get_console_state_path(&project.root).unwrap();
        assert!(path.ends_with(".cache/console_state.json"));
    }
}
