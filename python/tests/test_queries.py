from __future__ import annotations

import pytest

from kanbus import queries
from kanbus.models import IssueComment

from test_helpers import build_issue


def test_filter_issues_applies_all_filters() -> None:
    one = build_issue("kanbus-1", status="open", issue_type="task", labels=["a"])
    one.assignee = "dev"
    two = build_issue("kanbus-2", status="closed", issue_type="bug", labels=["b"])
    two.assignee = "ops"

    result = queries.filter_issues([one, two], "open", "task", "dev", "a")
    assert [issue.identifier for issue in result] == ["kanbus-1"]


def test_filter_issues_without_filters_returns_all() -> None:
    issues = [build_issue("kanbus-1"), build_issue("kanbus-2")]
    result = queries.filter_issues(issues, None, None, None, None)
    assert [issue.identifier for issue in result] == ["kanbus-1", "kanbus-2"]


def test_sort_issues_priority_and_invalid_key() -> None:
    hi = build_issue("kanbus-hi", priority=0)
    low = build_issue("kanbus-low", priority=4)

    sorted_issues = queries.sort_issues([low, hi], "priority")
    assert [issue.identifier for issue in sorted_issues] == ["kanbus-hi", "kanbus-low"]

    with pytest.raises(queries.QueryError, match="invalid sort key"):
        queries.sort_issues([hi], "bad")


def test_sort_issues_none_returns_input_order() -> None:
    issues = [build_issue("kanbus-1"), build_issue("kanbus-2")]
    result = queries.sort_issues(issues, None)
    assert [issue.identifier for issue in result] == ["kanbus-1", "kanbus-2"]


def test_search_issues_title_description_and_comments_with_dedupe() -> None:
    by_title = build_issue("kanbus-title", title="Fix Login")
    by_desc = build_issue("kanbus-desc")
    by_desc.description = "Contains API token"
    by_comment = build_issue("kanbus-comment")
    by_comment.comments = [
        IssueComment.model_validate(
            {
                "id": "1",
                "author": "dev",
                "text": "Needs migration",
                "created_at": "2026-03-09T00:00:00Z",
            }
        )
    ]

    result = queries.search_issues(
        [by_title, by_desc, by_comment],
        "api",
    )
    assert [issue.identifier for issue in result] == ["kanbus-desc"]

    result = queries.search_issues([by_title, by_desc, by_comment], "migration")
    assert [issue.identifier for issue in result] == ["kanbus-comment"]

    result = queries.search_issues([by_title, by_title], "fix")
    assert [issue.identifier for issue in result] == ["kanbus-title"]


def test_search_issues_empty_term_returns_all() -> None:
    issues = [build_issue("kanbus-1"), build_issue("kanbus-2")]
    assert queries.search_issues(issues, None) == issues
    assert queries.search_issues(issues, "") == issues
