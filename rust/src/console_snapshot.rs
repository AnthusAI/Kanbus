//! Console snapshot helpers.

use std::fs;
use std::path::{Path, PathBuf};

use chrono::{SecondsFormat, Utc};
use serde::Serialize;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::migration::load_beads_issues;
use crate::models::{IssueData, ProjectConfiguration};

/// Snapshot payload for the console.
#[derive(Debug, Clone, Serialize)]
pub struct ConsoleSnapshot {
    pub config: ProjectConfiguration,
    pub issues: Vec<IssueData>,
    pub updated_at: String,
}

/// Build a console snapshot for the given repository root.
///
/// # Arguments
///
/// * `root` - Repository root path.
///
/// # Errors
///
/// Returns `KanbusError` if snapshot creation fails.
pub fn build_console_snapshot(root: &Path) -> Result<ConsoleSnapshot, KanbusError> {
    let (project_dir, config) = load_project_context(root)?;
    let mut issues = if config.beads_compatibility {
        load_beads_issues(root)?
    } else {
        load_console_issues(&project_dir)?
    };
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    let updated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true);
    Ok(ConsoleSnapshot {
        config,
        issues,
        updated_at,
    })
}

fn load_project_context(root: &Path) -> Result<(PathBuf, ProjectConfiguration), KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&configuration_path)?;
    let project_dir = configuration_path
        .parent()
        .unwrap_or(root)
        .join(&configuration.project_directory);
    Ok((project_dir, configuration))
}

fn load_console_issues(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() || !issues_dir.is_dir() {
        return Err(KanbusError::IssueOperation(
            "project/issues directory not found".to_string(),
        ));
    }

    let mut issues = Vec::new();
    for entry in fs::read_dir(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
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
