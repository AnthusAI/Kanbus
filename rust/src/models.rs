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

/// Snyk vulnerability synchronization configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SnykConfiguration {
    /// Snyk organization ID (UUID from app.snyk.io/org/<slug>/manage/settings).
    pub org_id: String,
    /// Minimum severity to import: critical, high, medium, or low (default: low).
    #[serde(default = "default_snyk_min_severity")]
    pub min_severity: String,
    /// Kanbus issue ID of the parent epic to attach imported bugs to.
    #[serde(default)]
    pub parent_epic: Option<String>,
    /// GitHub repo slug to filter projects (e.g. "AnthusAI/Plexus").
    /// If omitted, auto-detected from git remote origin.
    #[serde(default)]
    pub repo: Option<String>,
}

fn default_snyk_min_severity() -> String {
    "low".to_string()
}

/// GitHub Dependabot synchronization configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependabotConfiguration {
    /// Minimum severity to import: critical, high, medium, or low (default: low).
    #[serde(default = "default_dependabot_min_severity")]
    pub min_severity: String,
    /// Alert state filter (default: open).
    #[serde(default = "default_dependabot_state")]
    pub state: String,
    /// Kanbus issue ID of the parent epic to attach imported bugs to.
    #[serde(default)]
    pub parent_epic: Option<String>,
}

impl Default for DependabotConfiguration {
    fn default() -> Self {
        Self {
            min_severity: default_dependabot_min_severity(),
            state: default_dependabot_state(),
            parent_epic: None,
        }
    }
}

fn default_dependabot_min_severity() -> String {
    "low".to_string()
}

fn default_dependabot_state() -> String {
    "open".to_string()
}

/// GitHub security synchronization configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GithubSecurityConfiguration {
    /// GitHub repository slug to sync (e.g. "AnthusAI/Kanbus").
    #[serde(default)]
    pub repo: Option<String>,
    /// Dependabot synchronization settings.
    #[serde(default)]
    pub dependabot: Option<DependabotConfiguration>,
}

/// Configuration for a single virtual project.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VirtualProjectConfig {
    pub path: String,
}

/// Project configuration loaded from .kanbus.yml.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectConfiguration {
    pub project_directory: String,
    #[serde(default)]
    pub virtual_projects: BTreeMap<String, VirtualProjectConfig>,
    #[serde(default)]
    pub new_issue_project: Option<String>,
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
    pub sort_order: BTreeMap<String, serde_yaml::Value>,
    #[serde(default)]
    pub type_colors: BTreeMap<String, String>,
    #[serde(default)]
    pub beads_compatibility: bool,
    #[serde(default)]
    pub jira: Option<JiraConfiguration>,
    #[serde(default)]
    pub snyk: Option<SnykConfiguration>,
    #[serde(default)]
    pub github_security: Option<GithubSecurityConfiguration>,
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
