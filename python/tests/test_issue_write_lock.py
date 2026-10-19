"""Concurrent issue writes are refused instead of silently overwritten."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kanbus.event_history import create_event
from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.issue_mutation import (
    ConcurrentIssueModificationError,
    PersistIssueMutationRequest,
    persist_issue_mutation,
)
from kanbus.models import IssueData


def _issue(title: str) -> IssueData:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return IssueData(
        id="kanbus-1",
        title=title,
        description="",
        type="task",
        status="open",
        priority=2,
        created_at=now,
        updated_at=now,
    )


def _request(project_dir: Path, issue_path: Path, before: IssueData, title: str):
    return PersistIssueMutationRequest(
        project_dir=project_dir,
        issue_path=issue_path,
        issue=before.model_copy(update={"title": title}),
        actor_id="dev",
        events=[
            create_event(
                issue_id="kanbus-1",
                event_type="issue_updated",
                actor_id="dev",
                payload={},
                occurred_at="2026-01-01T00:00:00.000Z",
            )
        ],
        before_issue=before,
    )


def test_second_writer_with_stale_snapshot_is_refused(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    issue_path = project_dir / "issues" / "kanbus-1.json"
    issue_path.parent.mkdir(parents=True)
    write_issue_to_file(_issue("Original"), issue_path)
    snapshot_read_by_both = read_issue_from_file(issue_path)

    persist_issue_mutation(
        _request(project_dir, issue_path, snapshot_read_by_both, "First")
    )
    with pytest.raises(ConcurrentIssueModificationError):
        persist_issue_mutation(
            _request(project_dir, issue_path, snapshot_read_by_both, "Second")
        )
    assert read_issue_from_file(issue_path).title == "First"
