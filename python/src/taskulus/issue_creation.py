"""Issue creation workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from taskulus.config_loader import load_project_configuration
from taskulus.hierarchy import InvalidHierarchyError, validate_parent_child_relationship
from taskulus.ids import IssueIdentifierRequest, generate_issue_identifier
from taskulus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from taskulus.models import IssueData
from taskulus.project import (
    ProjectMarkerError,
    ensure_project_local_directory,
    find_project_local_directory,
    load_project_directory,
)


class IssueCreationError(RuntimeError):
    """Raised when issue creation fails."""


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
) -> IssueData:
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
    :return: Created issue data.
    :rtype: IssueData
    :raises IssueCreationError: If validation or file operations fail.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise IssueCreationError(str(error)) from error

    issues_dir = project_dir / "issues"
    local_dir = find_project_local_directory(project_dir)
    if local:
        local_dir = ensure_project_local_directory(project_dir)
        issues_dir = local_dir / "issues"
    configuration = load_project_configuration(project_dir / "config.yaml")

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

    existing_ids = list_issue_identifiers(project_dir / "issues")
    if local_dir is not None:
        local_issues_dir = local_dir / "issues"
        if local_issues_dir.exists():
            existing_ids.update(list_issue_identifiers(local_issues_dir))
    created_at = datetime.now(timezone.utc)
    identifier_request = IssueIdentifierRequest(
        title=title,
        existing_ids=existing_ids,
        prefix=configuration.prefix,
        created_at=created_at,
    )
    identifier = generate_issue_identifier(identifier_request).identifier
    updated_at = created_at

    issue = IssueData(
        id=identifier,
        title=title,
        description=description or "",
        type=resolved_type,
        status=configuration.initial_status,
        priority=resolved_priority,
        assignee=assignee,
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
    return issue
