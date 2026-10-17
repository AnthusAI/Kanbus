"""Rust/Python persistence fidelity for issue files."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.issue_update import merge_labels
from kanbus.models import IssueData


def _issue() -> IssueData:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return IssueData(
        id="kanbus-1",
        title="t",
        description="",
        type="task",
        status="open",
        priority=2,
        created_at=now,
        updated_at=now,
    )


def test_write_omits_null_agent_fields_like_rust(tmp_path: Path) -> None:
    path = tmp_path / "kanbus-1.json"
    write_issue_to_file(_issue(), path)
    written = json.loads(path.read_text())
    assert "agent" not in written
    assert "agent_assignment" not in written


def test_rewrite_preserves_unknown_keys_and_nanosecond_timestamps(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kanbus-1.json"
    write_issue_to_file(_issue(), path)
    on_disk = json.loads(path.read_text())
    on_disk["written_by_newer_cli"] = {"nested": [1, 2, 3]}
    on_disk["updated_at"] = "2026-01-01T00:00:00.000000123Z"
    path.write_text(json.dumps(on_disk))

    issue = read_issue_from_file(path)
    issue.status = "closed"
    write_issue_to_file(issue, path)

    rewritten = json.loads(path.read_text())
    assert rewritten["status"] == "closed"
    assert rewritten["written_by_newer_cli"] == {"nested": [1, 2, 3]}
    assert rewritten["updated_at"] == "2026-01-01T00:00:00.000000123Z"


def test_merge_labels_trims_dedupes_case_insensitively_and_keeps_order() -> None:
    assert merge_labels(["b", "a"], None, [" A ", "c", "C"], None) == ["b", "a", "c"]
    assert merge_labels(["b", "a"], None, None, ["B"]) == ["a"]
    assert merge_labels(["b"], [" x ", ""], ["y"], None) == ["x", "y"]
