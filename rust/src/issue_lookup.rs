//! Issue lookup helpers for project directories.

use std::fs;
use std::path::{Path, PathBuf};

use crate::error::KanbusError;
use crate::file_io::find_project_local_directory;
use crate::ids::issue_identifier_matches;
use crate::issue_files::{issue_path_for_identifier, read_issue_from_file};
use crate::models::IssueData;
use crate::project::discover_project_directories;

/// Issue lookup result.
#[derive(Debug)]
pub struct IssueLookupResult {
    pub issue: IssueData,
    pub issue_path: PathBuf,
    pub project_dir: PathBuf,
}

/// Load an issue by identifier from a project directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier (full or abbreviated).
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if the issue cannot be found.
pub fn load_issue_from_project(
    root: &Path,
    identifier: &str,
) -> Result<IssueLookupResult, KanbusError> {
    let project_dirs = discover_project_directories(root)?;
    if project_dirs.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }

    let mut all_matches: Vec<(String, PathBuf, PathBuf)> = Vec::new();

    for project_dir in &project_dirs {
        for issues_dir in search_directories(project_dir) {
            let issue_path = issue_path_for_identifier(&issues_dir, identifier);
            if issue_path.exists() {
                let issue = read_issue_from_file(&issue_path)?;
                return Ok(IssueLookupResult {
                    issue,
                    issue_path,
                    project_dir: project_dir.clone(),
                });
            }

            if let Ok(matches) = find_matching_issues(&issues_dir, identifier) {
                for (full_id, path) in matches {
                    all_matches.push((full_id, path, project_dir.clone()));
                }
            }
        }
    }

    match all_matches.len() {
        0 => Err(KanbusError::IssueOperation("not found".to_string())),
        1 => {
            let (_full_id, issue_path, project_dir) = all_matches.into_iter().next().unwrap();
            let issue = read_issue_from_file(&issue_path)?;
            Ok(IssueLookupResult {
                issue,
                issue_path,
                project_dir,
            })
        }
        _ => {
            let ids: Vec<String> = all_matches.into_iter().map(|(id, _, _)| id).collect();
            Err(KanbusError::IssueOperation(format!(
                "ambiguous identifier, matches: {}",
                ids.join(", ")
            )))
        }
    }
}

/// Return issue directories to search for a given project directory.
fn search_directories(project_dir: &Path) -> Vec<PathBuf> {
    let mut dirs = vec![project_dir.join("issues")];
    if let Some(local_dir) = find_project_local_directory(project_dir) {
        dirs.push(local_dir.join("issues"));
    }
    dirs
}

/// Find issues that match an abbreviated identifier.
///
/// # Arguments
/// * `issues_dir` - Path to issues directory.
/// * `identifier` - Abbreviated identifier to match.
///
/// # Returns
/// Vector of (full_id, path) tuples for matching issues.
///
/// # Errors
/// Returns `KanbusError` if directory cannot be read.
fn find_matching_issues(
    issues_dir: &Path,
    identifier: &str,
) -> Result<Vec<(String, PathBuf)>, KanbusError> {
    let mut matches = Vec::new();

    let entries = fs::read_dir(issues_dir).map_err(|error| {
        KanbusError::IssueOperation(format!("cannot read issues directory: {error}"))
    })?;

    for entry in entries {
        let entry = entry.map_err(|error| {
            KanbusError::IssueOperation(format!("cannot read directory entry: {error}"))
        })?;

        let path = entry.path();
        if !path.is_file() || path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }

        let file_stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");

        if issue_identifier_matches(identifier, file_stem) {
            matches.push((file_stem.to_string(), path));
        }
    }

    Ok(matches)
}
