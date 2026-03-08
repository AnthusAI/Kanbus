//! File system helpers for initialization.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::config::default_project_configuration;
use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::models::ProjectConfiguration;
use crate::project_management_template::{
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE, DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
};
use serde_json;
use serde_yaml;

/// A resolved project directory with its label.
#[derive(Debug, Clone)]
pub struct ResolvedProject {
    pub label: String,
    pub project_dir: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RepairPlan {
    pub project_dir: PathBuf,
    pub missing_project_dir: bool,
    pub missing_issues_dir: bool,
    pub missing_events_dir: bool,
}

const WORKSPACE_IGNORE_DIRS: [&str; 11] = [
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "project",
    "project-local",
    "target",
];

const LEGACY_DISCOVERY_IGNORE_DIRS: [&str; 10] = [
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "project-local",
    "target",
];

fn should_force_canonicalize_failure() -> bool {
    std::env::var_os("KANBUS_TEST_CANONICALIZE_FAILURE").is_some()
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
/// Returns `KanbusError::Initialization` if the directory is not a git repository.
pub fn ensure_git_repository(root: &Path) -> Result<(), KanbusError> {
    let output = Command::new("git")
        .args(["rev-parse", "--is-inside-work-tree"])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    if !output.status.success() {
        return Err(KanbusError::Initialization(
            "not a git repository".to_string(),
        ));
    }

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout != "true" {
        return Err(KanbusError::Initialization(
            "not a git repository".to_string(),
        ));
    }

    Ok(())
}

/// Initialize the Kanbus project structure.
///
/// # Arguments
///
/// * `root` - Repository root.
/// * `create_local` - Whether to create project-local.
///
/// # Errors
///
/// Returns `KanbusError::Initialization` if already initialized.
pub fn initialize_project(root: &Path, create_local: bool) -> Result<(), KanbusError> {
    let project_dir = root.join("project");
    if project_dir.exists() {
        return Err(KanbusError::Initialization(
            "already initialized".to_string(),
        ));
    }

    let issues_dir = project_dir.join("issues");
    let events_dir = project_dir.join("events");

    std::fs::create_dir(&project_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    std::fs::create_dir(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    std::fs::create_dir(&events_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let config_path = root.join(".kanbus.yml");
    if !config_path.exists() {
        let default_configuration = default_project_configuration();
        let contents = serde_yaml::to_string(&default_configuration)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        std::fs::write(&config_path, contents)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let template_path = root.join(DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME);
    if !template_path.exists() {
        std::fs::write(&template_path, DEFAULT_PROJECT_MANAGEMENT_TEMPLATE)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    write_project_guard_files(&project_dir)?;
    write_tool_block_files(root)?;
    ensure_gitignore_entry(root, "project/.overlay/")?;
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

fn write_guard_files_in_subdir(subdir: &Path, folder_name: &str) -> Result<(), KanbusError> {
    let agents_path = subdir.join("AGENTS.md");
    let agents_content = [
        "# DO NOT EDIT HERE",
        "",
        &format!(
            "Do not read or write in this folder ({}/). Use Kanbus commands instead.",
            folder_name
        ),
        "Do not inspect issue JSON with tools like cat or jq.",
        "",
        "See ../../AGENTS.md and ../../CONTRIBUTING_AGENT.md for required process.",
    ]
    .join("\n")
        + "\n";
    std::fs::write(&agents_path, agents_content)
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    let do_not_edit = subdir.join("DO_NOT_EDIT");
    let do_not_edit_content = [
        &format!("DO NOT EDIT THIS FOLDER ({}/)", folder_name),
        "This folder is guarded by The Way.",
        "All changes must go through Kanbus (see ../../AGENTS.md and ../../CONTRIBUTING_AGENT.md).",
    ]
    .join("\n")
        + "\n";
    std::fs::write(&do_not_edit, do_not_edit_content)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}

fn write_project_guard_files(project_dir: &Path) -> Result<(), KanbusError> {
    let issues_dir = project_dir.join("issues");
    let events_dir = project_dir.join("events");
    if issues_dir.exists() {
        write_guard_files_in_subdir(&issues_dir, "issues")?;
    }
    if events_dir.exists() {
        write_guard_files_in_subdir(&events_dir, "events")?;
    }
    let root_agents_path = project_dir.join("AGENTS.md");
    let root_content = [
        "# Project directory",
        "",
        "Do not edit issues/ or events/ directly; use Kanbus for issues and events.",
        "You may edit wiki/ (e.g. Markdown) directly.",
        "",
        "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
    ]
    .join("\n")
        + "\n";
    std::fs::write(&root_agents_path, root_content)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}

fn write_project_guard_files_if_missing(project_dir: &Path) -> Result<(), KanbusError> {
    let issues_dir = project_dir.join("issues");
    let events_dir = project_dir.join("events");
    for (subdir, folder_name) in [(&issues_dir, "issues"), (&events_dir, "events")] {
        if !subdir.exists() {
            continue;
        }
        let agents_path = subdir.join("AGENTS.md");
        let do_not_edit = subdir.join("DO_NOT_EDIT");
        if !agents_path.exists() || !do_not_edit.exists() {
            write_guard_files_in_subdir(subdir, folder_name)?;
        }
    }
    let root_agents_path = project_dir.join("AGENTS.md");
    if !root_agents_path.exists() {
        let root_content = [
            "# Project directory",
            "",
            "Do not edit issues/ or events/ directly; use Kanbus for issues and events.",
            "You may edit wiki/ (e.g. Markdown) directly.",
            "",
            "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
        ]
        .join("\n")
            + "\n";
        std::fs::write(&root_agents_path, root_content)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(())
}

fn write_tool_block_files(root: &Path) -> Result<(), KanbusError> {
    let cursorignore = root.join(".cursorignore");
    if !cursorignore.exists() {
        std::fs::write(&cursorignore, "project/issues/\nproject/events/\n")
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }

    let claude_dir = root.join(".claude");
    std::fs::create_dir_all(&claude_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let claude_settings = claude_dir.join("settings.json");
    if !claude_settings.exists() {
        let payload = serde_json::json!({
            "permissions": {
                "deny": [
                    "Read(./project/issues/**)",
                    "Edit(./project/issues/**)",
                    "Read(./project/events/**)",
                    "Edit(./project/events/**)"
                ]
            }
        });
        let content = serde_json::to_string_pretty(&payload)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        std::fs::write(&claude_settings, format!("{}\n", content))
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }

    let vscode_dir = root.join(".vscode");
    std::fs::create_dir_all(&vscode_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let vscode_settings = vscode_dir.join("settings.json");
    if !vscode_settings.exists() {
        let payload = serde_json::json!({
            "files.exclude": {"**/project/issues/**": true, "**/project/events/**": true},
            "files.watcherExclude": {"**/project/issues/**": true, "**/project/events/**": true},
            "search.exclude": {"**/project/issues/**": true, "**/project/events/**": true},
        });
        let content = serde_json::to_string_pretty(&payload)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        std::fs::write(&vscode_settings, format!("{}\n", content))
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(())
}

/// Load a single Kanbus project directory by downward discovery.
///
/// # Arguments
///
/// * `root` - Repository root.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` if no project or multiple projects are found.
pub fn load_project_directory(root: &Path) -> Result<PathBuf, KanbusError> {
    // When a config file is found, derive the primary project directory from it.
    // Virtual project directories are for reading and lookup only — including
    // them here causes "multiple projects found" errors for write operations.
    if let Ok(config_path) = get_configuration_path(root) {
        if let Ok(configuration) = load_project_configuration(&config_path) {
            let base = config_path.parent().unwrap_or_else(|| Path::new(""));
            let primary = base.join(&configuration.project_directory);
            if is_path_ignored(&primary, base, &configuration.ignore_paths) {
                return Err(KanbusError::IssueOperation(
                    "project not initialized".to_string(),
                ));
            }
            return Ok(match canonicalize_path(&primary) {
                Ok(p) => p,
                Err(_) => primary,
            });
        }
    }

    // No config file — fall back to filesystem scanning.
    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;

    let mut normalized = Vec::new();
    for path in projects {
        match canonicalize_path(&path) {
            Ok(canonical) => normalized.push(canonical),
            Err(_) => normalized.push(path),
        }
    }
    normalized.sort();
    normalized.dedup();
    filter_and_validate_projects(normalized)
}

pub fn detect_repairable_project_issues(
    root: &Path,
    allow_uninitialized: bool,
) -> Result<Option<RepairPlan>, KanbusError> {
    let config_path = match get_configuration_path(root) {
        Ok(path) => path,
        Err(KanbusError::IssueOperation(message)) if message == "project not initialized" => {
            if allow_uninitialized {
                return Ok(None);
            }
            return Err(KanbusError::IssueOperation(message));
        }
        Err(KanbusError::Io(message)) if message == "configuration path lookup failed" => {
            if allow_uninitialized {
                return Ok(None);
            }
            return Err(KanbusError::Io(message));
        }
        Err(error) => return Err(error),
    };
    let configuration = load_project_configuration(&config_path)?;
    let base = config_path.parent().unwrap_or_else(|| Path::new(""));
    let project_dir = base.join(&configuration.project_directory);
    let missing_project_dir = !project_dir.exists();
    let issues_dir = project_dir.join("issues");
    let events_dir = project_dir.join("events");
    let missing_issues_dir = !issues_dir.exists();
    let missing_events_dir = !events_dir.exists();

    if missing_project_dir || missing_issues_dir || missing_events_dir {
        return Ok(Some(RepairPlan {
            project_dir,
            missing_project_dir,
            missing_issues_dir,
            missing_events_dir,
        }));
    }

    Ok(None)
}

pub fn repair_project_structure(plan: &RepairPlan) -> Result<(), KanbusError> {
    if plan.missing_project_dir {
        std::fs::create_dir_all(&plan.project_dir)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    if plan.missing_issues_dir {
        std::fs::create_dir_all(plan.project_dir.join("issues"))
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    if plan.missing_events_dir {
        std::fs::create_dir_all(plan.project_dir.join("events"))
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    if plan.project_dir.exists() {
        write_project_guard_files_if_missing(&plan.project_dir)?;
    }
    Ok(())
}

fn filter_and_validate_projects(normalized: Vec<PathBuf>) -> Result<PathBuf, KanbusError> {
    if normalized.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    if normalized.len() > 1 {
        let joined = normalized
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<String>>()
            .join(", ");
        return Err(KanbusError::IssueOperation(format!(
            "multiple projects found: {joined}. \
             Run this command from a directory with a single project/, \
             or remove extra entries from virtual_projects in .kanbus.yml."
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
/// Returns `KanbusError::Io` if filesystem operations fail.
pub fn ensure_project_local_directory(project_dir: &Path) -> Result<PathBuf, KanbusError> {
    let local_dir = project_dir
        .parent()
        .map(|parent| parent.join("project-local"))
        .ok_or_else(|| KanbusError::Io("project-local path unavailable".to_string()))?;
    let issues_dir = local_dir.join("issues");
    let events_dir = local_dir.join("events");
    std::fs::create_dir_all(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    std::fs::create_dir_all(&events_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    ensure_gitignore_entry(
        project_dir
            .parent()
            .ok_or_else(|| KanbusError::Io("project-local path unavailable".to_string()))?,
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
/// Returns `KanbusError::IssueOperation` if the configuration file is missing.
pub fn get_configuration_path(root: &Path) -> Result<PathBuf, KanbusError> {
    if std::env::var_os("KANBUS_TEST_CONFIGURATION_PATH_FAILURE").is_some() {
        return Err(KanbusError::Io(
            "configuration path lookup failed".to_string(),
        ));
    }
    let Some(path) = find_configuration_file(root)? else {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    };
    Ok(path)
}

fn ensure_gitignore_entry(root: &Path, entry: &str) -> Result<(), KanbusError> {
    let gitignore_path = root.join(".gitignore");
    let existing = if gitignore_path.exists() {
        std::fs::read_to_string(&gitignore_path)
            .map_err(|error| KanbusError::Io(error.to_string()))?
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
    std::fs::write(&gitignore_path, updated).map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}

/// Discover configured project paths from .kanbus.yml.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if configuration or dotfile paths are invalid.
pub fn discover_kanbus_projects(root: &Path) -> Result<Vec<PathBuf>, KanbusError> {
    let mut projects = Vec::new();
    let config_path = root.join(".kanbus.yml");
    if !config_path.is_file() {
        return Ok(projects);
    }
    let configuration = load_project_configuration(&config_path)?;
    let resolved = resolve_project_directories(
        config_path.parent().unwrap_or_else(|| Path::new("")),
        &configuration,
    )?;
    projects.extend(resolved.into_iter().map(|rp| rp.project_dir));
    Ok(projects)
}

/// Resolve all labeled project directories from configuration.
///
/// # Arguments
///
/// * `root` - Repository root.
///
/// # Errors
///
/// Returns `KanbusError` if configuration or paths are invalid.
pub fn resolve_labeled_projects(root: &Path) -> Result<Vec<ResolvedProject>, KanbusError> {
    let config_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&config_path)?;
    resolve_project_directories(
        config_path.parent().unwrap_or_else(|| Path::new("")),
        &configuration,
    )
}

fn find_configuration_file(root: &Path) -> Result<Option<PathBuf>, KanbusError> {
    let mut current = Some(root);
    while let Some(dir) = current {
        let candidate = dir.join(".kanbus.yml");
        if candidate.is_file() {
            return Ok(Some(candidate));
        }
        current = dir.parent();
    }
    Ok(None)
}

fn resolve_project_directories(
    base: &Path,
    configuration: &ProjectConfiguration,
) -> Result<Vec<ResolvedProject>, KanbusError> {
    let mut projects = Vec::new();
    let primary = base.join(&configuration.project_directory);
    if !is_path_ignored(&primary, base, &configuration.ignore_paths) {
        projects.push(ResolvedProject {
            label: configuration.project_key.clone(),
            project_dir: primary,
        });
    }
    for (label, vp) in &configuration.virtual_projects {
        let candidate = Path::new(&vp.path);
        let resolved = if candidate.is_absolute() {
            candidate.to_path_buf()
        } else {
            base.join(candidate)
        };
        if !resolved.is_dir() {
            return Err(KanbusError::IssueOperation(format!(
                "virtual project path not found: {}",
                resolved.display()
            )));
        }
        if !is_path_ignored(&resolved, base, &configuration.ignore_paths) {
            projects.push(ResolvedProject {
                label: label.clone(),
                project_dir: resolved,
            });
        }
    }
    Ok(projects)
}

pub(crate) fn is_path_ignored(path: &Path, base: &Path, ignore_paths: &[String]) -> bool {
    for ignore_pattern in ignore_paths {
        let ignore_path = base.join(ignore_pattern);
        if let Ok(ignore_canonical) = ignore_path.canonicalize() {
            if let Ok(path_canonical) = path.canonicalize() {
                if path_canonical == ignore_canonical {
                    return true;
                }
            }
        }
    }
    false
}

pub(crate) fn discover_project_directories(
    root: &Path,
    projects: &mut Vec<PathBuf>,
) -> Result<(), KanbusError> {
    let config_path = root.join(".kanbus.yml");
    if config_path.is_file() {
        let configuration = load_project_configuration(&config_path)?;
        let resolved = resolve_project_directories(
            config_path.parent().unwrap_or_else(|| Path::new("")),
            &configuration,
        )?;
        for rp in resolved {
            if !rp.project_dir.is_dir() {
                return Err(KanbusError::IssueOperation(format!(
                    "kanbus path not found: {}",
                    rp.project_dir.display()
                )));
            }
            projects.push(rp.project_dir);
        }
        return Ok(());
    }

    let workspace_configs = discover_workspace_config_paths(root)?;
    for config_path in workspace_configs {
        let configuration = match load_project_configuration(&config_path) {
            Ok(configuration) => configuration,
            Err(_) => continue,
        };
        let resolved = match resolve_project_directories(
            config_path.parent().unwrap_or_else(|| Path::new("")),
            &configuration,
        ) {
            Ok(resolved) => resolved,
            Err(_) => continue,
        };
        for rp in resolved {
            if rp.project_dir.is_dir() {
                projects.push(rp.project_dir);
            }
        }
    }

    if projects.is_empty() {
        discover_legacy_project_directories(root, projects)?;
    }
    Ok(())
}

fn discover_legacy_project_directories(
    root: &Path,
    projects: &mut Vec<PathBuf>,
) -> Result<(), KanbusError> {
    if root.is_dir() {
        if let Some(name) = root.file_name().and_then(|value| value.to_str()) {
            if name == "project" {
                projects.push(root.to_path_buf());
            }
        }
    }
    let mut stack = vec![root.to_path_buf()];
    while let Some(current) = stack.pop() {
        let entries = match std::fs::read_dir(&current) {
            Ok(entries) => entries,
            Err(error) => {
                if current == root {
                    return Err(KanbusError::Io(error.to_string()));
                }
                continue;
            }
        };

        for entry in entries {
            let entry = match entry {
                Ok(entry) => entry,
                Err(error) => {
                    if current == root {
                        return Err(KanbusError::Io(error.to_string()));
                    }
                    continue;
                }
            };
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            if entry.file_type().map(|ft| ft.is_symlink()).unwrap_or(false) {
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
            if LEGACY_DISCOVERY_IGNORE_DIRS.contains(&name) {
                continue;
            }
            stack.push(path);
        }
    }
    Ok(())
}

fn discover_workspace_config_paths(root: &Path) -> Result<Vec<PathBuf>, KanbusError> {
    let mut configs = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(current) = stack.pop() {
        let entries = match std::fs::read_dir(&current) {
            Ok(entries) => entries,
            Err(error) => {
                if current == root {
                    return Err(KanbusError::Io(error.to_string()));
                }
                continue;
            }
        };

        let config_path = current.join(".kanbus.yml");
        if config_path.is_file() {
            configs.push(config_path);
        }

        for entry in entries {
            let entry = match entry {
                Ok(entry) => entry,
                Err(error) => {
                    if current == root {
                        return Err(KanbusError::Io(error.to_string()));
                    }
                    continue;
                }
            };
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            if entry.file_type().map(|ft| ft.is_symlink()).unwrap_or(false) {
                continue;
            }
            let name = path
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or("");
            if WORKSPACE_IGNORE_DIRS.contains(&name) {
                continue;
            }
            stack.push(path);
        }
    }
    configs.sort();
    Ok(configs)
}

#[cfg(test)]
mod tests {
    use super::get_configuration_path;
    use crate::error::KanbusError;
    use std::fs;

    #[test]
    fn configuration_path_is_discovered_in_parent_directories() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let root = tempdir.path();
        let nested = root.join("project").join("issues");
        fs::create_dir_all(&nested).expect("create nested path");
        fs::write(root.join(".kanbus.yml"), "project_key: kbs\n").expect("write config");

        let found = get_configuration_path(&nested).expect("configuration should resolve upward");

        assert_eq!(found, root.join(".kanbus.yml"));
    }

    #[test]
    fn configuration_path_reports_uninitialized_when_missing() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let nested = tempdir.path().join("project").join("issues");
        fs::create_dir_all(&nested).expect("create nested path");

        let error = get_configuration_path(&nested).expect_err("missing config should fail");
        assert!(matches!(
            error,
            KanbusError::IssueOperation(message) if message == "project not initialized"
        ));
    }
}
