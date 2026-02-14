"""Issue close workflow."""

from __future__ import annotations

from pathlib import Path

from kanbus.issue_update import IssueUpdateError, update_issue
from kanbus.models import IssueData


class IssueCloseError(RuntimeError):
    """Raised when issue closing fails."""


def close_issue(root: Path, identifier: str) -> IssueData:
    """Close an issue by transitioning it to closed status.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Updated issue data.
    :rtype: IssueData
    :raises IssueCloseError: If closing fails.
    """
    try:
        return update_issue(
            root=root,
            identifier=identifier,
            title=None,
            description=None,
            status="closed",
            assignee=None,
            claim=False,
            validate=True,
        )
    except IssueUpdateError as error:
        raise IssueCloseError(str(error)) from error
