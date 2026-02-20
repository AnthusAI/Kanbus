//! Kanbus data models.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Category definition for grouping statuses.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CategoryDefinition {
    pub name: String,
    #[serde(default)]
    pub color: Option<String>,
}

/// Dependency link between issues.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyLink {
    pub target: String,
    #[serde(rename = "type")]
    pub dependency_type: String,
}

/// Comment on an issue.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueComment {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    pub author: String,
    pub text: String,
    pub created_at: DateTime<Utc>,
}

/// Issue data representation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueData {
    #[serde(rename = "id")]
    pub identifier: String,
    pub title: String,
    pub description: String,
    #[serde(rename = "type")]
    pub issue_type: String,
    pub status: String,
    pub priority: i32,
    pub assignee: Option<String>,
    pub creator: Option<String>,
    pub parent: Option<String>,
    pub labels: Vec<String>,
    pub dependencies: Vec<DependencyLink>,
    pub comments: Vec<IssueComment>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub closed_at: Option<DateTime<Utc>>,
    pub custom: BTreeMap<String, serde_json::Value>,
}

/// Jira synchronization configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JiraConfiguration {
    pub url: String,
    pub project_key: String,
    #[serde(default = "default_jira_sync_direction")]
    pub sync_direction: String,
    #[serde(default)]
    pub type_mappings: BTreeMap<String, String>,
    #[serde(default)]
    pub field_mappings: BTreeMap<String, String>,
}

fn default_jira_sync_direction() -> String {
    "pull".to_string()
}

/// Project configuration loaded from .kanbus.yml.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectConfiguration {
    pub project_directory: String,
    #[serde(default)]
    pub external_projects: Vec<String>,
    #[serde(default)]
    pub ignore_paths: Vec<String>,
    #[serde(default)]
    pub console_port: Option<u16>,
    pub project_key: String,
    #[serde(default)]
    pub project_management_template: Option<String>,
    pub hierarchy: Vec<String>,
    pub types: Vec<String>,
    pub workflows: BTreeMap<String, BTreeMap<String, Vec<String>>>,
    #[serde(default)]
    pub transition_labels: BTreeMap<String, BTreeMap<String, BTreeMap<String, String>>>,
    pub initial_status: String,
    pub priorities: BTreeMap<u8, PriorityDefinition>,
    pub default_priority: u8,
    #[serde(default)]
    pub assignee: Option<String>,
    #[serde(default)]
    pub time_zone: Option<String>,
    pub statuses: Vec<StatusDefinition>,
    #[serde(default)]
    pub categories: Vec<CategoryDefinition>,
    #[serde(default)]
    pub type_colors: BTreeMap<String, String>,
    #[serde(default)]
    pub beads_compatibility: bool,
    #[serde(default)]
    pub jira: Option<JiraConfiguration>,
}

/// Status definition with display metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatusDefinition {
    pub key: String,
    pub name: String,
    pub category: String,
    #[serde(default)]
    pub color: Option<String>,
    #[serde(default)]
    pub collapsed: bool,
}

/// Priority definition containing label and optional color.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriorityDefinition {
    pub name: String,
    #[serde(default)]
    pub color: Option<String>,
}
