"""Issue update workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from kanbus.config_loader import load_project_configuration
from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueData
from kanbus.project import get_configuration_path
from kanbus.workflows import (
    InvalidTransitionError,
    apply_transition_side_effects,
    validate_status_transition,
)


class IssueUpdateError(RuntimeError):
    """Raised when issue updates fail."""


def update_issue(
    root: Path,
    identifier: str,
    title: Optional[str],
    description: Optional[str],
    status: Optional[str],
    assignee: Optional[str],
    claim: bool,
) -> IssueData:
    """Update an issue and persist it to disk.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :param title: Updated title if provided.
    :type title: Optional[str]
    :param description: Updated description if provided.
    :type description: Optional[str]
    :param status: Updated status if provided.
    :type status: Optional[str]
    :param assignee: Updated assignee if provided.
    :type assignee: Optional[str]
    :param claim: Whether to claim the issue.
    :type claim: bool
    :return: Updated issue data.
    :rtype: IssueData
    :raises IssueUpdateError: If the update fails.
    """
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueUpdateError(str(error)) from error

    project_dir = lookup.project_dir
    configuration = load_project_configuration(get_configuration_path(project_dir))
    updated_issue = lookup.issue
    current_time = datetime.now(timezone.utc)

    resolved_status = status
    if claim:
        resolved_status = "in_progress"

    if title is not None:
        normalized_title = title.strip()
        if normalized_title.casefold() == updated_issue.title.strip().casefold():
            title = None
        else:
            duplicate_identifier = _find_duplicate_title(
                project_dir / "issues",
                normalized_title,
                updated_issue.identifier,
            )
            if duplicate_identifier is not None:
                message = (
                    f'duplicate title: "{normalized_title}" '
                    f"already exists as {duplicate_identifier}"
                )
                raise IssueUpdateError(message)
            title = normalized_title

    if description is not None:
        description = description.strip()
        if description == updated_issue.description:
            description = None

    if assignee is not None and assignee == updated_issue.assignee:
        assignee = None

    if resolved_status is not None and resolved_status == updated_issue.status:
        resolved_status = None

    if (
        resolved_status is None
        and title is None
        and description is None
        and assignee is None
    ):
        raise IssueUpdateError("no updates requested")

    if resolved_status is not None:
        try:
            validate_status_transition(
                configuration,
                updated_issue.issue_type,
                updated_issue.status,
                resolved_status,
            )
        except InvalidTransitionError as error:
            raise IssueUpdateError(str(error)) from error
        updated_issue = apply_transition_side_effects(
            updated_issue,
            resolved_status,
            current_time,
        )
        updated_issue = updated_issue.model_copy(update={"status": resolved_status})

    update_fields = {"updated_at": current_time}
    if title is not None:
        update_fields["title"] = title
    if description is not None:
        update_fields["description"] = description
    if assignee is not None:
        update_fields["assignee"] = assignee

    updated_issue = updated_issue.model_copy(update=update_fields)
    write_issue_to_file(updated_issue, lookup.issue_path)
    return updated_issue


def _find_duplicate_title(
    issues_dir: Path, title: str, current_identifier: str
) -> Optional[str]:
    normalized_title = title.strip().casefold()
    for issue_path in issues_dir.glob("*.json"):
        if issue_path.stem == current_identifier:
            continue
        try:
            issue = read_issue_from_file(issue_path)
        except (ValueError, ValidationError):
            continue
        if issue.title.strip().casefold() == normalized_title:
            return issue.identifier
    return None
