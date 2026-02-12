"""Issue update workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from taskulus.config_loader import load_project_configuration
from taskulus.issue_files import write_issue_to_file
from taskulus.issue_lookup import IssueLookupError, load_issue_from_project
from taskulus.models import IssueData
from taskulus.workflows import (
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
    configuration = load_project_configuration(project_dir / "config.yaml")
    updated_issue = lookup.issue
    current_time = datetime.now(timezone.utc)

    resolved_status = status
    if claim:
        resolved_status = "in_progress"

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
