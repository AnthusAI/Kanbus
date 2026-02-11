"""Tests for issue comment helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from taskulus.issue_comment import IssueCommentError, add_comment
from taskulus.issue_files import write_issue_to_file
from taskulus.models import IssueData


def _write_project_marker(root: Path, project_dir: str) -> Path:
    marker = root / ".taskulus.yaml"
    marker.write_text(f"project_dir: {project_dir}\n", encoding="utf-8")
    project_path = root / project_dir
    (project_path / "issues").mkdir(parents=True)
    return project_path


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


def test_add_comment_updates_issue(tmp_path: Path) -> None:
    project_dir = _write_project_marker(tmp_path, "project")
    issue = _make_issue("tsk-001")
    issue_path = project_dir / "issues" / "tsk-001.json"
    write_issue_to_file(issue, issue_path)

    result = add_comment(tmp_path, "tsk-001", "dev@example.com", "Note")

    assert result.issue.identifier == "tsk-001"
    assert result.comment.author == "dev@example.com"
    assert result.comment.text == "Note"
    assert result.issue.comments[-1].text == "Note"
    assert result.issue.updated_at is not None


def test_add_comment_missing_issue(tmp_path: Path) -> None:
    _write_project_marker(tmp_path, "project")
    with pytest.raises(IssueCommentError, match="not found"):
        add_comment(tmp_path, "tsk-missing", "dev@example.com", "Note")
