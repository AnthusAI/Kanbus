#![cfg_attr(tarpaulin, skip)]
//! Issue lookup helpers for project directories.

use std::fs;
use std::path::{Path, PathBuf};

use crate::error::KanbusError;
use crate::file_io::load_project_directory;
use crate::ids::format_issue_key;
use crate::issue_files::{issue_path_for_identifier, read_issue_from_file};
use crate::models::IssueData;

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
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");

    let issue_path = issue_path_for_identifier(&issues_dir, identifier);
    if issue_path.exists() {
        let issue = read_issue_from_file(&issue_path)?;
        return Ok(IssueLookupResult {
            issue,
            issue_path,
            project_dir,
        });
    }

    let matches = find_matching_issues(&issues_dir, identifier)?;

    match matches.len() {
        0 => Err(KanbusError::IssueOperation("not found".to_string())),
        1 => {
            let (_full_id, issue_path) = matches.into_iter().next().unwrap();
            let issue = read_issue_from_file(&issue_path)?;
            Ok(IssueLookupResult {
                issue,
                issue_path,
                project_dir,
            })
        }
        _ => {
            let ids: Vec<String> = matches.into_iter().map(|(id, _)| id).collect();
            Err(KanbusError::IssueOperation(format!(
                "ambiguous identifier, matches: {}",
                ids.join(", ")
            )))
        }
    }
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

        if issue_matches(identifier, file_stem) {
            matches.push((file_stem.to_string(), path));
        }
    }

    Ok(matches)
}

/// Check if an abbreviated identifier matches a full identifier.
///
/// # Arguments
/// * `abbreviated` - Abbreviated ID (e.g., "tskl-abcdef", "custom-uuid00").
/// * `full_id` - Full ID (e.g., "tskl-abcdef2", "custom-uuid-0000001").
///
/// # Returns
/// True if abbreviated ID matches the full ID.
fn issue_matches(abbreviated: &str, full_id: &str) -> bool {
    let abbreviated_formatted = format_issue_key(full_id, false);

    if abbreviated == abbreviated_formatted {
        return true;
    }

    if abbreviated.len() >= full_id.len() {
        return false;
    }

    full_id.starts_with(abbreviated)
}
