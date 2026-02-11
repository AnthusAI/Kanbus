"""Taskulus data models."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


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


class ProjectConfiguration(BaseModel):
    """Project configuration loaded from config.yaml.

    :param prefix: Issue ID prefix.
    :type prefix: str
    :param hierarchy: Hierarchy ordering.
    :type hierarchy: List[str]
    :param types: Non-hierarchical types.
    :type types: List[str]
    :param workflows: Workflow definitions.
    :type workflows: Dict[str, Dict[str, List[str]]]
    :param initial_status: Initial status for new issues.
    :type initial_status: str
    :param priorities: Priority map.
    :type priorities: Dict[int, str]
    :param default_priority: Default priority.
    :type default_priority: int
    """

    prefix: str = Field(min_length=1)
    hierarchy: List[str]
    types: List[str]
    workflows: Dict[str, Dict[str, List[str]]]
    initial_status: str = Field(min_length=1)
    priorities: Dict[int, str]
    default_priority: int
