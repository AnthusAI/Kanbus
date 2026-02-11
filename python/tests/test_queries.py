"""Tests for query utilities."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from taskulus.models import IssueComment, IssueData
from taskulus.queries import QueryError, filter_issues, search_issues, sort_issues


def _make_issue(identifier: str) -> IssueData:
    now = datetime.now(timezone.utc)
    return IssueData(
        id=identifier,
        title="Title",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        description="",
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )


def test_filter_issues_by_fields() -> None:
    issue_a = _make_issue("tsk-a").model_copy(
        update={
            "status": "open",
            "issue_type": "task",
            "assignee": "dev",
            "labels": ["auth"],
        }
    )
    issue_b = _make_issue("tsk-b").model_copy(
        update={"status": "closed", "issue_type": "bug", "assignee": None, "labels": []}
    )

    filtered = filter_issues(
        [issue_a, issue_b],
        status="open",
        issue_type="task",
        assignee="dev",
        label="auth",
    )

    assert [issue.identifier for issue in filtered] == ["tsk-a"]


def test_sort_issues_by_priority() -> None:
    issue_high = _make_issue("tsk-high").model_copy(update={"priority": 1})
    issue_low = _make_issue("tsk-low").model_copy(update={"priority": 3})

    sorted_issues = sort_issues([issue_low, issue_high], "priority")

    assert [issue.identifier for issue in sorted_issues] == ["tsk-high", "tsk-low"]


def test_sort_issues_rejects_invalid_key() -> None:
    issue = _make_issue("tsk-1")
    with pytest.raises(QueryError, match="invalid sort key"):
        sort_issues([issue], "bad")


def test_search_issues_matches_title_description_and_comments() -> None:
    issue_title = _make_issue("tsk-title").model_copy(update={"title": "OAuth setup"})
    issue_desc = _make_issue("tsk-desc").model_copy(
        update={"description": "Fix login button"}
    )
    comment = IssueComment(
        author="dev",
        text="Login failure",
        created_at=datetime.now(timezone.utc),
    )
    issue_comment = _make_issue("tsk-comment").model_copy(
        update={"comments": [comment]}
    )

    matches = search_issues([issue_title, issue_desc, issue_comment], term="login")

    identifiers = {issue.identifier for issue in matches}
    assert "tsk-desc" in identifiers
    assert "tsk-comment" in identifiers
    assert "tsk-title" not in identifiers


def test_search_issues_does_not_duplicate_matches() -> None:
    comment = IssueComment(
        author="dev",
        text="Search term in comment",
        created_at=datetime.now(timezone.utc),
    )
    issue = _make_issue("tsk-dup").model_copy(
        update={"title": "Search term in title", "comments": [comment]}
    )

    matches = search_issues([issue], term="search")

    assert [match.identifier for match in matches] == ["tsk-dup"]
