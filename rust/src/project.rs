//! Project discovery helpers.

use std::path::{Path, PathBuf};

use crate::error::KanbusError;
use crate::file_io::{
    discover_kanbus_projects, discover_project_directories as discover_project_directories_inner,
    load_project_directory as load_project_directory_inner,
};

/// Discover all Kanbus project directories from the root.
///
/// # Arguments
/// * `root` - Root directory used for discovery.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if a configured project path is missing.
pub fn discover_project_directories(root: &Path) -> Result<Vec<PathBuf>, KanbusError> {
    let mut projects = Vec::new();
    discover_project_directories_inner(root, &mut projects)?;
    let mut dotfile_projects = discover_kanbus_projects(root)?;
    projects.append(&mut dotfile_projects);
    let mut normalized = Vec::new();
    for path in projects {
        let canonical = path
            .canonicalize()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        normalized.push(canonical);
    }
    normalized.sort();
    normalized.dedup();
    Ok(normalized)
}

/// Load a single Kanbus project directory by downward discovery.
///
/// # Arguments
/// * `root` - Root directory used for discovery.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if no project or multiple projects are found.
pub fn load_project_directory(root: &Path) -> Result<PathBuf, KanbusError> {
    load_project_directory_inner(root)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn write_config(root: &Path) {
        fs::write(
            root.join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\n",
        )
        .expect("write config");
        fs::create_dir_all(root.join("project/issues")).expect("create project issues");
    }

    #[test]
    fn discover_project_directories_normalizes_and_deduplicates() {
        let tmp = tempfile::tempdir().expect("tempdir");
        write_config(tmp.path());
        let discovered = discover_project_directories(tmp.path()).expect("discover");
        assert_eq!(discovered.len(), 1);
        assert_eq!(
            discovered[0],
            tmp.path()
                .join("project")
                .canonicalize()
                .expect("canonical project")
        );
    }

    #[test]
    fn discover_project_directories_returns_io_when_path_canonicalize_fails() {
        let tmp = tempfile::tempdir().expect("tempdir");
        fs::write(
            tmp.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: missing-project\n",
        )
        .expect("write config");
        let result = discover_project_directories(tmp.path());
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert!(message.contains("kanbus path not found"))
            }
            other => panic!("expected issue operation error, got {other:?}"),
        }
    }

    #[test]
    fn load_project_directory_delegates_to_file_io() {
        let tmp = tempfile::tempdir().expect("tempdir");
        write_config(tmp.path());
        let loaded = load_project_directory(tmp.path()).expect("load project dir");
        assert_eq!(
            loaded,
            tmp.path()
                .join("project")
                .canonicalize()
                .expect("canonical project")
        );
    }
}
