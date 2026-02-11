"""Unit tests for data models."""

from __future__ import annotations

from datetime import datetime, timezone

from taskulus.models import DependencyLink, IssueComment, IssueData


def test_issue_data_parses_from_aliases() -> None:
    """Issue data should parse using JSON field aliases."""
    payload = {
        "id": "tsk-aaaaaa",
        "title": "Title",
        "description": "",
        "type": "task",
        "status": "open",
        "priority": 2,
        "assignee": None,
        "creator": "user@example.com",
        "parent": None,
        "labels": ["label"],
        "dependencies": [{"target": "tsk-bbbbbb", "type": "blocked-by"}],
        "comments": [
            {
                "author": "user@example.com",
                "text": "Comment",
                "created_at": datetime(2025, 2, 10, tzinfo=timezone.utc),
            }
        ],
        "created_at": datetime(2025, 2, 10, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 2, 10, tzinfo=timezone.utc),
        "closed_at": None,
        "custom": {},
    }

    issue = IssueData.model_validate(payload)
    assert issue.identifier == "tsk-aaaaaa"
    assert issue.issue_type == "task"
    assert isinstance(issue.dependencies[0], DependencyLink)
    assert isinstance(issue.comments[0], IssueComment)
