"""Kanbus data models."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class PriorityDefinition(BaseModel):
    """Priority definition containing label and optional color."""

    name: str = Field(min_length=1)
    color: Optional[str] = None


class ProjectConfiguration(BaseModel):
    """Project configuration loaded from .kanbus.yml.

    :param project_directory: Relative path to the primary project directory.
    :type project_directory: str
    :param external_projects: Optional list of additional project directories.
    :type external_projects: List[str]
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
    :param status_colors: Optional map of status to color name.
    :type status_colors: Dict[str, str]
    :param type_colors: Optional map of issue type to color name.
    :type type_colors: Dict[str, str]
    :param beads_compatibility: Default Beads compatibility mode.
    :type beads_compatibility: bool
    """

    model_config = ConfigDict(extra="forbid")

    project_directory: str
    external_projects: List[str] = Field(default_factory=list)
    ignore_paths: List[str] = Field(default_factory=list)
    console_port: Optional[int] = None
    project_key: str = Field(min_length=1)
    project_management_template: Optional[str] = None
    hierarchy: List[str]
    types: List[str]
    workflows: Dict[str, Dict[str, List[str]]]
    initial_status: str = Field(min_length=1)
    priorities: Dict[int, PriorityDefinition]
    default_priority: int
    assignee: Optional[str] = Field(default=None, min_length=1)
    time_zone: Optional[str] = Field(default=None, min_length=1)
    status_colors: Dict[str, str] = Field(default_factory=dict)
    type_colors: Dict[str, str] = Field(default_factory=dict)
    beads_compatibility: bool = False
