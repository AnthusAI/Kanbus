//! Kanbus data models.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HttpEndpointError {
    Invalid,
    Credentials,
    Insecure,
}

/// Validate an HTTP(S) endpoint, allowing plain HTTP only for loopback hosts.
pub(crate) fn validate_http_endpoint(value: &str) -> Result<(), HttpEndpointError> {
    let url = reqwest::Url::parse(value).map_err(|_| HttpEndpointError::Invalid)?;
    let host = url.host_str().ok_or(HttpEndpointError::Invalid)?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(HttpEndpointError::Invalid);
    }
    if !url.username().is_empty() || url.password().is_some() {
        return Err(HttpEndpointError::Credentials);
    }
    if url.scheme() == "http" {
        let is_loopback = host.eq_ignore_ascii_case("localhost")
            || host
                .strip_prefix('[')
                .and_then(|address| address.strip_suffix(']'))
                .unwrap_or(host)
                .parse::<std::net::IpAddr>()
                .is_ok_and(|address| address.is_loopback());
        if !is_loopback {
            return Err(HttpEndpointError::Insecure);
        }
    }
    Ok(())
}

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

/// Structured AI agent provenance metadata.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AgentMetadata {
    pub platform: String,
    pub model: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub settings: BTreeMap<String, serde_json::Value>,
}

/// Comment on an issue.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueComment {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    pub author: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    pub created_at: DateTime<Utc>,
    #[serde(default = "default_comment_type")]
    pub comment_type: String,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub data: BTreeMap<String, serde_json::Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent: Option<AgentMetadata>,
}

fn default_comment_type() -> String {
    "default".to_string()
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent: Option<AgentMetadata>,
    #[serde(default)]
    pub right_now_summary: Option<String>,
    #[serde(default)]
    pub right_now_updated_at: Option<DateTime<Utc>>,
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
    /// AI provider identifier (`litellm` routes through LiteLLM to the model vendor).
    pub provider: String,
    /// Model identifier (e.g. gpt-5.6-luna).
    pub model: String,
}

fn default_right_now_max_length() -> usize {
    120
}

fn default_right_now_model() -> Option<String> {
    Some("gpt-5.6-luna".to_string())
}

/// Right-now summary configuration for the console.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RightNowConfiguration {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub default_tree_expanded: bool,
    #[serde(default = "default_right_now_max_length")]
    pub max_length: usize,
    #[serde(default = "default_right_now_model")]
    pub model: Option<String>,
}

impl Default for RightNowConfiguration {
    fn default() -> Self {
        Self {
            enabled: true,
            default_tree_expanded: false,
            max_length: default_right_now_max_length(),
            model: default_right_now_model(),
        }
    }
}

fn default_standup_window() -> String {
    String::from("rolling")
}

fn default_standup_lookback() -> String {
    String::from("24h")
}

/// On-demand standup report configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StandupConfiguration {
    #[serde(default = "default_standup_window")]
    pub window: String,
    #[serde(default = "default_standup_lookback")]
    pub lookback: String,
    #[serde(default)]
    pub skip_weekends: bool,
    #[serde(default)]
    pub timezone: Option<String>,
}

impl Default for StandupConfiguration {
    fn default() -> Self {
        Self {
            window: default_standup_window(),
            lookback: default_standup_lookback(),
            skip_weekends: false,
            timezone: None,
        }
    }
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
    #[serde(default)]
    pub display_name: Option<String>,
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

/// Ordered coordination provider settings for soft resource leases.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CoordinationConfiguration {
    /// Strongest-first provider chain: `git`, `mqtt,git`, or `mutex_api,mqtt,git`.
    #[serde(default = "default_coordination_providers")]
    pub providers: Vec<String>,
    /// Duration during which competing claims may be compared, such as `5s`.
    #[serde(default = "default_coordination_contention_window")]
    pub contention_window: String,
    /// Lease duration used when a claim or renewal omits an override.
    #[serde(default = "default_coordination_lease_ttl")]
    pub default_lease_ttl: String,
    /// Optional authenticated hard-mutex API connection.
    #[serde(default)]
    pub mutex_api: MutexApiConfiguration,
}

/// Optional connection settings for the hard coordination mutex API.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MutexApiConfiguration {
    /// Base URL of the API, such as `https://mutex.example.test`.
    #[serde(default)]
    pub endpoint: Option<String>,
    /// Bearer token sent to the API.
    #[serde(default)]
    pub bearer_token: Option<String>,
}

/// Issue Router lifecycle status roles.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterWorkflowConfiguration {
    /// Status assigned while a package awaits a router worker.
    pub pending: String,
    /// Status assigned while a router worker owns a package.
    pub active: String,
    /// Status assigned after a change is published for review.
    pub review: String,
    /// Status assigned when a package cannot proceed.
    pub blocked: String,
    /// Statuses that indicate a completed package.
    pub terminal: Vec<String>,
}

/// Project, review, class, and provider work-in-progress limits.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterLimitsConfiguration {
    /// Maximum packages active, in review, or blocked across the project.
    pub project_wip: usize,
    /// Maximum packages in the configured review status.
    pub review_wip: usize,
    /// Optional per-class package limits.
    #[serde(default)]
    pub class_wip: BTreeMap<String, usize>,
    /// Optional per-provider-profile package limits.
    #[serde(default)]
    pub provider_wip: BTreeMap<String, usize>,
}

/// A configured Codex command profile used to execute an issue package.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterProviderConfiguration {
    /// Adapter protocol for the profile.
    pub adapter: String,
    /// Executable used to launch the adapter; defaults to the adapter name.
    #[serde(default)]
    pub command: Option<String>,
    /// Arguments preceding the adapter's subcommand arguments.
    #[serde(default)]
    pub args: Vec<String>,
    /// Model passed to the adapter, e.g. `amazon-bedrock/openai.gpt-oss-20b-1:0`.
    #[serde(default)]
    pub model: Option<String>,
    /// Environment variables merged over the parent environment for the adapter.
    #[serde(default)]
    pub env: BTreeMap<String, String>,
    /// Bedrock service tier (`flex`, `priority`, `default`) for OpenCode profiles.
    #[serde(default)]
    pub service_tier: Option<String>,
}

impl IssueRouterProviderConfiguration {
    /// Executable used to launch the adapter.
    pub fn resolved_command(&self) -> &str {
        self.command.as_deref().unwrap_or(&self.adapter)
    }
}

/// Ordered provider profiles available to an issue class.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterClassConfiguration {
    /// Provider profiles tried in order when a new claim begins.
    pub providers: Vec<String>,
}

/// Retry policy for a package after a retryable worker failure.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterRetryConfiguration {
    /// Maximum number of worker attempts before the package is blocked.
    #[serde(default = "default_issue_router_max_attempts")]
    pub max_attempts: u32,
}

/// Forge configuration for pull request publication and observation.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterForgeConfiguration {
    /// Forge implementation name, currently `github`.
    #[serde(default = "default_issue_router_forge_provider")]
    pub provider: String,
    /// Repository in `owner/name` form.
    pub repository: String,
    /// Base branch used for new pull requests.
    #[serde(default = "default_issue_router_base_branch")]
    pub base_branch: String,
    /// Forge API base URL.
    #[serde(default = "default_issue_router_api_url")]
    pub api_url: String,
    /// Environment variable containing the forge token.
    #[serde(default = "default_issue_router_token_environment")]
    pub token_env: String,
}

/// Optional configuration for the deterministic issue router.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IssueRouterConfiguration {
    /// Whether the configured router is enabled.
    #[serde(default = "default_true")]
    pub enabled: bool,
    /// Workflow statuses assigned to router lifecycle roles.
    pub workflow: IssueRouterWorkflowConfiguration,
    /// WIP limits that gate package scheduling.
    pub limits: IssueRouterLimitsConfiguration,
    /// Named provider profiles.
    pub providers: BTreeMap<String, IssueRouterProviderConfiguration>,
    /// Optional ordered provider groups keyed by issue class.
    #[serde(default)]
    pub classes: BTreeMap<String, IssueRouterClassConfiguration>,
    /// Worker retry policy.
    #[serde(default)]
    pub retries: IssueRouterRetryConfiguration,
    /// Polling interval used by `router run --watch`.
    #[serde(default = "default_issue_router_watch_interval")]
    pub watch_interval: String,
    /// Optional forge used to publish and observe pull requests.
    #[serde(default)]
    pub forge: Option<IssueRouterForgeConfiguration>,
}

fn default_issue_router_max_attempts() -> u32 {
    3
}

fn default_issue_router_watch_interval() -> String {
    "30s".to_string()
}

fn default_issue_router_forge_provider() -> String {
    "github".to_string()
}

fn default_issue_router_base_branch() -> String {
    "main".to_string()
}

fn default_issue_router_api_url() -> String {
    "https://api.github.com".to_string()
}

fn default_issue_router_token_environment() -> String {
    "GITHUB_TOKEN".to_string()
}

impl Default for IssueRouterRetryConfiguration {
    fn default() -> Self {
        Self {
            max_attempts: default_issue_router_max_attempts(),
        }
    }
}

fn default_coordination_providers() -> Vec<String> {
    vec!["git".to_string()]
}

fn default_coordination_contention_window() -> String {
    "5s".to_string()
}

fn default_coordination_lease_ttl() -> String {
    "300s".to_string()
}

impl Default for CoordinationConfiguration {
    fn default() -> Self {
        Self {
            providers: default_coordination_providers(),
            contention_window: default_coordination_contention_window(),
            default_lease_ttl: default_coordination_lease_ttl(),
            mutex_api: MutexApiConfiguration::default(),
        }
    }
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
    /// Human-readable board title. When unset, the console uses the repository folder.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
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
    pub right_now: RightNowConfiguration,
    #[serde(default)]
    pub standup: StandupConfiguration,
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
    #[serde(default)]
    pub github_security: Option<GithubSecurityConfiguration>,
    /// Git-backed soft-lease coordination settings.
    #[serde(default)]
    pub coordination: CoordinationConfiguration,
    /// Optional deterministic issue routing configuration.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub router: Option<IssueRouterConfiguration>,
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
    pub semantic_category: String,
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
