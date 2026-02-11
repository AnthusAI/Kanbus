//! File system helpers for initialization.

use std::path::{Path, PathBuf};
use std::process::Command;

use serde::Serialize;

use crate::config::write_default_configuration;
use crate::error::TaskulusError;

#[derive(Serialize)]
struct ProjectMarker {
    project_dir: String,
}

/// Ensure the current directory is inside a git repository.
///
/// # Arguments
///
/// * `root` - Path to validate.
///
/// # Errors
///
/// Returns `TaskulusError::Initialization` if the directory is not a git repository.
pub fn ensure_git_repository(root: &Path) -> Result<(), TaskulusError> {
    let output = Command::new("git")
        .args(["rev-parse", "--is-inside-work-tree"])
        .current_dir(root)
        .output()
        .map_err(|error| TaskulusError::Io(error.to_string()))?;

    if !output.status.success() {
        return Err(TaskulusError::Initialization(
            "not a git repository".to_string(),
        ));
    }

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout != "true" {
        return Err(TaskulusError::Initialization(
            "not a git repository".to_string(),
        ));
    }

    Ok(())
}

/// Write the project marker file.
///
/// # Arguments
///
/// * `root` - Repository root.
/// * `project_dir` - Project directory path.
///
/// # Errors
///
/// Returns `TaskulusError::Io` if writing fails.
pub fn write_project_marker(root: &Path, project_dir: &Path) -> Result<(), TaskulusError> {
    let marker_path = root.join(".taskulus.yaml");
    let marker = ProjectMarker {
        project_dir: project_dir
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string(),
    };
    let contents =
        serde_yaml::to_string(&marker).map_err(|error| TaskulusError::Io(error.to_string()))?;
    std::fs::write(marker_path, contents).map_err(|error| TaskulusError::Io(error.to_string()))
}

/// Initialize the Taskulus project structure.
///
/// # Arguments
///
/// * `root` - Repository root.
/// * `project_dir_name` - Project directory name.
///
/// # Errors
///
/// Returns `TaskulusError::Initialization` if already initialized.
pub fn initialize_project(root: &Path, project_dir_name: &str) -> Result<(), TaskulusError> {
    let marker_path = root.join(".taskulus.yaml");
    if marker_path.exists() {
        return Err(TaskulusError::Initialization(
            "already initialized".to_string(),
        ));
    }

    let project_dir = root.join(project_dir_name);
    let issues_dir = project_dir.join("issues");
    let wiki_dir = project_dir.join("wiki");

    std::fs::create_dir(&project_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;
    std::fs::create_dir(&issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;
    std::fs::create_dir(&wiki_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;

    write_default_configuration(&project_dir.join("config.yaml"))?;
    std::fs::write(wiki_dir.join("index.md"), "# Taskulus Wiki\n")
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    write_project_marker(root, &project_dir)?;

    Ok(())
}

/// Resolve the repository root for initialization.
///
/// # Arguments
///
/// * `cwd` - Current working directory.
///
/// # Returns
///
/// The root path used for initialization.
pub fn resolve_root(cwd: &Path) -> PathBuf {
    cwd.to_path_buf()
}
