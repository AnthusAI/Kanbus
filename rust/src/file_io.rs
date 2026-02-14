//! File system helpers for initialization.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::config::default_project_configuration;
use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::models::ProjectConfiguration;
use crate::project_management_template::{
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE, DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
};
use serde_yaml;

fn should_force_canonicalize_failure() -> bool {
    std::env::var_os("TASKULUS_TEST_CANONICALIZE_FAILURE").is_some()
}

pub(crate) fn canonicalize_path(path: &Path) -> Result<PathBuf, std::io::Error> {
    if should_force_canonicalize_failure() {
        return Err(std::io::Error::other("forced canonicalize failure"));
    }
    path.canonicalize()
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

/// Initialize the Taskulus project structure.
///
/// # Arguments
///
/// * `root` - Repository root.
/// * `create_local` - Whether to create project-local.
///
/// # Errors
///
/// Returns `TaskulusError::Initialization` if already initialized.
pub fn initialize_project(root: &Path, create_local: bool) -> Result<(), TaskulusError> {
    let project_dir = root.join("project");
    if project_dir.exists() {
        return Err(TaskulusError::Initialization(
            "already initialized".to_string(),
        ));
    }

    let issues_dir = project_dir.join("issues");

    std::fs::create_dir(&project_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;
    std::fs::create_dir(&issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let config_path = root.join(".taskulus.yml");
    if !config_path.exists() {
        let default_configuration = default_project_configuration();
        let contents = serde_yaml::to_string(&default_configuration)
            .map_err(|error| TaskulusError::Io(error.to_string()))?;
        std::fs::write(&config_path, contents)
            .map_err(|error| TaskulusError::Io(error.to_string()))?;
    }
    let template_path = root.join(DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME);
    if !template_path.exists() {
        std::fs::write(&template_path, DEFAULT_PROJECT_MANAGEMENT_TEMPLATE)
            .map_err(|error| TaskulusError::Io(error.to_string()))?;
    }
    write_project_guard_files(&project_dir)?;
    if create_local {
        ensure_project_local_directory(&project_dir)?;
    }

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

fn write_project_guard_files(project_dir: &Path) -> Result<(), TaskulusError> {
    let agents_path = project_dir.join("AGENTS.md");
    let agents_content = [
        "# DO NOT EDIT HERE",
        "",
        "Editing anything under project/ directly is hacking the data and is a sin against The Way.",
        "Do not read or write in this folder. Use Taskulus commands instead.",
        "",
        "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
    ]
    .join("\n")
        + "\n";
    std::fs::write(&agents_path, agents_content)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;

    let do_not_edit = project_dir.join("DO_NOT_EDIT");
    let do_not_edit_content = [
        "DO NOT EDIT ANYTHING IN project/",
        "This folder is guarded by The Way.",
        "All changes must go through Taskulus (see ../AGENTS.md and ../CONTRIBUTING_AGENT.md).",
    ]
    .join("\n")
        + "\n";
    std::fs::write(&do_not_edit, do_not_edit_content)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(())
}

/// Load a single Taskulus project directory by downward discovery.
///
/// # Arguments
///
/// * `root` - Repository root.
///
/// # Errors
///
/// Returns `TaskulusError::IssueOperation` if no project or multiple projects are found.
pub fn load_project_directory(root: &Path) -> Result<PathBuf, TaskulusError> {
    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;
    let mut dotfile_projects = discover_taskulus_projects(root)?;
    projects.append(&mut dotfile_projects);
    let mut normalized = Vec::new();
    for path in projects {
        match canonicalize_path(&path) {
            Ok(canonical) => normalized.push(canonical),
            Err(_) => normalized.push(path),
        }
    }
    normalized.sort();
    normalized.dedup();
    if normalized.is_empty() {
        return Err(TaskulusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    if normalized.len() > 1 {
        let joined = normalized
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<String>>()
            .join(", ");
        return Err(TaskulusError::IssueOperation(format!(
            "multiple projects found: {joined}. \
             Run this command from a directory with a single project/, \
             or remove extra entries from external_projects in .taskulus.yml."
        )));
    }
    Ok(normalized[0].clone())
}

/// Find a sibling project-local directory for a project.
///
/// # Arguments
///
/// * `project_dir` - Shared project directory.
pub fn find_project_local_directory(project_dir: &Path) -> Option<PathBuf> {
    let local_dir = project_dir
        .parent()
        .map(|parent| parent.join("project-local"))?;
    if local_dir.is_dir() {
        Some(local_dir)
    } else {
        None
    }
}

/// Ensure the project-local directory exists and is gitignored.
///
/// # Arguments
///
/// * `project_dir` - Shared project directory.
///
/// # Errors
///
/// Returns `TaskulusError::Io` if filesystem operations fail.
pub fn ensure_project_local_directory(project_dir: &Path) -> Result<PathBuf, TaskulusError> {
    let local_dir = project_dir
        .parent()
        .map(|parent| parent.join("project-local"))
        .ok_or_else(|| TaskulusError::Io("project-local path unavailable".to_string()))?;
    let issues_dir = local_dir.join("issues");
    std::fs::create_dir_all(&issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;
    ensure_gitignore_entry(
        project_dir
            .parent()
            .ok_or_else(|| TaskulusError::Io("project-local path unavailable".to_string()))?,
        "project-local/",
    )?;
    Ok(local_dir)
}

/// Locate the configuration file path.
///
/// # Arguments
///
/// * `root` - Path used for upward search.
///
/// # Errors
///
/// Returns `TaskulusError::IssueOperation` if the configuration file is missing.
pub fn get_configuration_path(root: &Path) -> Result<PathBuf, TaskulusError> {
    if std::env::var_os("TASKULUS_TEST_CONFIGURATION_PATH_FAILURE").is_some() {
        return Err(TaskulusError::Io(
            "configuration path lookup failed".to_string(),
        ));
    }
    let Some(path) = find_configuration_file(root)? else {
        return Err(TaskulusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    };
    Ok(path)
}

fn ensure_gitignore_entry(root: &Path, entry: &str) -> Result<(), TaskulusError> {
    let gitignore_path = root.join(".gitignore");
    let existing = if gitignore_path.exists() {
        std::fs::read_to_string(&gitignore_path)
            .map_err(|error| TaskulusError::Io(error.to_string()))?
    } else {
        String::new()
    };
    let lines: Vec<&str> = existing.lines().map(str::trim).collect();
    if lines.contains(&entry) {
        return Ok(());
    }
    let mut updated = existing;
    if !updated.is_empty() && !updated.ends_with('\n') {
        updated.push('\n');
    }
    updated.push_str(entry);
    updated.push('\n');
    std::fs::write(&gitignore_path, updated)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(())
}

/// Discover configured project paths from .taskulus.yml.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `TaskulusError` if configuration or dotfile paths are invalid.
pub fn discover_taskulus_projects(root: &Path) -> Result<Vec<PathBuf>, TaskulusError> {
    let mut projects = Vec::new();
    if let Some(config_path) = find_configuration_file(root)? {
        let configuration = load_project_configuration(&config_path)?;
        projects.extend(resolve_project_directories(
            config_path.parent().unwrap_or_else(|| Path::new("")),
            &configuration,
        )?);
    }
    Ok(projects)
}

fn find_configuration_file(root: &Path) -> Result<Option<PathBuf>, TaskulusError> {
    let git_root = find_git_root(root);
    let mut current = root
        .canonicalize()
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    loop {
        let candidate = current.join(".taskulus.yml");
        if candidate.is_file() {
            return Ok(Some(candidate));
        }
        if let Some(root) = &git_root {
            if &current == root {
                break;
            }
        }
        let parent = match current.parent() {
            Some(parent) => parent.to_path_buf(),
            None => break,
        };
        #[cfg(windows)]
        if parent == current {
            break;
        }
        current = parent;
    }
    Ok(None)
}

fn resolve_project_directories(
    base: &Path,
    configuration: &ProjectConfiguration,
) -> Result<Vec<PathBuf>, TaskulusError> {
    let mut projects = Vec::new();
    let primary = base.join(&configuration.project_directory);
    projects.push(primary);
    for extra in &configuration.external_projects {
        let candidate = Path::new(extra);
        let resolved = if candidate.is_absolute() {
            candidate.to_path_buf()
        } else {
            base.join(candidate)
        };
        if !resolved.is_dir() {
            return Err(TaskulusError::IssueOperation(format!(
                "taskulus path not found: {}",
                resolved.display()
            )));
        }
        projects.push(resolved);
    }
    Ok(projects)
}

fn find_git_root(root: &Path) -> Option<PathBuf> {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(root)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let path = PathBuf::from(stdout);
    path.is_dir().then_some(path)
}

pub(crate) fn discover_project_directories(
    root: &Path,
    projects: &mut Vec<PathBuf>,
) -> Result<(), TaskulusError> {
    for entry in std::fs::read_dir(root).map_err(|error| TaskulusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("");
        if name == "project" {
            projects.push(path);
            continue;
        }
        if name == "project-local" {
            continue;
        }
        discover_project_directories(&path, projects)?;
    }
    Ok(())
}
