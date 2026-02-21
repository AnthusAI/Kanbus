"""Kanbus data models."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    """

    id: Optional[str] = None
    author: str = Field(min_length=1)
    text: str = Field(min_length=1)
    created_at: datetime


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
    :param custom: Custom fields.
    :type custom: Dict[str, object]
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
    custom: Dict[str, object] = Field(default_factory=dict)


class StatusDefinition(BaseModel):
    """Status definition with display metadata."""

    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    color: Optional[str] = None
    collapsed: bool = False


class PriorityDefinition(BaseModel):
    """Priority definition containing label and optional color."""

    name: str = Field(min_length=1)
    color: Optional[str] = None


class JiraConfiguration(BaseModel):
    """Jira synchronization configuration."""

    model_config = ConfigDict(extra="forbid")

    url: str
    project_key: str
    sync_direction: str = "pull"
    type_mappings: Dict[str, str] = Field(default_factory=dict)
    field_mappings: Dict[str, str] = Field(default_factory=dict)


class VirtualProjectConfig(BaseModel):
    """Configuration for a single virtual project."""

    model_config = ConfigDict(extra="forbid")

    path: str


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
    :param jira: Optional Jira synchronization configuration.
    :type jira: Optional[JiraConfiguration]
    """

    model_config = ConfigDict(extra="forbid")

    project_directory: str
    virtual_projects: Dict[str, VirtualProjectConfig] = Field(default_factory=dict)
    new_issue_project: Optional[str] = None
    ignore_paths: List[str] = Field(default_factory=list)
    console_port: Optional[int] = None
    project_key: str = Field(min_length=1)
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
    type_colors: Dict[str, str] = Field(default_factory=dict)
    beads_compatibility: bool = False
    jira: Optional[JiraConfiguration] = None
