"""Tests for issue file helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from taskulus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from taskulus.models import IssueData


def _make_issue(identifier: str) -> IssueData:
    now = datetime.now(timezone.utc)
    return IssueData(
        id=identifier,
        title="Test issue",
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


def test_write_and_read_issue(tmp_path: Path) -> None:
    issue = _make_issue("tsk-123")
    issue_path = tmp_path / "tsk-123.json"
    write_issue_to_file(issue, issue_path)

    loaded = read_issue_from_file(issue_path)

    assert loaded.identifier == "tsk-123"
    assert loaded.title == "Test issue"


def test_list_issue_identifiers(tmp_path: Path) -> None:
    write_issue_to_file(_make_issue("tsk-1"), tmp_path / "tsk-1.json")
    write_issue_to_file(_make_issue("tsk-2"), tmp_path / "tsk-2.json")

    identifiers = list_issue_identifiers(tmp_path)

    assert identifiers == {"tsk-1", "tsk-2"}
