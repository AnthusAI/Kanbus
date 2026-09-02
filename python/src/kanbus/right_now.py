"""Right-now summary helpers."""

from __future__ import annotations

from typing import Optional

from kanbus.models import IssueData


def get_right_now_summary(issue: IssueData) -> Optional[str]:
    """Return the right-now summary for an issue.

    :param issue: Issue data to read.
    :type issue: IssueData
    :return: The right-now summary text, or None when absent.
    :rtype: Optional[str]
    """
    return issue.right_now_summary
