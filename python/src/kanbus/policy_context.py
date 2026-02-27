"""Policy evaluation context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from kanbus.models import IssueData, ProjectConfiguration


class PolicyOperation(str, Enum):
    """Type of operation triggering policy evaluation."""

    CREATE = "create"
    UPDATE = "update"
    CLOSE = "close"
    DELETE = "delete"


@dataclass
class StatusTransition:
    """Status transition details.

    :param from_status: Status before the transition.
    :type from_status: str
    :param to_status: Status after the transition.
    :type to_status: str
    """

    from_status: str
    to_status: str


@dataclass
class PolicyContext:
    """Context provided to policy evaluation steps.

    Contains all information needed to evaluate policies against
    a proposed issue state change.

    :param current_issue: Current issue state on disk.
    :type current_issue: Optional[IssueData]
    :param proposed_issue: Proposed issue state after applying updates.
    :type proposed_issue: IssueData
    :param transition: Status transition details if status is changing.
    :type transition: Optional[StatusTransition]
    :param operation: Type of operation triggering evaluation.
    :type operation: PolicyOperation
    :param project_configuration: Project configuration.
    :type project_configuration: ProjectConfiguration
    :param all_issues: All issues in the project for aggregate checks.
    :type all_issues: list[IssueData]
    """

    current_issue: Optional[IssueData]
    proposed_issue: IssueData
    transition: Optional[StatusTransition]
    operation: PolicyOperation
    project_configuration: ProjectConfiguration
    all_issues: list[IssueData]

    @property
    def issue(self) -> IssueData:
        """Get the issue being evaluated (proposed state).

        :return: The proposed issue.
        :rtype: IssueData
        """
        return self.proposed_issue

    def is_transition(self) -> bool:
        """Check if this is a status transition.

        :return: True if status is changing.
        :rtype: bool
        """
        return self.transition is not None

    def is_transitioning_to(self, status: str) -> bool:
        """Check if transitioning to a specific status.

        :param status: Target status to check.
        :type status: str
        :return: True if transitioning to this status.
        :rtype: bool
        """
        return self.transition is not None and self.transition.to_status == status

    def is_transitioning_from(self, status: str) -> bool:
        """Check if transitioning from a specific status.

        :param status: Source status to check.
        :type status: str
        :return: True if transitioning from this status.
        :rtype: bool
        """
        return self.transition is not None and self.transition.from_status == status

    def child_issues(self) -> list[IssueData]:
        """Get child issues of the proposed issue.

        :return: List of child issues.
        :rtype: list[IssueData]
        """
        parent_id = self.proposed_issue.identifier
        return [
            issue for issue in self.all_issues if issue.parent == parent_id
        ]

    def parent_issue(self) -> Optional[IssueData]:
        """Get parent issue of the proposed issue.

        :return: Parent issue if it exists.
        :rtype: Optional[IssueData]
        """
        if not self.proposed_issue.parent:
            return None
        parent_id = self.proposed_issue.parent
        return next(
            (issue for issue in self.all_issues if issue.identifier == parent_id),
            None,
        )


class PolicyViolationError(RuntimeError):
    """Raised when a policy is violated.

    :param policy_file: Path to the policy file.
    :type policy_file: str
    :param scenario: Scenario name that failed.
    :type scenario: str
    :param failed_step: The specific step that failed.
    :type failed_step: str
    :param message: Human-readable explanation.
    :type message: str
    """

    def __init__(
        self, policy_file: str, scenario: str, failed_step: str, message: str
    ) -> None:
        """Initialize policy violation error."""
        self.policy_file = policy_file
        self.scenario = scenario
        self.failed_step = failed_step
        self.message = message
        super().__init__(
            f"policy violation in {policy_file}\n"
            f"  Scenario: {scenario}\n"
            f"  Failed: {failed_step}\n"
            f"  {message}"
        )
