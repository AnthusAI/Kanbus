from __future__ import annotations

import json
from pathlib import Path

from kanbus import console_snapshot

from test_helpers import build_issue, build_project_configuration


def write_issue_file(project_dir: Path, issue_id: str, title: str) -> None:
    issue = build_issue(issue_id, title=title)
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    payload = issue.model_dump(by_alias=True, mode="json")
    (issues_dir / f"{issue_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_tag_issue_adds_project_and_source() -> None:
    issue = build_issue("kanbus-001")

    tagged = console_snapshot._tag_issue(issue, project_label="alpha", source="shared")

    assert tagged.custom["project_label"] == "alpha"
    assert tagged.custom["source"] == "shared"


def test_read_issues_from_dir_sorts_and_ignores_non_json(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    write_issue_file(project_dir, "kanbus-b", "Issue B")
    write_issue_file(project_dir, "kanbus-a", "Issue A")
    (project_dir / "issues" / "notes.txt").write_text("skip", encoding="utf-8")

    issues = console_snapshot._read_issues_from_dir(project_dir / "issues")

    assert [issue.identifier for issue in issues] == ["kanbus-a", "kanbus-b"]


def test_load_console_issues_includes_shared_and_local(tmp_path: Path) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    write_issue_file(project_dir, "kanbus-shared", "Shared issue")
    write_issue_file(local_dir, "kanbus-local", "Local issue")
    configuration = build_project_configuration()

    issues = console_snapshot._load_console_issues(root, project_dir, configuration)

    by_id = {issue.identifier: issue for issue in issues}
    assert by_id["kanbus-shared"].custom["source"] == "shared"
    assert by_id["kanbus-local"].custom["source"] == "local"


def test_load_console_issues_raises_when_project_issues_missing(tmp_path: Path) -> None:
    configuration = build_project_configuration()

    try:
        console_snapshot._load_console_issues(
            tmp_path, tmp_path / "missing", configuration
        )
    except console_snapshot.ConsoleSnapshotError as error:
        assert "project/issues directory not found" in str(error)
    else:
        raise AssertionError("expected ConsoleSnapshotError")


def test_format_timestamp_uses_utc_z_suffix() -> None:
    from datetime import datetime, timezone

    value = datetime(2026, 3, 6, 12, 0, 0, 123456, tzinfo=timezone.utc)

    assert console_snapshot._format_timestamp(value) == "2026-03-06T12:00:00.123Z"
