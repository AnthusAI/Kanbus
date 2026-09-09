"""Workflow validation and transition side effects."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set

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


def collect_workflow_statuses(workflow: Dict[str, List[str]]) -> Set[str]:
    """Return every status key reachable in a workflow definition.

    :param workflow: Workflow definition for an issue type.
    :type workflow: Dict[str, List[str]]
    :return: Status keys present as sources or transition targets.
    :rtype: Set[str]
    """
    valid_statuses = set(workflow.keys())
    for allowed in workflow.values():
        valid_statuses.update(allowed)
    return valid_statuses


def _preferred_alternative_issue_type(
    configuration: ProjectConfiguration,
    status: str,
    current_type: str,
) -> Optional[str]:
    alternative_types = [
        candidate_type
        for candidate_type in find_issue_types_allowing_status(configuration, status)
        if candidate_type != current_type
    ]
    if "task" in alternative_types:
        return "task"
    if alternative_types:
        return alternative_types[0]
    return None


def find_issue_types_allowing_status(
    configuration: ProjectConfiguration,
    status: str,
) -> List[str]:
    """Return issue types whose workflow includes the given status.

    :param configuration: Project configuration with workflow definitions.
    :type configuration: ProjectConfiguration
    :param status: Status key to match against each type workflow.
    :type status: str
    :return: Matching issue types in configuration order.
    :rtype: List[str]
    """
    valid_types = configuration.hierarchy + configuration.types
    matching_types: List[str] = []
    for candidate_type in valid_types:
        try:
            workflow = get_workflow_for_issue_type(configuration, candidate_type)
        except ValueError:
            continue
        if status in collect_workflow_statuses(workflow):
            matching_types.append(candidate_type)
    return matching_types


def format_status_not_allowed_for_type_error(
    configuration: ProjectConfiguration,
    issue_type: str,
    status: str,
    issue_identifier: Optional[str] = None,
) -> str:
    """Build an actionable error for a type and status workflow mismatch.

    :param configuration: Project configuration with workflow definitions.
    :type configuration: ProjectConfiguration
    :param issue_type: Issue type being validated.
    :type issue_type: str
    :param status: Status value outside the type workflow.
    :type status: str
    :param issue_identifier: Optional issue identifier for remediation commands.
    :type issue_identifier: Optional[str]
    :return: Human-readable error with remediation hints.
    :rtype: str
    """
    workflow = get_workflow_for_issue_type(configuration, issue_type)
    allowed_statuses = sorted(collect_workflow_statuses(workflow))
    allowed_text = ", ".join(allowed_statuses)
    prefix = f"{issue_identifier}: " if issue_identifier else ""
    message = (
        f"{prefix}status '{status}' is not allowed for type '{issue_type}' "
        f"(allowed: {allowed_text})"
    )

    remediation_parts: List[str] = []
    if issue_identifier and allowed_statuses:
        remediation_parts.append(
            f"kbs update {issue_identifier} --status {allowed_statuses[0]}"
        )

    alternative_type = _preferred_alternative_issue_type(
        configuration, status, issue_type
    )
    if issue_identifier and alternative_type is not None:
        remediation_parts.append(f"kbs move {issue_identifier} {alternative_type}")
    elif not issue_identifier and alternative_type is not None:
        remediation_parts.append(f"use --type {alternative_type}")

    if remediation_parts:
        return f"{message}. Remediation: {' OR '.join(remediation_parts)}"
    return message


def validate_status_value(
    configuration: ProjectConfiguration,
    issue_type: str,
    status: str,
    issue_identifier: Optional[str] = None,
) -> None:
    """Validate that a status is known and allowed for the issue type workflow.

    :param configuration: Project configuration with workflow definitions.
    :type configuration: ProjectConfiguration
    :param issue_type: Issue type being validated.
    :type issue_type: str
    :param status: Status value to validate.
    :type status: str
    :param issue_identifier: Optional issue identifier for remediation hints.
    :type issue_identifier: Optional[str]
    :raises InvalidTransitionError: If the status is unknown or not allowed.
    """
    valid_statuses = {s.key for s in configuration.statuses}
    if status not in valid_statuses:
        raise InvalidTransitionError("unknown status")

    workflow = get_workflow_for_issue_type(configuration, issue_type)
    if status not in collect_workflow_statuses(workflow):
        raise InvalidTransitionError(
            format_status_not_allowed_for_type_error(
                configuration,
                issue_type,
                status,
                issue_identifier,
            )
        )


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
