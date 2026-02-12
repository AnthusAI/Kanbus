//! File system helpers for initialization.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::error::TaskulusError;

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
    projects.sort();
    projects.dedup();

    if projects.is_empty() {
        return Err(TaskulusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    if projects.len() > 1 {
        return Err(TaskulusError::IssueOperation(
            "multiple projects found".to_string(),
        ));
    }
    Ok(projects[0].clone())
}

/// Find a sibling project-local directory for a project.
///
/// # Arguments
///
/// * `project_dir` - Shared project directory.
pub fn find_project_local_directory(project_dir: &Path) -> Option<PathBuf> {
    let local_dir = project_dir.parent().map(|parent| parent.join("project-local"))?;
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
    std::fs::create_dir_all(&issues_dir)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    ensure_gitignore_entry(
        project_dir
            .parent()
            .ok_or_else(|| TaskulusError::Io("project-local path unavailable".to_string()))?,
        "project-local/",
    )?;
    Ok(local_dir)
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
    if lines.iter().any(|line| *line == entry) {
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

pub fn discover_taskulus_projects(root: &Path) -> Result<Vec<PathBuf>, TaskulusError> {
    let dotfile = find_taskulus_dotfile(root)?;
    let Some(dotfile) = dotfile else {
        return Ok(Vec::new());
    };
    let contents =
        std::fs::read_to_string(&dotfile).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let mut projects = Vec::new();
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let candidate = Path::new(trimmed);
        let resolved = if candidate.is_absolute() {
            candidate.to_path_buf()
        } else {
            dotfile
                .parent()
                .unwrap_or_else(|| Path::new(""))
                .join(candidate)
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

fn find_taskulus_dotfile(root: &Path) -> Result<Option<PathBuf>, TaskulusError> {
    let git_root = find_git_root(root);
    let mut current = root
        .canonicalize()
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    loop {
        let candidate = current.join(".taskulus");
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
