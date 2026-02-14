//! Console snapshot helpers.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_yaml::Value;

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::file_io::get_configuration_path;
use crate::models::IssueData;

/// Console-visible project configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsoleProjectConfig {
    pub prefix: String,
    pub hierarchy: Vec<String>,
    pub types: Vec<String>,
    pub workflows: BTreeMap<String, BTreeMap<String, Vec<String>>>,
    pub initial_status: String,
    pub priorities: BTreeMap<u8, String>,
    pub default_priority: u8,
    #[serde(default)]
    pub beads_compatibility: bool,
}

/// Snapshot payload for the console.
#[derive(Debug, Clone, Serialize)]
pub struct ConsoleSnapshot {
    pub config: ConsoleProjectConfig,
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
/// Returns `TaskulusError` if snapshot creation fails.
pub fn build_console_snapshot(root: &Path) -> Result<ConsoleSnapshot, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let config = load_console_config(&project_dir)?;
    let mut issues = load_console_issues(&project_dir)?;
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    let updated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true);
    Ok(ConsoleSnapshot {
        config,
        issues,
        updated_at,
    })
}

fn load_project_directory(root: &Path) -> Result<PathBuf, TaskulusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&configuration_path)?;
    Ok(configuration_path
        .parent()
        .unwrap_or(root)
        .join(configuration.project_directory))
}

fn load_console_config(project_dir: &Path) -> Result<ConsoleProjectConfig, TaskulusError> {
    let config_path = project_dir.join("config.yaml");
    let contents = fs::read_to_string(&config_path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            TaskulusError::Configuration("project/config.yaml not found".to_string())
        } else {
            TaskulusError::Io(error.to_string())
        }
    })?;

    let raw_value: Value = serde_yaml::from_str(&contents)
        .map_err(|_error| TaskulusError::Configuration("config.yaml is invalid".to_string()))?;

    if !matches!(raw_value, Value::Mapping(_)) {
        return Err(TaskulusError::Configuration(
            "config.yaml is invalid".to_string(),
        ));
    }

    serde_yaml::from_value(raw_value)
        .map_err(|_error| TaskulusError::Configuration("config.yaml is invalid".to_string()))
}

fn load_console_issues(project_dir: &Path) -> Result<Vec<IssueData>, TaskulusError> {
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() || !issues_dir.is_dir() {
        return Err(TaskulusError::IssueOperation(
            "project/issues directory not found".to_string(),
        ));
    }

    let mut issues = Vec::new();
    for entry in fs::read_dir(&issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let bytes = fs::read(&path)
            .map_err(|_error| TaskulusError::IssueOperation("issue file is invalid".to_string()))?;
        let issue: IssueData = serde_json::from_slice(&bytes)
            .map_err(|_error| TaskulusError::IssueOperation("issue file is invalid".to_string()))?;
        issues.push(issue);
    }
    Ok(issues)
}
