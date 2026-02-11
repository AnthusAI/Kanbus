"""Tests for Beads migration helpers."""

from __future__ import annotations

import json
import subprocess
from datetime import timezone
from pathlib import Path

import pytest

from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.migration import (
    MigrationError,
    _convert_comment,
    _convert_dependencies,
    _convert_record,
    _load_beads_records,
    _parse_timestamp,
    migrate_from_beads,
)
from taskulus.models import ProjectConfiguration


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)


def _config() -> ProjectConfiguration:
    return ProjectConfiguration.model_validate(DEFAULT_CONFIGURATION)


def test_migrate_requires_beads_dir(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with pytest.raises(MigrationError, match="no .beads directory"):
        migrate_from_beads(tmp_path)


def test_migrate_requires_git_repo(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="not a git repository"):
        migrate_from_beads(tmp_path)


def test_migrate_requires_issues_jsonl(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    with pytest.raises(MigrationError, match="no issues.jsonl"):
        migrate_from_beads(tmp_path)


def test_migrate_requires_uninitialized(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".beads").mkdir()
    (tmp_path / ".beads" / "issues.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".taskulus.yaml").write_text("project_dir: project\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="already initialized"):
        migrate_from_beads(tmp_path)


def test_load_beads_records_requires_id(tmp_path: Path) -> None:
    path = tmp_path / "issues.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="missing id"):
        _load_beads_records(path)


def test_load_beads_records_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "issues.jsonl"
    path.write_text("\n" + json.dumps(_record_base()) + "\n", encoding="utf-8")
    records = _load_beads_records(path)
    assert len(records) == 1


def test_parse_timestamp_valid_z_suffix() -> None:
    parsed = _parse_timestamp("2024-01-01T00:00:00Z", "created_at")
    assert parsed.tzinfo is not None


def test_parse_timestamp_requires_value() -> None:
    with pytest.raises(MigrationError, match="created_at is required"):
        _parse_timestamp(None, "created_at")


def test_parse_timestamp_requires_string() -> None:
    with pytest.raises(MigrationError, match="created_at must be a string"):
        _parse_timestamp(123, "created_at")


def test_parse_timestamp_rejects_invalid() -> None:
    with pytest.raises(MigrationError, match="invalid created_at"):
        _parse_timestamp("nope", "created_at")


def test_parse_timestamp_adds_timezone_when_missing() -> None:
    parsed = _parse_timestamp("2024-01-01T00:00:00", "created_at")
    assert parsed.tzinfo == timezone.utc


def test_convert_comment_rejects_invalid() -> None:
    with pytest.raises(MigrationError, match="invalid comment"):
        _convert_comment(
            {"author": "", "text": "", "created_at": "2024-01-01T00:00:00Z"}
        )


def test_convert_comment_accepts_valid() -> None:
    comment = _convert_comment(
        {"author": "Alice", "text": "Note", "created_at": "2024-01-01T00:00:00Z"}
    )
    assert comment.author == "Alice"
    assert comment.text == "Note"


def _record_base() -> dict[str, object]:
    return {
        "id": "tsk-1",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


def test_convert_record_requires_title() -> None:
    record = _record_base()
    record["title"] = ""
    with pytest.raises(MigrationError, match="title is required"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_requires_issue_type() -> None:
    record = _record_base()
    record["issue_type"] = ""
    with pytest.raises(MigrationError, match="issue_type is required"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_requires_status() -> None:
    record = _record_base()
    record["status"] = ""
    with pytest.raises(MigrationError, match="status is required"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_requires_priority() -> None:
    record = _record_base()
    record.pop("priority")
    with pytest.raises(MigrationError, match="priority is required"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_rejects_invalid_priority() -> None:
    record = _record_base()
    record["priority"] = 9
    with pytest.raises(MigrationError, match="invalid priority"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_rejects_unknown_issue_type() -> None:
    record = _record_base()
    record["issue_type"] = "invalid"
    with pytest.raises(MigrationError, match="unknown issue type"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_rejects_invalid_status() -> None:
    record = _record_base()
    record["status"] = "invalid"
    with pytest.raises(MigrationError, match="invalid status"):
        _convert_record(record, {"tsk-1": record}, _config())


def test_convert_record_includes_closed_at_and_custom_fields() -> None:
    record = _record_base()
    record["closed_at"] = "2024-01-02T00:00:00Z"
    record["owner"] = "Owner"
    record["notes"] = "Notes"
    record["acceptance_criteria"] = "Criteria"
    record["close_reason"] = "Reason"
    issue = _convert_record(record, {"tsk-1": record}, _config())
    assert issue.closed_at is not None
    assert issue.custom["beads_owner"] == "Owner"
    assert issue.custom["beads_notes"] == "Notes"
    assert issue.custom["beads_acceptance_criteria"] == "Criteria"
    assert issue.custom["beads_close_reason"] == "Reason"


def test_convert_dependencies_rejects_invalid_dependency() -> None:
    record = _record_base()
    with pytest.raises(MigrationError, match="invalid dependency"):
        _convert_dependencies([{}], record["id"], {"tsk-1": record}, _config(), "task")


def test_convert_dependencies_rejects_missing_dependency() -> None:
    record = _record_base()
    with pytest.raises(MigrationError, match="missing dependency"):
        _convert_dependencies(
            [{"type": "blocked-by", "depends_on_id": "tsk-2"}],
            record["id"],
            {"tsk-1": record},
            _config(),
            "task",
        )


def test_convert_dependencies_adds_dependency_links() -> None:
    record = _record_base()
    dependency_record = {"id": "tsk-2", "issue_type": "task"}
    dependencies = [{"type": "blocked-by", "depends_on_id": "tsk-2"}]
    parent, links = _convert_dependencies(
        dependencies,
        record["id"],
        {"tsk-1": record, "tsk-2": dependency_record},
        _config(),
        "task",
    )

    assert parent is None
    assert len(links) == 1
    assert links[0].target == "tsk-2"
    assert links[0].dependency_type == "blocked-by"


def test_convert_dependencies_rejects_multiple_parents() -> None:
    record = _record_base()
    parent_record = {"id": "tsk-parent", "issue_type": "initiative"}
    dependencies = [
        {"type": "parent-child", "depends_on_id": "tsk-parent"},
        {"type": "parent-child", "depends_on_id": "tsk-parent"},
    ]
    with pytest.raises(MigrationError, match="multiple parents"):
        _convert_dependencies(
            dependencies,
            record["id"],
            {"tsk-1": record, "tsk-parent": parent_record},
            _config(),
            "task",
        )


def test_convert_dependencies_requires_parent_issue_type() -> None:
    record = _record_base()
    parent_record = {"id": "tsk-parent"}
    dependencies = [
        {"type": "parent-child", "depends_on_id": "tsk-parent"},
    ]
    with pytest.raises(MigrationError, match="parent issue_type is required"):
        _convert_dependencies(
            dependencies,
            record["id"],
            {"tsk-1": record, "tsk-parent": parent_record},
            _config(),
            "task",
        )


def test_convert_dependencies_validates_parent_child_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record_base()
    parent_record = {"id": "tsk-parent", "issue_type": "initiative"}
    dependencies = [
        {"type": "parent-child", "depends_on_id": "tsk-parent"},
    ]
    calls: dict[str, object] = {"args": None}

    def fake_validate(
        configuration: ProjectConfiguration, parent: str, child: str
    ) -> None:
        calls["args"] = (parent, child)

    monkeypatch.setattr(
        "taskulus.migration.validate_parent_child_relationship", fake_validate
    )

    parent, links = _convert_dependencies(
        dependencies,
        record["id"],
        {"tsk-1": record, "tsk-parent": parent_record},
        _config(),
        "task",
    )

    assert parent == "tsk-parent"
    assert links == []
    assert calls["args"] == ("initiative", "task")


def test_migrate_success(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    issues_path = beads_dir / "issues.jsonl"
    record = _record_base()
    issues_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = migrate_from_beads(tmp_path)

    assert result.issue_count == 1
    assert (tmp_path / ".taskulus.yaml").exists()
    assert (tmp_path / "project" / "issues" / "tsk-1.json").exists()
