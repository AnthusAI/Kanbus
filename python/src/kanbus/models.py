"""Kanbus data models."""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)


def _is_loopback_http_url(value: str) -> bool:
    """Return whether an HTTP URL targets an explicitly loopback host.

    :param value: Absolute HTTP URL to inspect.
    :type value: str
    :return: Whether the URL host is localhost or an IP loopback address.
    :rtype: bool
    """
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class AgentMetadata(BaseModel):
    """Structured AI agent provenance metadata.

    :param platform: Agent platform identifier (for example cursor).
    :type platform: str
    :param model: Model identifier used for the action.
    :type model: str
    :param name: Optional session or bot name for the agent runtime.
    :type name: Optional[str]
    :param settings: Optional open-ended model or runtime settings object.
    :type settings: Dict[str, Any]
    """

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    settings: Dict[str, Any] = Field(default_factory=dict)


class AgentAssignment(BaseModel):
    """Router assignment and resolved configuration shown in the console."""

    model_config = ConfigDict(extra="allow")

    kind: Optional[str] = None
    name: Optional[str] = None
    agent_class: Optional[str] = None
    provider: Optional[str] = None
    provider_profile: Optional[str] = None
    effective: Dict[str, Any] = Field(default_factory=dict)
    effective_configuration: Dict[str, Any] = Field(default_factory=dict)
    effective_config: Dict[str, Any] = Field(default_factory=dict)


class CategoryDefinition(BaseModel):
    """Category definition for grouping statuses."""

    name: str = Field(min_length=1)
    color: Optional[str] = None


class DependencyLink(BaseModel):
    """Dependency link between issues.

    :param target: Target issue identifier.
    :type target: str
    :param dependency_type: Dependency type.
    :type dependency_type: str
    """

    target: str = Field(min_length=1)
    dependency_type: str = Field(alias="type", min_length=1)


class IssueComment(BaseModel):
    """Comment on an issue.

    :param author: Comment author.
    :type author: str
    :param text: Comment text.
    :type text: str
    :param created_at: Timestamp when the comment was created.
    :type created_at: datetime
    :param comment_type: Type of comment (e.g. default, summary).
    :type comment_type: str
    :param data: Structured comment payload (e.g. compaction summary fields).
    :type data: Dict[str, Any]
    :param agent: Optional agent provenance metadata for this comment.
    :type agent: Optional[AgentMetadata]
    """

    id: Optional[str] = None
    author: str = Field(min_length=1)
    text: Optional[str] = None
    created_at: datetime
    comment_type: str = "default"
    data: Dict[str, Any] = Field(default_factory=dict)
    agent: Optional[AgentMetadata] = None

    @model_serializer(mode="wrap")
    def serialize_model(self, serializer: object) -> Dict[str, Any]:
        """Serialize comment data for issue JSON files.

        :param serializer: Pydantic serializer callable.
        :type serializer: object
        :return: Serialized comment payload.
        :rtype: Dict[str, Any]
        """
        data: Dict[str, Any] = serializer(self)
        if self.comment_type == "summary" and not self.text:
            data.pop("text", None)
        return data

    @model_validator(mode="after")
    def validate_comment_shape(self) -> "IssueComment":
        """Validate comment text and summary payload shape.

        :return: Validated comment instance.
        :rtype: IssueComment
        """
        if self.comment_type == "summary":
            rewritten_description = self.data.get("rewritten_description")
            activity_summary = self.data.get("activity_summary")
            has_structured_data = (
                isinstance(rewritten_description, str) and rewritten_description
            ) and (isinstance(activity_summary, str) and activity_summary)
            has_text = self.text and self.text.strip()
            if not has_structured_data and not has_text:
                raise ValueError(
                    "summary comment requires either data.rewritten_description + "
                    "data.activity_summary OR non-empty text (legacy format)"
                )
            return self
        if not self.text or not self.text.strip():
            raise ValueError("comment text is required")
        return self


class IssueData(BaseModel):
    """Issue data representation.

    :param identifier: Issue ID.
    :type identifier: str
    :param title: Short summary.
    :type title: str
    :param description: Markdown body.
    :type description: str
    :param issue_type: Issue type.
    :type issue_type: str
    :param status: Issue status.
    :type status: str
    :param priority: Priority level.
    :type priority: int
    :param assignee: Assignee identifier.
    :type assignee: Optional[str]
    :param creator: Creator identifier.
    :type creator: Optional[str]
    :param parent: Parent issue identifier.
    :type parent: Optional[str]
    :param labels: Labels for the issue.
    :type labels: List[str]
    :param dependencies: Dependency links.
    :type dependencies: List[DependencyLink]
    :param comments: Issue comments.
    :type comments: List[IssueComment]
    :param created_at: Creation timestamp.
    :type created_at: datetime
    :param updated_at: Update timestamp.
    :type updated_at: datetime
    :param closed_at: Close timestamp.
    :type closed_at: Optional[datetime]
    :param right_now_summary: Right-now summary text for the issue.
    :type right_now_summary: Optional[str]
    :param right_now_updated_at: Timestamp when the right-now summary was last updated.
    :type right_now_updated_at: Optional[datetime]
    :param custom: Custom fields.
    :type custom: Dict[str, object]
    :param agent: Optional agent provenance metadata captured at issue create.
    :type agent: Optional[AgentMetadata]
    """

    identifier: str = Field(alias="id", min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    issue_type: str = Field(alias="type", min_length=1)
    status: str = Field(min_length=1)
    priority: int
    assignee: Optional[str] = None
    creator: Optional[str] = None
    parent: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    dependencies: List[DependencyLink] = Field(default_factory=list)
    comments: List[IssueComment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    right_now_summary: Optional[str] = None
    right_now_updated_at: Optional[datetime] = None
    custom: Dict[str, object] = Field(default_factory=dict)
    agent: Optional[AgentMetadata] = None
    agent_assignment: Optional[AgentAssignment] = None


class StatusDefinition(BaseModel):
    """Status definition with display metadata."""

    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    semantic_category: str = Field(min_length=1)
    color: Optional[str] = None
    collapsed: bool = False


class PriorityDefinition(BaseModel):
    """Priority definition containing label and optional color."""

    name: str = Field(min_length=1)
    color: Optional[str] = None


class AiConfiguration(BaseModel):
    """AI provider configuration for wiki summarization.

    :param provider: AI provider identifier (`litellm` routes through LiteLLM).
    :type provider: str
    :param model: Model identifier (e.g. gpt-5.6-luna).
    :type model: str
    """

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class RightNowConfiguration(BaseModel):
    """Right-now summary configuration for the console.

    :param enabled: Whether right-now summaries are enabled.
    :type enabled: bool
    :param default_tree_expanded: Whether the right-now tree starts expanded.
    :type default_tree_expanded: bool
    :param max_length: Maximum summary length in characters.
    :type max_length: int
    :param model: Optional model override; when unset, reuse ai.model.
    :type model: Optional[str]
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    default_tree_expanded: bool = False
    max_length: int = 120
    model: Optional[str] = "gpt-5.6-luna"


class StandupConfiguration(BaseModel):
    """On-demand standup report configuration.

    :param window: Standup window mode (`rolling` or `calendar`).
    :type window: str
    :param lookback: Rolling lookback duration (for example `24h` or `1d`).
    :type lookback: str
    :param skip_weekends: Whether calendar mode bundles weekends on Monday.
    :type skip_weekends: bool
    :param timezone: Optional IANA timezone for calendar buckets.
    :type timezone: Optional[str]
    """

    model_config = ConfigDict(extra="forbid")

    window: str = "rolling"
    lookback: str = "24h"
    skip_weekends: bool = False
    timezone: Optional[str] = None


class JiraConfiguration(BaseModel):
    """Jira synchronization configuration."""

    model_config = ConfigDict(extra="forbid")

    url: str
    project_key: str
    sync_direction: str = "pull"
    type_mappings: Dict[str, str] = Field(default_factory=dict)
    field_mappings: Dict[str, str] = Field(default_factory=dict)


class SnykConfiguration(BaseModel):
    """Snyk vulnerability synchronization configuration."""

    model_config = ConfigDict(extra="forbid")

    org_id: str
    min_severity: str = "low"
    parent_epic: Optional[str] = None
    repo: Optional[str] = None


class DependabotConfiguration(BaseModel):
    """GitHub Dependabot synchronization configuration."""

    model_config = ConfigDict(extra="forbid")

    min_severity: str = "low"
    state: str = "open"
    parent_epic: Optional[str] = None


class GithubSecurityConfiguration(BaseModel):
    """GitHub security synchronization configuration."""

    model_config = ConfigDict(extra="forbid")

    repo: Optional[str] = None
    dependabot: Optional[DependabotConfiguration] = None


class VirtualProjectConfig(BaseModel):
    """Configuration for a single virtual project.

    :param path: Relative or absolute path to the virtual project directory.
    :type path: str
    :param display_name: Optional stable human label for standup and console output.
    :type display_name: Optional[str]
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    display_name: Optional[str] = None


class RealtimeTopics(BaseModel):
    """Realtime topic templates."""

    model_config = ConfigDict(extra="forbid")

    project_events: str = "projects/{project}/events"


class RealtimeConfig(BaseModel):
    """Realtime gossip configuration."""

    model_config = ConfigDict(extra="forbid")

    transport: str = "auto"
    broker: str = "auto"
    autostart: bool = True
    keepalive: bool = False
    uds_socket_path: Optional[str] = None
    mqtt_custom_authorizer_name: Optional[str] = None
    mqtt_api_token: Optional[str] = None
    topics: RealtimeTopics = Field(default_factory=RealtimeTopics)


class OverlayConfig(BaseModel):
    """Overlay cache configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    ttl_s: int = 86400


class MutexApiConfiguration(BaseModel):
    """Optional hard coordination API connection settings."""

    model_config = ConfigDict(extra="forbid")

    endpoint: Optional[str] = None
    bearer_token: Optional[str] = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        endpoint = value.strip()
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute http(s) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("must not include URL credentials")
        if parsed.scheme == "http" and not _is_loopback_http_url(endpoint):
            raise ValueError("must use HTTPS unless the host is loopback")
        return endpoint

    @field_validator("bearer_token")
    @classmethod
    def normalize_bearer_token(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        return value.strip()


class CoordinationConfiguration(BaseModel):
    """Soft coordination defaults and provider preferences.

    :param providers: Configured coordination providers, ordered strongest first.
    :type providers: List[str]
    :param contention_window: Claim contention duration (for example ``5s``).
    :type contention_window: str
    :param default_lease_ttl: Default soft lease duration (for example ``300s``).
    :type default_lease_ttl: str
    """

    model_config = ConfigDict(extra="forbid")

    providers: List[str] = Field(default_factory=lambda: ["git"])
    contention_window: str = "5s"
    default_lease_ttl: str = "300s"
    mutex_api: MutexApiConfiguration = Field(default_factory=MutexApiConfiguration)

    @field_validator("providers")
    @classmethod
    def validate_providers(cls, value: List[str]) -> List[str]:
        """Require the canonical strongest-first provider fallback chain."""
        allowed = (["git"], ["mqtt", "git"], ["mutex_api", "mqtt", "git"])
        if value not in allowed:
            raise ValueError(
                "coordination providers must be one of: git; mqtt,git; "
                "mutex_api,mqtt,git"
            )
        return value

    @field_validator("contention_window", "default_lease_ttl")
    @classmethod
    def validate_duration(cls, value: str) -> str:
        """Require a positive integer followed by a supported unit."""
        import re

        if not re.fullmatch(r"[1-9][0-9]*[smh]", value):
            raise ValueError(
                "duration must be a positive integer followed by s, m, or h"
            )
        return value


class RouterWorkflowRoles(BaseModel):
    """Explicit workflow statuses used by the deterministic issue router."""

    model_config = ConfigDict(extra="forbid")

    pending: str = Field(min_length=1)
    active: str = Field(min_length=1)
    review: str = Field(min_length=1)
    blocked: str = Field(min_length=1)
    terminal: List[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_distinct_roles(self) -> "RouterWorkflowRoles":
        """Reject ambiguous role assignments."""
        roles = [self.pending, self.active, self.review, self.blocked, *self.terminal]
        if len(roles) != len(set(roles)):
            raise ValueError("router workflow roles must use distinct statuses")
        return self


class RouterLimits(BaseModel):
    """Router-owned WIP and retry limits."""

    model_config = ConfigDict(extra="forbid")

    project_wip: int = Field(ge=1, strict=True)
    review_wip: int = Field(ge=1, strict=True)
    class_wip: Dict[str, int] = Field(default_factory=dict)
    provider_wip: Dict[str, int] = Field(default_factory=dict)

    @field_validator("class_wip", "provider_wip")
    @classmethod
    def validate_positive_limits(cls, value: Dict[str, int]) -> Dict[str, int]:
        """Require named limits to be positive integers."""
        if any(
            not key.strip()
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
            for key, limit in value.items()
        ):
            raise ValueError("router named limits must be positive integers")
        return value


class RouterAgentProfile(BaseModel):
    """Structured execution profile for one agent provider."""

    model_config = ConfigDict(extra="forbid")

    adapter: str
    command: str = "codex"
    args: List[str] = Field(default_factory=list)

    @field_validator("adapter")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        """Require the configured adapter supported by this slice."""
        normalized = value.strip().lower()
        if normalized != "codex":
            raise ValueError("router provider adapter must be codex")
        return normalized


class RouterAgentClass(BaseModel):
    """Ordered provider profiles available to a routed agent class."""

    model_config = ConfigDict(extra="forbid")

    providers: List[str] = Field(min_length=1)


class RouterRetryConfiguration(BaseModel):
    """Retry limit for an issue package."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)


class RouterForgeConfiguration(BaseModel):
    """Forge-neutral pull request integration settings."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "github"
    repository: str = Field(min_length=3)
    base_branch: str = "main"
    api_url: str = "https://api.github.com"
    token_env: str = "GITHUB_TOKEN"

    @model_validator(mode="after")
    def validate_forge(self) -> "RouterForgeConfiguration":
        """Require repository coordinates for GitHub operation."""
        if self.provider != "github":
            raise ValueError("router forge provider must be github")
        if len(self.repository.split("/")) != 2 or not all(self.repository.split("/")):
            raise ValueError("router forge repository must use owner/repository")
        import re

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.token_env):
            raise ValueError(
                "router forge token_env must be a valid environment variable name"
            )
        parsed_api_url = urlparse(self.api_url)
        if parsed_api_url.scheme not in {"http", "https"} or not parsed_api_url.netloc:
            raise ValueError("router forge api_url must be an absolute http(s) URL")
        if parsed_api_url.username is not None or parsed_api_url.password is not None:
            raise ValueError("router forge api_url must not include URL credentials")
        if parsed_api_url.scheme == "http" and not _is_loopback_http_url(self.api_url):
            raise ValueError(
                "router forge api_url must use HTTPS unless the host is loopback"
            )
        return self


class IssueRouterConfiguration(BaseModel):
    """Optional deterministic issue router configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    workflow: RouterWorkflowRoles | None = None
    limits: RouterLimits | None = None
    providers: Dict[str, RouterAgentProfile] = Field(default_factory=dict)
    classes: Dict[str, RouterAgentClass] = Field(default_factory=dict)
    retries: RouterRetryConfiguration = Field(default_factory=RouterRetryConfiguration)
    forge: Optional[RouterForgeConfiguration] = None
    watch_interval: str = "30s"

    @model_validator(mode="before")
    @classmethod
    def require_enabled_fields(cls, value: Any) -> Any:
        """Allow an explicit disabled marker without requiring execution settings."""
        if isinstance(value, dict) and value.get("enabled", True) is not False:
            missing = [
                key for key in ("workflow", "limits", "providers") if key not in value
            ]
            if missing:
                raise ValueError("router workflow, limits, and providers are required")
        return value

    @model_validator(mode="after")
    def validate_enabled_configuration(self) -> "IssueRouterConfiguration":
        """Require usable routes on enabled router configurations."""
        if self.enabled and (
            self.workflow is None or self.limits is None or not self.providers
        ):
            raise ValueError("router workflow, limits, and providers are required")
        return self

    @field_validator("watch_interval")
    @classmethod
    def validate_watch_interval(cls, value: str) -> str:
        """Require a positive duration using seconds, minutes, or hours."""
        import re

        if not re.fullmatch(r"[1-9][0-9]*[smh]", value):
            raise ValueError(
                "duration must be a positive integer followed by s, m, or h"
            )
        return value


class HookDefinition(BaseModel):
    """Hook definition for an event/phase binding."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    command: List[str] = Field(min_length=1)
    blocking: Optional[bool] = None
    timeout_ms: Optional[int] = Field(default=None, ge=1)
    cwd: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)


class HooksConfiguration(BaseModel):
    """Lifecycle hook engine configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    run_in_beads_mode: bool = True
    default_timeout_ms: int = Field(default=5000, ge=1)
    before: Dict[str, List[HookDefinition]] = Field(default_factory=dict)
    after: Dict[str, List[HookDefinition]] = Field(default_factory=dict)


class ProjectConfiguration(BaseModel):
    """Project configuration loaded from .kanbus.yml.

    :param project_directory: Relative path to the primary project directory.
    :type project_directory: str
    :param virtual_projects: Map of label to virtual project configuration.
    :type virtual_projects: Dict[str, VirtualProjectConfig]
    :param new_issue_project: Project label for new issue creation routing.
    :type new_issue_project: Optional[str]
    :param ignore_paths: Paths to exclude from project discovery.
    :type ignore_paths: List[str]
    :param project_key: Issue ID project key (prefix).
    :type project_key: str
    :param name: Optional human-readable board title.
    :type name: Optional[str]
    :param project_management_template: Optional template path for CONTRIBUTING_AGENT.md.
    :type project_management_template: Optional[str]
    :param hierarchy: Hierarchy ordering.
    :type hierarchy: List[str]
    :param types: Non-hierarchical types.
    :type types: List[str]
    :param workflows: Workflow definitions.
    :type workflows: Dict[str, Dict[str, List[str]]]
    :param initial_status: Initial status for new issues.
    :type initial_status: str
    :param priorities: Priority map.
    :type priorities: Dict[int, PriorityDefinition]
    :param default_priority: Default priority.
    :type default_priority: int
    :param assignee: Default assignee identifier.
    :type assignee: Optional[str]
    :param time_zone: Preferred display time zone.
    :type time_zone: Optional[str]
    :param type_colors: Optional map of issue type to color name.
    :type type_colors: Dict[str, str]
    :param beads_compatibility: Default Beads compatibility mode.
    :type beads_compatibility: bool
    :param sort_order: Optional status/category sort rules for console columns.
    :type sort_order: Dict[str, object]
    :param right_now: Right-now summary configuration.
    :type right_now: RightNowConfiguration
    :param standup: Standup report configuration.
    :type standup: StandupConfiguration
    :param jira: Optional Jira synchronization configuration.
    :type jira: Optional[JiraConfiguration]
    :param snyk: Optional Snyk vulnerability synchronization configuration.
    :type snyk: Optional[SnykConfiguration]
    :param realtime: Realtime gossip configuration.
    :type realtime: RealtimeConfig
    :param overlay: Overlay cache configuration.
    :type overlay: OverlayConfig
    :param hooks: Lifecycle hook configuration.
    :type hooks: HooksConfiguration
    :param github_security: Optional GitHub security synchronization configuration.
    :type github_security: Optional[GithubSecurityConfiguration]
    """

    model_config = ConfigDict(extra="forbid")

    project_directory: str
    virtual_projects: Dict[str, VirtualProjectConfig] = Field(default_factory=dict)
    new_issue_project: Optional[str] = None
    ignore_paths: List[str] = Field(default_factory=list)
    console_port: Optional[int] = None
    project_key: str = Field(min_length=1)
    name: Optional[str] = None
    project_management_template: Optional[str] = None
    hierarchy: List[str]
    types: List[str]
    workflows: Dict[str, Dict[str, List[str]]]
    transition_labels: Dict[str, Dict[str, Dict[str, str]]] = Field(
        default_factory=dict
    )
    initial_status: str = Field(min_length=1)
    priorities: Dict[int, PriorityDefinition]
    default_priority: int
    assignee: Optional[str] = Field(default=None, min_length=1)
    time_zone: Optional[str] = Field(default=None, min_length=1)
    statuses: List[StatusDefinition] = Field(default_factory=list)
    categories: List[CategoryDefinition] = Field(default_factory=list)
    sort_order: Dict[str, Any] = Field(default_factory=dict)
    type_colors: Dict[str, str] = Field(default_factory=dict)
    beads_compatibility: bool = False
    wiki_directory: Optional[str] = None
    ai: Optional[AiConfiguration] = None
    right_now: RightNowConfiguration = Field(default_factory=RightNowConfiguration)
    standup: StandupConfiguration = Field(default_factory=StandupConfiguration)
    jira: Optional[JiraConfiguration] = None
    snyk: Optional[SnykConfiguration] = None
    realtime: RealtimeConfig = Field(default_factory=RealtimeConfig)
    coordination: CoordinationConfiguration = Field(
        default_factory=CoordinationConfiguration
    )
    router: Optional[IssueRouterConfiguration] = None
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    hooks: HooksConfiguration = Field(default_factory=HooksConfiguration)
    github_security: Optional[GithubSecurityConfiguration] = None
