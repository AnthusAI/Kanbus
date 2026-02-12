//! Issue file input/output helpers.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use crate::error::TaskulusError;
use crate::models::IssueData;

/// List issue identifiers based on JSON filenames.
///
/// # Arguments
/// * `issues_directory` - Directory containing issue files.
///
/// # Errors
/// Returns `TaskulusError::Io` if directory entries cannot be read.
pub fn list_issue_identifiers(issues_directory: &Path) -> Result<HashSet<String>, TaskulusError> {
    let mut identifiers = HashSet::new();
    for entry in
        fs::read_dir(issues_directory).map_err(|error| TaskulusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        if let Some(stem) = path.file_stem().and_then(|name| name.to_str()) {
            identifiers.insert(stem.to_string());
        }
    }
    Ok(identifiers)
}

/// Read an issue from a JSON file.
///
/// # Arguments
/// * `issue_path` - Path to the issue JSON file.
///
/// # Errors
/// Returns `TaskulusError::Io` if reading or parsing fails.
pub fn read_issue_from_file(issue_path: &Path) -> Result<IssueData, TaskulusError> {
    let contents = fs::read(issue_path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let issue: IssueData =
        serde_json::from_slice(&contents).map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(issue)
}

/// Write an issue to a JSON file with pretty formatting.
///
/// # Arguments
/// * `issue` - Issue data to serialize.
/// * `issue_path` - Path to the issue JSON file.
///
/// # Errors
/// Returns `TaskulusError::Io` if writing fails.
pub fn write_issue_to_file(issue: &IssueData, issue_path: &Path) -> Result<(), TaskulusError> {
    let contents = serde_json::to_string_pretty(issue)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    fs::write(issue_path, contents).map_err(|error| TaskulusError::Io(error.to_string()))
}

/// Resolve an issue file path by identifier.
///
/// # Arguments
/// * `issues_directory` - Directory containing issue files.
/// * `identifier` - Issue identifier.
pub fn issue_path_for_identifier(issues_directory: &Path, identifier: &str) -> PathBuf {
    issues_directory.join(format!("{identifier}.json"))
}
