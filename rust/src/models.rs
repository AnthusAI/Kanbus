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

/// AI provider configuration for wiki summarization.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AiConfiguration {
    /// AI provider identifier (e.g. openai).
    pub provider: String,
    /// Model identifier (e.g. gpt-4o).
    pub model: String,
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

/// Realtime topic templates.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RealtimeTopics {
    pub project_events: String,
}

impl Default for RealtimeTopics {
    fn default() -> Self {
        Self {
            project_events: "projects/{project}/events".to_string(),
        }
    }
}

/// Realtime gossip configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RealtimeConfig {
    pub transport: String,
    pub broker: String,
    pub autostart: bool,
    pub keepalive: bool,
    pub uds_socket_path: Option<String>,
    pub mqtt_custom_authorizer_name: Option<String>,
    pub mqtt_api_token: Option<String>,
    pub topics: RealtimeTopics,
}

impl Default for RealtimeConfig {
    fn default() -> Self {
        Self {
            transport: "auto".to_string(),
            broker: "auto".to_string(),
            autostart: true,
            keepalive: false,
            uds_socket_path: None,
            mqtt_custom_authorizer_name: None,
            mqtt_api_token: None,
            topics: RealtimeTopics::default(),
        }
    }
}

/// Overlay cache configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlayConfig {
    pub enabled: bool,
    pub ttl_s: u64,
}

impl Default for OverlayConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            ttl_s: 86_400,
        }
    }
}

fn default_true() -> bool {
    true
}

fn default_hooks_timeout_ms() -> u64 {
    5_000
}

/// One external hook entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HookDefinition {
    pub id: String,
    pub command: Vec<String>,
    #[serde(default)]
    pub blocking: Option<bool>,
    #[serde(default)]
    pub timeout_ms: Option<u64>,
    #[serde(default)]
    pub cwd: Option<String>,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
}

/// Lifecycle hook engine configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HooksConfiguration {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_true")]
    pub run_in_beads_mode: bool,
    #[serde(default = "default_hooks_timeout_ms")]
    pub default_timeout_ms: u64,
    #[serde(default)]
    pub before: BTreeMap<String, Vec<HookDefinition>>,
    #[serde(default)]
    pub after: BTreeMap<String, Vec<HookDefinition>>,
}

impl Default for HooksConfiguration {
    fn default() -> Self {
        Self {
            enabled: true,
            run_in_beads_mode: true,
            default_timeout_ms: default_hooks_timeout_ms(),
            before: BTreeMap::new(),
            after: BTreeMap::new(),
        }
    }
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
    pub wiki_directory: Option<String>,
    #[serde(default)]
    pub ai: Option<AiConfiguration>,
    #[serde(default)]
    pub jira: Option<JiraConfiguration>,
    #[serde(default)]
    pub snyk: Option<SnykConfiguration>,
    #[serde(default)]
    pub realtime: RealtimeConfig,
    #[serde(default)]
    pub overlay: OverlayConfig,
    #[serde(default)]
    pub hooks: HooksConfiguration,
    pub github_security: Option<GithubSecurityConfiguration>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn jira_and_snyk_defaults_apply_on_deserialize() {
        let jira: JiraConfiguration = serde_json::from_str(
            r#"{
                "url":"https://jira.example.com",
                "project_key":"KAN",
                "type_mappings":{},
                "field_mappings":{}
            }"#,
        )
        .expect("deserialize jira");
        assert_eq!(jira.sync_direction, "pull");

        let snyk: SnykConfiguration = serde_json::from_str(
            r#"{
                "org_id":"org-id",
                "parent_epic":null,
                "repo":null
            }"#,
        )
        .expect("deserialize snyk");
        assert_eq!(snyk.min_severity, "low");
    }

    #[test]
    fn defaults_for_realtime_overlay_and_hooks_match_expected_values() {
        let topics = RealtimeTopics::default();
        assert_eq!(topics.project_events, "projects/{project}/events");

        let realtime = RealtimeConfig::default();
        assert_eq!(realtime.transport, "auto");
        assert_eq!(realtime.broker, "auto");
        assert!(realtime.autostart);
        assert!(!realtime.keepalive);
        assert!(realtime.uds_socket_path.is_none());
        assert!(realtime.mqtt_custom_authorizer_name.is_none());
        assert!(realtime.mqtt_api_token.is_none());
        assert_eq!(realtime.topics.project_events, "projects/{project}/events");

        let overlay = OverlayConfig::default();
        assert!(overlay.enabled);
        assert_eq!(overlay.ttl_s, 86_400);

        let hooks = HooksConfiguration::default();
        assert!(hooks.enabled);
        assert!(hooks.run_in_beads_mode);
        assert_eq!(hooks.default_timeout_ms, 5_000);
        assert!(hooks.before.is_empty());
        assert!(hooks.after.is_empty());
    }
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
