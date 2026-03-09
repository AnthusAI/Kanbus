//! Issue file input/output helpers.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use crate::error::KanbusError;
use crate::models::IssueData;

/// List issue identifiers based on JSON filenames.
///
/// # Arguments
/// * `issues_directory` - Directory containing issue files.
///
/// # Errors
/// Returns `KanbusError::Io` if directory entries cannot be read.
pub fn list_issue_identifiers(issues_directory: &Path) -> Result<HashSet<String>, KanbusError> {
    let mut identifiers = HashSet::new();
    for entry in
        fs::read_dir(issues_directory).map_err(|error| KanbusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
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
/// Returns `KanbusError::Io` if reading or parsing fails.
pub fn read_issue_from_file(issue_path: &Path) -> Result<IssueData, KanbusError> {
    let contents = fs::read(issue_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let issue: IssueData =
        serde_json::from_slice(&contents).map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(issue)
}

/// Write an issue to a JSON file with pretty formatting.
///
/// # Arguments
/// * `issue` - Issue data to serialize.
/// * `issue_path` - Path to the issue JSON file.
///
/// # Errors
/// Returns `KanbusError::Io` if writing fails.
pub fn write_issue_to_file(issue: &IssueData, issue_path: &Path) -> Result<(), KanbusError> {
    let contents =
        serde_json::to_string_pretty(issue).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(issue_path, contents).map_err(|error| KanbusError::Io(error.to_string()))
}

/// Resolve an issue file path by identifier.
///
/// # Arguments
/// * `issues_directory` - Directory containing issue files.
/// * `identifier` - Issue identifier.
pub fn issue_path_for_identifier(issues_directory: &Path, identifier: &str) -> PathBuf {
    issues_directory.join(format!("{identifier}.json"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::collections::BTreeMap;

    use crate::models::{DependencyLink, IssueComment};

    fn sample_issue(id: &str) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: format!("Issue {id}"),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::<DependencyLink>::new(),
            comments: Vec::<IssueComment>::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn issue_path_for_identifier_appends_json_suffix() {
        let base = Path::new("/tmp/issues");
        let path = issue_path_for_identifier(base, "kanbus-1");
        assert!(path.ends_with("issues/kanbus-1.json"));
    }

    #[test]
    fn write_and_read_issue_round_trip() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues dir");
        let issue = sample_issue("kanbus-1");
        let path = issue_path_for_identifier(&issues_dir, "kanbus-1");
        write_issue_to_file(&issue, &path).expect("write issue");

        let loaded = read_issue_from_file(&path).expect("read issue");
        assert_eq!(loaded.identifier, "kanbus-1");
        assert_eq!(loaded.status, "open");
    }

    #[test]
    fn write_issue_to_file_returns_io_error_when_target_is_directory() {
        let temp = tempfile::tempdir().expect("tempdir");
        let target_dir = temp.path().join("not-a-file");
        std::fs::create_dir_all(&target_dir).expect("create target dir");
        let issue = sample_issue("kanbus-2");
        let error = write_issue_to_file(&issue, &target_dir).expect_err("write should fail");
        assert!(matches!(error, KanbusError::Io(_)));
    }

    #[test]
    fn list_issue_identifiers_reads_only_json_filenames() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues dir");
        std::fs::write(issues_dir.join("kanbus-1.json"), "{}").expect("write issue one");
        std::fs::write(issues_dir.join("kanbus-2.json"), "{}").expect("write issue two");
        std::fs::write(issues_dir.join("README.md"), "ignored").expect("write non-json");

        let ids = list_issue_identifiers(&issues_dir).expect("list issue ids");
        assert_eq!(ids.len(), 2);
        assert!(ids.contains("kanbus-1"));
        assert!(ids.contains("kanbus-2"));
    }
}
