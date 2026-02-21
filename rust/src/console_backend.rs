//! Console backend core helpers.

use std::fs;
use std::path::{Path, PathBuf};

use chrono::{SecondsFormat, Utc};
use serde::Serialize;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{find_project_local_directory, get_configuration_path};
use crate::migration::load_beads_issues;
use crate::models::{IssueData, ProjectConfiguration};

/// Snapshot payload for the console.
#[derive(Debug, Clone, Serialize)]
pub struct ConsoleSnapshot {
    pub config: ProjectConfiguration,
    pub issues: Vec<IssueData>,
    pub updated_at: String,
}

/// File-backed store for console data.
#[derive(Debug, Clone)]
pub struct FileStore {
    root: PathBuf,
}

impl FileStore {
    /// Create a new file store rooted at the provided path.
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// Resolve a tenant root under a shared base directory.
    pub fn resolve_tenant_root(base: &Path, account: &str, project: &str) -> PathBuf {
        base.join(account).join(project)
    }

    /// Return the file store root path.
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Load the project configuration for this store.
    pub fn load_config(&self) -> Result<ProjectConfiguration, KanbusError> {
        let configuration_path = get_configuration_path(self.root())?;
        load_project_configuration(&configuration_path)
    }

    /// Load issues for this store using the provided configuration.
    pub fn load_issues(
        &self,
        configuration: &ProjectConfiguration,
    ) -> Result<Vec<IssueData>, KanbusError> {
        if configuration.beads_compatibility {
            load_beads_issues(self.root())
        } else {
            let project_dir = self.root().join(&configuration.project_directory);
            load_console_issues(&project_dir)
        }
    }

    /// Build a snapshot payload for this store.
    pub fn build_snapshot(&self) -> Result<ConsoleSnapshot, KanbusError> {
        let configuration = self.load_config()?;
        let mut issues = self.load_issues(&configuration)?;
        issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
        let updated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true);
        Ok(ConsoleSnapshot {
            config: configuration,
            issues,
            updated_at,
        })
    }

    /// Build the JSON payload for a snapshot.
    pub fn build_snapshot_payload(&self) -> Result<String, KanbusError> {
        let snapshot = self.build_snapshot()?;
        serde_json::to_string(&snapshot).map_err(|error| KanbusError::Io(error.to_string()))
    }
}

/// Resolve issues by full or short identifier.
///
/// Short identifiers are `{project_key}-{prefix}` where `prefix` is up to 6
/// characters from the UUID segment after the dash.
pub fn find_issue_matches<'a>(
    issues: &'a [IssueData],
    identifier: &str,
    project_key: &str,
) -> Vec<&'a IssueData> {
    let mut matches = Vec::new();
    for issue in issues {
        if issue.identifier == identifier {
            matches.push(issue);
            continue;
        }
        if short_id_matches(identifier, project_key, &issue.identifier) {
            matches.push(issue);
        }
    }
    matches
}

fn short_id_matches(candidate: &str, project_key: &str, full_id: &str) -> bool {
    if !candidate.starts_with(project_key) {
        return false;
    }
    let mut parts = candidate.splitn(2, '-');
    let prefix_key = parts.next().unwrap_or("");
    let prefix = parts.next().unwrap_or("");
    if prefix_key != project_key {
        return false;
    }
    if prefix.is_empty() || prefix.len() > 6 {
        return false;
    }
    let mut full_parts = full_id.splitn(2, '-');
    let full_key = full_parts.next().unwrap_or("");
    let full_suffix = full_parts.next().unwrap_or("");
    if full_key != project_key {
        return false;
    }
    full_suffix.starts_with(prefix)
}

fn load_issues_from_dir(issues_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let mut issues = Vec::new();
    for entry in fs::read_dir(issues_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let bytes = fs::read(&path)
            .map_err(|_error| KanbusError::IssueOperation("issue file is invalid".to_string()))?;
        let issue: IssueData = serde_json::from_slice(&bytes)
            .map_err(|_error| KanbusError::IssueOperation("issue file is invalid".to_string()))?;
        issues.push(issue);
    }
    Ok(issues)
}

fn load_console_issues(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() || !issues_dir.is_dir() {
        return Err(KanbusError::IssueOperation(
            "project/issues directory not found".to_string(),
        ));
    }

    let mut issues = load_issues_from_dir(&issues_dir)?;

    if let Some(local_dir) = find_project_local_directory(project_dir) {
        let local_issues_dir = local_dir.join("issues");
        if local_issues_dir.is_dir() {
            issues.extend(load_issues_from_dir(&local_issues_dir)?);
        }
    }

    Ok(issues)
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::fs;
    use tempfile::TempDir;

    fn write_config(root: &Path, contents: &str) {
        fs::write(root.join(".kanbus.yml"), contents).expect("write config");
    }

    fn write_issue(project_root: &Path, issue: IssueData) {
        let issues_dir = project_root.join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues dir");
        let path = issues_dir.join(format!("{}.json", issue.identifier));
        let payload = serde_json::to_string(&issue).expect("serialize issue");
        fs::write(path, payload).expect("write issue");
    }

    fn make_issue(id: &str, issue_type: &str, parent: Option<&str>) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: format!("Issue {id}"),
            description: String::new(),
            issue_type: issue_type.to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: parent.map(str::to_string),
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: Default::default(),
        }
    }

    #[test]
    fn resolves_tenant_root() {
        let base = Path::new("/tmp");
        let resolved = FileStore::resolve_tenant_root(base, "acme", "widgets");
        assert_eq!(resolved, Path::new("/tmp").join("acme").join("widgets"));
    }

    #[test]
    fn root_returns_store_root() {
        let temp = TempDir::new().expect("temp dir");
        let store = FileStore::new(temp.path());
        assert_eq!(store.root(), temp.path());
    }

    #[test]
    fn finds_issue_matches_with_short_id() {
        let issues = vec![
            make_issue("kanbus-abc123", "epic", None),
            make_issue("kanbus-def456", "task", None),
        ];
        let matches = find_issue_matches(&issues, "kanbus-abc123", "kanbus");
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].identifier, "kanbus-abc123");

        let short_matches = find_issue_matches(&issues, "kanbus-abc", "kanbus");
        assert_eq!(short_matches.len(), 1);
        assert_eq!(short_matches[0].identifier, "kanbus-abc123");

        let none_matches = find_issue_matches(&issues, "kanbus-zzz", "kanbus");
        assert!(none_matches.is_empty());
    }

    #[test]
    fn short_id_matches_rejects_invalid_formats() {
        assert!(!short_id_matches("kanbus", "kanbus", "kanbus-abc123"));
        assert!(!short_id_matches("other-abc", "kanbus", "kanbus-abc123"));
        assert!(!short_id_matches("kanbusx-abc", "kanbus", "kanbus-abc123"));
        assert!(!short_id_matches("kanbus-", "kanbus", "kanbus-abc123"));
        assert!(!short_id_matches(
            "kanbus-abcdefg",
            "kanbus",
            "kanbus-abcdefg123"
        ));
    }

    #[test]
    fn short_id_matches_requires_full_id_prefix_match() {
        assert!(!short_id_matches("kanbus-abc", "kanbus", "other-abc123"));
    }

    #[test]
    fn builds_snapshot_from_project_files() {
        let temp = TempDir::new().expect("temp dir");
        write_config(temp.path(), "");
        write_issue(temp.path(), make_issue("kanbus-2", "task", None));
        write_issue(temp.path(), make_issue("kanbus-1", "epic", None));

        let store = FileStore::new(temp.path());
        let snapshot = store.build_snapshot().expect("snapshot");
        assert_eq!(snapshot.issues.len(), 2);
        assert_eq!(snapshot.issues[0].identifier, "kanbus-1");
        assert_eq!(snapshot.issues[1].identifier, "kanbus-2");
        assert!(snapshot.updated_at.contains('T'));
    }

    #[test]
    fn build_snapshot_payload_serializes() {
        let temp = TempDir::new().expect("temp dir");
        write_config(temp.path(), "");
        write_issue(temp.path(), make_issue("kanbus-1", "epic", None));

        let store = FileStore::new(temp.path());
        let payload = store.build_snapshot_payload().expect("payload");
        assert!(payload.contains("\"issues\""));
        assert!(payload.contains("kanbus-1"));
    }

    #[test]
    fn build_snapshot_payload_errors_when_config_missing() {
        let temp = TempDir::new().expect("temp dir");
        let store = FileStore::new(temp.path());
        assert!(store.build_snapshot_payload().is_err());
    }

    #[test]
    fn load_issues_errors_when_missing_dir() {
        let temp = TempDir::new().expect("temp dir");
        write_config(temp.path(), "");
        let store = FileStore::new(temp.path());
        let config = store.load_config().expect("config");
        let result = store.load_issues(&config);
        assert!(result.is_err());
    }

    #[test]
    fn load_config_errors_when_missing() {
        let temp = TempDir::new().expect("temp dir");
        let store = FileStore::new(temp.path());
        assert!(store.load_config().is_err());
    }

    #[test]
    fn load_issues_errors_on_invalid_json() {
        let temp = TempDir::new().expect("temp dir");
        write_config(temp.path(), "");
        let issues_dir = temp.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues dir");
        fs::write(issues_dir.join("bad.json"), "{not json").expect("write bad json");

        let store = FileStore::new(temp.path());
        let config = store.load_config().expect("config");
        let result = store.load_issues(&config);
        assert!(result.is_err());
    }

    #[test]
    fn load_issues_skips_non_json_files() {
        let temp = TempDir::new().expect("temp dir");
        write_config(temp.path(), "");
        let issues_dir = temp.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues dir");
        fs::write(issues_dir.join("ignore.txt"), "nope").expect("write non-json");
        write_issue(temp.path(), make_issue("kanbus-1", "epic", None));

        let store = FileStore::new(temp.path());
        let config = store.load_config().expect("config");
        let issues = store.load_issues(&config).expect("issues");
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].identifier, "kanbus-1");
    }

    #[test]
    fn loads_beads_issues_when_enabled() {
        let temp = TempDir::new().expect("temp dir");
        write_config(temp.path(), "beads_compatibility: true\n");
        let beads_dir = temp.path().join(".beads");
        fs::create_dir_all(&beads_dir).expect("create beads dir");
        let record = serde_json::json!({
            "id": "bd-001",
            "title": "Beads issue",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-01T00:00:00Z",
            "updated_at": "2026-02-01T00:00:00Z"
        });
        fs::write(beads_dir.join("issues.jsonl"), format!("{record}\n")).expect("write beads");

        let store = FileStore::new(temp.path());
        let config = store.load_config().expect("config");
        let issues = store.load_issues(&config).expect("beads issues");
        assert_eq!(issues.len(), 1);
        assert_eq!(issues[0].identifier, "bd-001");
    }
}
