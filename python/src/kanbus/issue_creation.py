"""Issue creation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from pydantic import ValidationError

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.hierarchy import InvalidHierarchyError, validate_parent_child_relationship
from kanbus.ids import IssueIdentifierRequest, generate_issue_identifier
from kanbus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project import (
    ProjectMarkerError,
    ensure_project_local_directory,
    find_project_local_directory,
    get_configuration_path,
    load_project_directory,
)


class IssueCreationError(RuntimeError):
    """Raised when issue creation fails."""


@dataclass(frozen=True)
class IssueCreationResult:
    """Result of issue creation."""

    issue: IssueData
    configuration: ProjectConfiguration


def create_issue(
    root: Path,
    title: str,
    issue_type: Optional[str],
    priority: Optional[int],
    assignee: Optional[str],
    parent: Optional[str],
    labels: Iterable[str],
    description: Optional[str],
    local: bool = False,
) -> IssueCreationResult:
    """Create a new issue and write it to disk.

    :param root: Repository root path.
    :type root: Path
    :param title: Issue title.
    :type title: str
    :param issue_type: Issue type override.
    :type issue_type: Optional[str]
    :param priority: Issue priority override.
    :type priority: Optional[int]
    :param assignee: Assignee identifier.
    :type assignee: Optional[str]
    :param parent: Parent issue identifier.
    :type parent: Optional[str]
    :param labels: Issue labels.
    :type labels: Iterable[str]
    :param description: Issue description.
    :type description: Optional[str]
    :param local: Whether to create the issue in project-local.
    :type local: bool
    :return: Created issue data and configuration.
    :rtype: IssueCreationResult
    :raises IssueCreationError: If validation or file operations fail.
    """
    try:
        project_dir = load_project_directory(root)
    except (ProjectMarkerError, ConfigurationError) as error:
        raise IssueCreationError(str(error)) from error

    issues_dir = project_dir / "issues"
    local_dir = find_project_local_directory(project_dir)
    if local:
        local_dir = ensure_project_local_directory(project_dir)
        issues_dir = local_dir / "issues"
    try:
        configuration = load_project_configuration(get_configuration_path(project_dir))
    except (ProjectMarkerError, ConfigurationError) as error:
        raise IssueCreationError(str(error)) from error

    resolved_type = issue_type or "task"
    valid_types = configuration.hierarchy + configuration.types
    if resolved_type not in valid_types:
        raise IssueCreationError("unknown issue type")

    resolved_priority = (
        priority if priority is not None else configuration.default_priority
    )
    if resolved_priority not in configuration.priorities:
        raise IssueCreationError("invalid priority")

    parent_issue = None
    if parent is not None:
        parent_path = issues_dir / f"{parent}.json"
        if not parent_path.exists():
            raise IssueCreationError("not found")
        parent_issue = read_issue_from_file(parent_path)
        try:
            validate_parent_child_relationship(
                configuration, parent_issue.issue_type, resolved_type
            )
        except InvalidHierarchyError as error:
            raise IssueCreationError(str(error)) from error

    duplicate_identifier = _find_duplicate_title(issues_dir, title)
    if duplicate_identifier is not None:
        message = f'duplicate title: "{title}" already exists as {duplicate_identifier}'
        raise IssueCreationError(message)

    existing_ids = list_issue_identifiers(project_dir / "issues")
    if local_dir is not None:
        local_issues_dir = local_dir / "issues"
        if local_issues_dir.exists():
            existing_ids.update(list_issue_identifiers(local_issues_dir))
    created_at = datetime.now(timezone.utc)
    identifier_request = IssueIdentifierRequest(
        title=title,
        existing_ids=existing_ids,
        prefix=configuration.project_key,
    )
    identifier = generate_issue_identifier(identifier_request).identifier
    updated_at = created_at

    resolved_assignee = assignee if assignee is not None else configuration.assignee

    issue = IssueData(
        id=identifier,
        title=title,
        description=description or "",
        type=resolved_type,
        status=configuration.initial_status,
        priority=resolved_priority,
        assignee=resolved_assignee,
        creator=None,
        parent=parent,
        labels=list(labels),
        dependencies=[],
        comments=[],
        created_at=created_at,
        updated_at=updated_at,
        closed_at=None,
        custom={},
    )

    issue_path = issues_dir / f"{identifier}.json"
    write_issue_to_file(issue, issue_path)
    return IssueCreationResult(issue=issue, configuration=configuration)


def _find_duplicate_title(issues_dir: Path, title: str) -> Optional[str]:
    normalized_title = title.strip().casefold()
    for issue_path in issues_dir.glob("*.json"):
        try:
            issue = read_issue_from_file(issue_path)
        except (ValueError, ValidationError):
            continue
        if issue.title.strip().casefold() == normalized_title:
            return issue.identifier
    return None
