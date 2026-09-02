"""Query utilities for issue listing."""

from __future__ import annotations

from typing import Iterable, List

from kanbus.ids import matches_issue_identifier
from kanbus.models import IssueData
from kanbus.comment_summary import get_comment_display_text


class QueryError(RuntimeError):
    """Raised when query parameters are invalid."""


def filter_issues(
    issues: Iterable[IssueData],
    status: str | None,
    issue_type: str | None,
    assignee: str | None,
    label: str | None,
    parent: str | None = None,
) -> List[IssueData]:
    """Filter issues by common fields.

    :param issues: Issues to filter.
    :type issues: Iterable[IssueData]
    :param status: Status filter.
    :type status: str | None
    :param issue_type: Type filter.
    :type issue_type: str | None
    :param assignee: Assignee filter.
    :type assignee: str | None
    :param label: Label filter.
    :type label: str | None
    :param parent: Parent identifier filter. Accepts full ids and unique prefixes.
    :type parent: str | None
    :return: Filtered issues.
    :rtype: List[IssueData]
    """
    result = list(issues)
    if status:
        result = [issue for issue in result if issue.status == status]
    if issue_type:
        result = [issue for issue in result if issue.issue_type == issue_type]
    if assignee:
        result = [issue for issue in result if issue.assignee == assignee]
    if label:
        result = [issue for issue in result if label in issue.labels]
    if parent:
        result = [
            issue
            for issue in result
            if issue.parent is not None
            and matches_issue_identifier(parent, issue.parent)
        ]
    return result


def sort_issues_by_recently_updated(issues: Iterable[IssueData]) -> List[IssueData]:
    """Sort issues by updated_at descending with identifier ascending tie-break.

    :param issues: Issues to sort.
    :type issues: Iterable[IssueData]
    :return: Sorted issues.
    :rtype: List[IssueData]
    """
    return sorted(
        issues,
        key=lambda issue: (
            -_recently_updated_sort_timestamp(issue),
            issue.identifier,
        ),
    )


def _recently_updated_sort_timestamp(issue: IssueData) -> float:
    updated_at = issue.updated_at
    if updated_at.tzinfo is None:
        return updated_at.timestamp()
    return updated_at.timestamp()


def sort_issues(issues: Iterable[IssueData], sort_key: str | None) -> List[IssueData]:
    """Sort issues by a supported key.

    :param issues: Issues to sort.
    :type issues: Iterable[IssueData]
    :param sort_key: Sort key name.
    :type sort_key: str | None
    :return: Sorted issues.
    :rtype: List[IssueData]
    :raises QueryError: If the sort key is unsupported.
    """
    result = list(issues)
    if sort_key is None:
        return result
    if sort_key == "priority":
        return sorted(result, key=lambda issue: issue.priority)
    raise QueryError("invalid sort key")


def search_issues(issues: Iterable[IssueData], term: str | None) -> List[IssueData]:
    """Search issues by title and description.

    :param issues: Issues to search.
    :type issues: Iterable[IssueData]
    :param term: Search term.
    :type term: str | None
    :return: Matching issues.
    :rtype: List[IssueData]
    """
    if not term:
        return list(issues)
    lowered = term.lower()
    matches: List[IssueData] = []
    seen: set[str] = set()
    for issue in issues:
        if lowered in issue.title.lower() or lowered in issue.description.lower():
            if issue.identifier not in seen:
                matches.append(issue)
                seen.add(issue.identifier)
            continue
        for comment in issue.comments:
            if lowered in get_comment_display_text(comment).lower():
                if issue.identifier not in seen:
                    matches.append(issue)
                    seen.add(issue.identifier)
                break
    return matches
