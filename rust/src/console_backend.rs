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
