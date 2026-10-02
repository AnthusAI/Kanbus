//! Issue file input/output helpers.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::daemon_client::{is_daemon_enabled, request_virtuus};
use crate::error::KanbusError;
use crate::models::IssueData;
use serde_json::{json, Value};
use virtuus::table::{StorageMode, ValidationMode};
use virtuus::Table;

fn issue_table(issues_directory: &Path) -> Result<Table, KanbusError> {
    let mut table = Table::new(
        "issues",
        Some("id"),
        None,
        None,
        Some(issues_directory.to_path_buf()),
        ValidationMode::Warn,
    )
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    table.set_storage_mode(StorageMode::Memory);
    table.set_pretty_json(true);
    table.add_gsi("by_status", "status", None);
    table.add_gsi("by_type", "type", None);
    table.add_gsi("by_parent", "parent", None);
    table.add_gsi("by_label", "labels[*]", None);
    table.add_gsi(
        "blocked_by",
        "dependencies[dependency_type=blocked-by].target",
        None,
    );
    table.load_from_dir(None);
    Ok(table)
}

fn service_spec(issues_directory: &Path) -> Value {
    json!({
        "name": "issues",
        "primary_key": "id",
        "directory": issues_directory,
        "validation": "warn",
        "pretty_json": true,
        "reconcile_seconds": 2,
        "indexes": [
            {"name": "by_status", "partition_key": "status"},
            {"name": "by_type", "partition_key": "type"},
            {"name": "by_parent", "partition_key": "parent"},
            {"name": "by_label", "partition_key": "labels[*]"},
            {"name": "blocked_by", "partition_key": "dependencies[dependency_type=blocked-by].target"}
        ]
    })
}

fn project_root(issues_directory: &Path) -> PathBuf {
    for candidate in issues_directory.ancestors() {
        if candidate.join(".kanbus.yml").is_file() {
            return candidate.to_path_buf();
        }
    }
    let parent = issues_directory.parent().unwrap_or(issues_directory);
    if matches!(
        parent.file_name().and_then(|name| name.to_str()),
        Some("project") | Some("project-local")
    ) {
        return parent.parent().unwrap_or(parent).to_path_buf();
    }
    parent.to_path_buf()
}

fn use_service(issues_directory: &Path) -> bool {
    if cfg!(test) {
        return false;
    }
    let root = project_root(issues_directory);
    is_daemon_enabled() && root.join(".kanbus.yml").is_file()
}

fn service_request(issues_directory: &Path, mut request: Value) -> Result<Value, KanbusError> {
    let root = project_root(issues_directory);
    let opened = request_virtuus(
        &root,
        &json!({"action": "open_table", "spec": service_spec(issues_directory)}),
    )?;
    let handle = opened
        .get("handle")
        .and_then(Value::as_str)
        .ok_or_else(|| KanbusError::Io("Virtuus daemon returned no table handle".to_string()))?;
    request["handle"] = Value::String(handle.to_string());
    request_virtuus(&root, &request)
}

/// List issue identifiers based on JSON filenames.
///
/// # Arguments
/// * `issues_directory` - Directory containing issue files.
///
/// # Errors
/// Returns `KanbusError::Io` if directory entries cannot be read.
pub fn list_issue_identifiers(issues_directory: &Path) -> Result<HashSet<String>, KanbusError> {
    if !issues_directory.is_dir() {
        return Ok(HashSet::new());
    }
    if use_service(issues_directory) {
        return Ok(
            service_request(issues_directory, json!({"action": "scan"}))?
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|record| record.get("id").and_then(Value::as_str).map(str::to_string))
                .collect(),
        );
    }
    let identifiers = std::fs::read_dir(issues_directory)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .filter_map(|entry| entry.ok())
        .filter_map(|entry| {
            let path = entry.path();
            (path.extension().and_then(|value| value.to_str()) == Some("json"))
                .then(|| path.file_stem()?.to_str().map(str::to_string))
                .flatten()
        })
        .collect::<HashSet<_>>();
    Ok(identifiers)
}

/// Collect every issue identifier in the repository for short-ID widths.
///
/// Unions the shared and local issue directories of every discovered project
/// (filename listing only; issue JSON bodies are never parsed).
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError::Io` if directory entries cannot be read.
pub fn project_identifier_universe(root: &Path) -> Result<HashSet<String>, KanbusError> {
    let mut universe = HashSet::new();
    let mut project_dirs = crate::project::discover_project_directories(root).unwrap_or_default();
    if project_dirs.is_empty() {
        project_dirs.push(root.to_path_buf());
    }
    for project_dir in &project_dirs {
        let mut dirs = vec![project_dir.join("issues")];
        if let Some(local_dir) = crate::file_io::find_project_local_directory(project_dir) {
            dirs.push(local_dir.join("issues"));
        }
        for issues_dir in &dirs {
            universe.extend(list_issue_identifiers(issues_dir)?);
        }
    }
    Ok(universe)
}

/// Read an issue from a JSON file.
///
/// # Arguments
/// * `issue_path` - Path to the issue JSON file.
///
/// # Errors
/// Returns `KanbusError::Io` if reading or parsing fails.
pub fn read_issue_from_file(issue_path: &Path) -> Result<IssueData, KanbusError> {
    let identifier = issue_path
        .file_stem()
        .and_then(|value| value.to_str())
        .ok_or_else(|| KanbusError::Io(format!("invalid issue path: {}", issue_path.display())))?;
    let parent = issue_path
        .parent()
        .ok_or_else(|| KanbusError::Io("issue path has no parent".to_string()))?;
    let record = if use_service(parent) {
        service_request(parent, json!({"action": "get", "pk": identifier}))?
    } else {
        issue_table(parent)?
            .get(identifier, None)
            .unwrap_or(Value::Null)
    };
    if record.is_null() {
        return Err(KanbusError::Io(format!(
            "issue not found: {}",
            issue_path.display()
        )));
    }
    serde_json::from_value(record).map_err(|error| KanbusError::Io(error.to_string()))
}

/// Load all canonical issue records from a directory through Virtuus.
pub fn read_issues_from_directory(issues_directory: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let records = if use_service(issues_directory) {
        service_request(issues_directory, json!({"action": "scan"}))?
            .as_array()
            .cloned()
            .unwrap_or_default()
    } else {
        issue_table(issues_directory)?.scan()
    };
    let mut issues: Vec<IssueData> = records
        .into_iter()
        .map(|record| {
            serde_json::from_value(record).map_err(|error| KanbusError::Io(error.to_string()))
        })
        .collect::<Result<_, _>>()?;
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    Ok(issues)
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
    if issue_path.is_dir() {
        return Err(KanbusError::Io(format!(
            "issue path is a directory: {}",
            issue_path.display()
        )));
    }
    let parent = issue_path
        .parent()
        .ok_or_else(|| KanbusError::Io("issue path has no parent".to_string()))?;
    let record = serde_json::to_value(issue).map_err(|error| KanbusError::Io(error.to_string()))?;
    if use_service(parent) {
        service_request(parent, json!({"action": "put", "record": record}))?;
    } else {
        std::fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
        issue_table(parent)?
            .try_put(record)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(())
}

/// Delete an issue through the resident Virtuus table when available.
pub fn delete_issue_file(issue_path: &Path) -> Result<(), KanbusError> {
    let parent = issue_path
        .parent()
        .ok_or_else(|| KanbusError::Io("issue path has no parent".to_string()))?;
    let identifier = issue_path
        .file_stem()
        .and_then(|value| value.to_str())
        .ok_or_else(|| KanbusError::Io(format!("invalid issue path: {}", issue_path.display())))?;
    if use_service(parent) {
        service_request(parent, json!({"action": "delete", "pk": identifier}))?;
    } else if issue_path.exists() {
        issue_table(parent)?
            .try_delete(identifier, None)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(())
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
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
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
