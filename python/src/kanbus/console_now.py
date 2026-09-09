"""Console Now panel API helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

from kanbus.console_snapshot import (
    ConsoleSnapshotError,
    _load_console_issues,
    _load_project_context,
)
from kanbus.models import IssueData
from kanbus.right_now import (
    ensure_right_now_summaries,
    require_display_right_now_summary,
)

DEFAULT_NOW_STATUS_FILTER = "in_progress"
NOW_STATUS_FILTER_ALL = "all"


def collect_now_tree_issue_identifiers(
    all_issues: List[IssueData],
    status_filter: str,
) -> List[str]:
    """Collect issue identifiers for the console Now tree display set.

    :param all_issues: Every issue available to the console.
    :type all_issues: List[IssueData]
    :param status_filter: Status key to match, or ``all``.
    :type status_filter: str
    :return: Identifiers for matching issues plus ancestors and descendants.
    :rtype: List[str]
    """
    if status_filter == NOW_STATUS_FILTER_ALL:
        matching_issues = list(all_issues)
    else:
        matching_issues = [
            issue for issue in all_issues if issue.status == status_filter
        ]

    if not matching_issues or len(matching_issues) == len(all_issues):
        return [issue.identifier for issue in matching_issues]

    issues_by_identifier = {issue.identifier: issue for issue in all_issues}
    children_by_parent: Dict[str, List[str]] = {}
    for issue in all_issues:
        if issue.parent:
            children_by_parent.setdefault(issue.parent, []).append(issue.identifier)

    included: set[str] = set()
    pending = [issue.identifier for issue in matching_issues]
    while pending:
        identifier = pending.pop()
        if identifier in included:
            continue
        included.add(identifier)
        pending.extend(children_by_parent.get(identifier, []))
        parent = issues_by_identifier.get(identifier)
        if parent and parent.parent:
            pending.append(parent.parent)

    return [issue.identifier for issue in all_issues if issue.identifier in included]


def build_now_issues(root: Path) -> List[IssueData]:
    """Backfill right-now summaries and return issues for the Now panel API.

    :param root: Repository root path.
    :type root: Path
    :return: Issues with JIT right-now summaries for the Now tree display set.
    :rtype: List[IssueData]
    :raises ConsoleSnapshotError: When configuration, loading, or generation fails.
    """
    project_dir, configuration = _load_project_context(root)
    issues = _load_console_issues(root, project_dir, configuration)
    display_identifiers = collect_now_tree_issue_identifiers(
        issues,
        DEFAULT_NOW_STATUS_FILTER,
    )
    ensure_right_now_summaries(root, display_identifiers, fail_closed=True)
    refreshed_issues = _load_console_issues(root, project_dir, configuration)
    issues_by_identifier = {issue.identifier: issue for issue in refreshed_issues}
    for identifier in display_identifiers:
        issue = issues_by_identifier.get(identifier)
        if issue is None:
            raise ConsoleSnapshotError(f"issue not found after JIT: {identifier}")
        require_display_right_now_summary(issue)
    return refreshed_issues


def format_now_timestamp(value: datetime) -> str:
    """Format a timestamp for Now API responses.

    :param value: Timestamp to format.
    :type value: datetime
    :return: RFC3339 timestamp with millisecond precision.
    :rtype: str
    """
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
