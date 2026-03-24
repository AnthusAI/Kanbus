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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use crate::error::KanbusError;
    use std::fs;
    use tempfile::TempDir;

    fn write_minimal_project(root: &Path) {
        let project_dir = root.join("project");
        fs::create_dir_all(project_dir.join("issues")).expect("create issues dir");
        let config = default_project_configuration();
        let yaml = serde_yaml::to_string(&config).expect("serialize config");
        fs::write(root.join(".kanbus.yml"), yaml).expect("write config");
    }

    #[test]
    fn paths_resolve_inside_project_cache_directory() {
        let temp = TempDir::new().expect("tempdir");
        write_minimal_project(temp.path());

        let socket = get_daemon_socket_path(temp.path()).expect("socket path");
        let index = get_index_cache_path(temp.path()).expect("index path");
        let console = get_console_state_path(temp.path()).expect("console state path");

        assert!(socket.ends_with(".cache/kanbus.sock"));
        assert!(index.ends_with(".cache/index.json"));
        assert!(console.ends_with(".cache/console_state.json"));
        assert!(index.parent().is_some());
        assert!(console.parent().is_some());
    }

    #[test]
    fn errors_when_project_marker_missing() {
        let temp = TempDir::new().expect("tempdir");
        let error = get_daemon_socket_path(temp.path()).expect_err("expected missing project");
        match error {
            KanbusError::IssueOperation(message) => {
                assert!(message.contains("project"));
            }
            other => panic!("unexpected error type: {other:?}"),
        }
    }
}
