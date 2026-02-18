"""Workflow validation and transition side effects."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from kanbus.models import IssueData, ProjectConfiguration


class InvalidTransitionError(RuntimeError):
    """Raised when a workflow status transition is invalid."""


def get_workflow_for_issue_type(
    configuration: ProjectConfiguration,
    issue_type: str,
) -> Dict[str, List[str]]:
    """Return the workflow definition for a specific issue type.

    :param configuration: Project configuration with workflow definitions.
    :type configuration: ProjectConfiguration
    :param issue_type: Issue type to lookup.
    :type issue_type: str
    :return: Workflow definition for the issue type.
    :rtype: Dict[str, List[str]]
    :raises ValueError: If the default workflow is missing.
    """
    workflows = configuration.workflows
    if issue_type in workflows:
        return workflows[issue_type]
    if "default" not in workflows:
        raise ValueError("default workflow not defined")
    return workflows["default"]


def validate_status_transition(
    configuration: ProjectConfiguration,
    issue_type: str,
    current_status: str,
    new_status: str,
) -> None:
    """Validate that a status transition is permitted by the workflow.

    Looks up the workflow for the given issue type in the project
    configuration (falling back to the default workflow if no
    type-specific workflow exists), then verifies that the new status
    appears in the list of allowed transitions from the current status.

    :param configuration: Project configuration containing workflow definitions.
    :type configuration: ProjectConfiguration
    :param issue_type: Issue type being transitioned.
    :type issue_type: str
    :param current_status: Issue's current status.
    :type current_status: str
    :param new_status: Desired new status.
    :type new_status: str
    :raises InvalidTransitionError: If the transition is not permitted.
    """
    workflow = get_workflow_for_issue_type(configuration, issue_type)
    allowed_transitions = workflow.get(current_status, [])
    if new_status not in allowed_transitions:
        raise InvalidTransitionError(
            f"invalid transition from '{current_status}' "
            f"to '{new_status}' for type '{issue_type}'"
        )


def _collect_workflow_statuses(workflow: Dict[str, List[str]]) -> set[str]:
    valid_statuses = set(workflow.keys())
    for allowed in workflow.values():
        valid_statuses.update(allowed)
    return valid_statuses


def validate_status_value(
    configuration: ProjectConfiguration, issue_type: str, status: str
) -> None:
    valid_statuses: set[str] = set()

    # Add statuses from the statuses list (primary source of truth)
    valid_statuses.update(s.name for s in configuration.statuses)

    # Also check workflows for backward compatibility and additional validation
    if "default" in configuration.workflows:
        valid_statuses.update(
            _collect_workflow_statuses(configuration.workflows["default"])
        )
    if issue_type in configuration.workflows:
        valid_statuses.update(
            _collect_workflow_statuses(configuration.workflows[issue_type])
        )
    if status not in valid_statuses:
        raise InvalidTransitionError("unknown status")


def apply_transition_side_effects(
    issue: IssueData,
    new_status: str,
    current_utc_time: datetime,
) -> IssueData:
    """Apply workflow side effects based on a status transition.

    :param issue: Issue being updated.
    :type issue: IssueData
    :param new_status: New status being applied.
    :type new_status: str
    :param current_utc_time: Current UTC timestamp.
    :type current_utc_time: datetime
    :return: Updated issue data with side effects applied.
    :rtype: IssueData
    """
    closed_at = issue.closed_at
    if new_status == "closed":
        closed_at = current_utc_time
    elif issue.status == "closed" and new_status != "closed":
        closed_at = None
    return issue.model_copy(update={"closed_at": closed_at})
