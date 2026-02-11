"""Unit tests for workflow validation and side effects."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.models import IssueData, ProjectConfiguration
from taskulus.workflows import (
    InvalidTransitionError,
    apply_transition_side_effects,
    get_workflow_for_issue_type,
    validate_status_transition,
)


def build_issue_data(status: str, closed_at: datetime | None) -> IssueData:
    """Create a basic issue instance for workflow tests.

    :param status: Issue status value.
    :type status: str
    :param closed_at: Closed timestamp.
    :type closed_at: datetime | None
    :return: Issue data instance.
    :rtype: IssueData
    """
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)
    return IssueData(
        id="tsk-test01",
        title="Title",
        description="",
        type="task",
        status=status,
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=timestamp,
        updated_at=timestamp,
        closed_at=closed_at,
        custom={},
    )


def build_configuration() -> ProjectConfiguration:
    """Build a ProjectConfiguration from defaults.

    :return: ProjectConfiguration instance.
    :rtype: ProjectConfiguration
    """
    return ProjectConfiguration.model_validate(DEFAULT_CONFIGURATION)


def test_validate_status_transition_allows_valid_transition() -> None:
    """Valid transitions should not raise errors."""
    configuration = build_configuration()
    validate_status_transition(configuration, "task", "open", "in_progress")


def test_validate_status_transition_rejects_invalid_transition() -> None:
    """Invalid transitions should raise InvalidTransitionError."""
    configuration = build_configuration()
    with pytest.raises(InvalidTransitionError) as error:
        validate_status_transition(configuration, "task", "open", "blocked")
    assert "invalid transition from 'open' to 'blocked' for type 'task'" in str(
        error.value
    )


def test_apply_transition_side_effects_sets_closed_at_on_close() -> None:
    """Closing an issue should set closed_at."""
    now = datetime(2026, 2, 11, tzinfo=timezone.utc)
    issue = build_issue_data(status="open", closed_at=None)
    updated = apply_transition_side_effects(issue, "closed", now)
    assert updated.closed_at == now


def test_apply_transition_side_effects_clears_closed_at_on_reopen() -> None:
    """Reopening an issue should clear closed_at."""
    now = datetime(2026, 2, 11, tzinfo=timezone.utc)
    closed_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
    issue = build_issue_data(status="closed", closed_at=closed_at)
    updated = apply_transition_side_effects(issue, "open", now)
    assert updated.closed_at is None


def test_get_workflow_for_issue_type_uses_specific() -> None:
    configuration = build_configuration()
    workflow = get_workflow_for_issue_type(configuration, "epic")
    assert "open" in workflow


def test_get_workflow_for_issue_type_requires_default() -> None:
    configuration = build_configuration()
    configuration = configuration.model_copy(update={"workflows": {}})
    with pytest.raises(ValueError, match="default workflow not defined"):
        get_workflow_for_issue_type(configuration, "task")
