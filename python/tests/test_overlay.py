from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile

from kanbus.models import IssueData, OverlayConfig
from kanbus.overlay import (
    OverlayIssueRecord,
    gc_overlay,
    overlay_issue_path,
    resolve_issue_with_overlay,
    write_overlay_issue,
)


def _issue(identifier: str, updated_at: datetime) -> IssueData:
    return IssueData(
        id=identifier,
        title="Overlay test",
        description="",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=updated_at,
        updated_at=updated_at,
        closed_at=None,
        custom={},
    )


def test_overlay_prefers_newer_overlay() -> None:
    base_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    overlay_time = base_time + timedelta(hours=1)
    base_issue = _issue("kanbus-1", base_time)
    overlay_issue = _issue("kanbus-1", overlay_time)
    overlay_record = OverlayIssueRecord(
        issue=overlay_issue,
        overlay_ts=overlay_time.isoformat().replace("+00:00", "Z"),
        overlay_event_id=None,
    )
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        project_dir.mkdir(parents=True, exist_ok=True)
        result = resolve_issue_with_overlay(
            project_dir,
            base_issue,
            overlay_record,
            None,
            OverlayConfig(enabled=True, ttl_s=86400),
        )
    assert result is not None
    assert result.identifier == overlay_issue.identifier
    assert result.updated_at == overlay_issue.updated_at


def test_gc_overlay_removes_stale_overlay() -> None:
    base_time = datetime.now(timezone.utc)
    overlay_time = base_time - timedelta(hours=1)
    base_issue = _issue("kanbus-2", base_time)
    overlay_issue = _issue("kanbus-2", overlay_time)
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        issues_dir = project_dir / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_path = issues_dir / "kanbus-2.json"
        issue_path.write_text(
            json.dumps(base_issue.model_dump(by_alias=True, mode="json"), indent=2),
            encoding="utf-8",
        )
        write_overlay_issue(
            project_dir,
            overlay_issue,
            overlay_time.isoformat().replace("+00:00", "Z"),
            None,
        )
        gc_overlay(project_dir, OverlayConfig(enabled=True, ttl_s=86400))
        assert not overlay_issue_path(project_dir, "kanbus-2").exists()
