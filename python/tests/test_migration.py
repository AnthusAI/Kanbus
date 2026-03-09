from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

import pytest

from kanbus import migration
from kanbus.migration import MigrationError

from test_helpers import build_project_configuration


def _record(issue_id: str, **overrides):
    base = {
        "id": issue_id,
        "title": f"Title {issue_id}",
        "description": "desc",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-03-08T00:00:00Z",
        "updated_at": "2026-03-09T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    base.update(overrides)
    return base


def test_load_beads_issues_and_issue_error_paths(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="no .beads directory"):
        migration.load_beads_issues(tmp_path)

    beads = tmp_path / ".beads"
    beads.mkdir()
    with pytest.raises(MigrationError, match="no issues.jsonl"):
        migration.load_beads_issues(tmp_path)

    (beads / "issues.jsonl").write_text(json.dumps(_record("kanbus-1")) + "\n", encoding="utf-8")
    issues = migration.load_beads_issues(tmp_path)
    assert len(issues) == 1
    assert issues[0].identifier == "kanbus-1"
    assert migration.load_beads_issue(tmp_path, "kanbus-1").identifier == "kanbus-1"

    with pytest.raises(MigrationError, match="not found"):
        migration.load_beads_issue(tmp_path, "missing")


def test_migrate_from_beads_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        migration,
        "ensure_git_repository",
        lambda _root: (_ for _ in ()).throw(RuntimeError("not a git repo")),
    )
    with pytest.raises(MigrationError, match="not a git repo"):
        migration.migrate_from_beads(tmp_path)

    monkeypatch.setattr(migration, "ensure_git_repository", lambda _root: None)
    with pytest.raises(MigrationError, match="no .beads directory"):
        migration.migrate_from_beads(tmp_path)

    beads = tmp_path / ".beads"
    beads.mkdir()
    with pytest.raises(MigrationError, match="no issues.jsonl"):
        migration.migrate_from_beads(tmp_path)

    (beads / "issues.jsonl").write_text(json.dumps(_record("kanbus-1")) + "\n", encoding="utf-8")
    monkeypatch.setattr(migration, "discover_project_directories", lambda _root: [Path("project")])
    with pytest.raises(MigrationError, match="already initialized"):
        migration.migrate_from_beads(tmp_path)


def test_migrate_from_beads_success_writes_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beads = tmp_path / ".beads"
    beads.mkdir()
    records = [_record("kanbus-1"), _record("kanbus-2")]
    (beads / "issues.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    project_dir = tmp_path / "project"
    (project_dir / "issues").mkdir(parents=True)

    monkeypatch.setattr(migration, "ensure_git_repository", lambda _root: None)
    monkeypatch.setattr(migration, "discover_project_directories", lambda _root: [])
    monkeypatch.setattr(migration, "initialize_project", lambda _root: None)
    monkeypatch.setattr(migration, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        migration,
        "load_project_configuration",
        lambda _path: build_project_configuration(),
    )

    writes: list[Path] = []
    monkeypatch.setattr(migration, "write_issue_to_file", lambda issue, path: writes.append(path))

    result = migration.migrate_from_beads(tmp_path)
    assert result.issue_count == 2
    assert len(writes) == 2
    assert writes[0].name == "kanbus-1.json"


def test_load_beads_records_and_dedupe(tmp_path: Path) -> None:
    issues_path = tmp_path / "issues.jsonl"
    issues_path.write_text("\n" + json.dumps(_record("kanbus-1")) + "\n", encoding="utf-8")

    records = migration._load_beads_records(issues_path)
    assert len(records) == 1

    issues_path.write_text(json.dumps({"title": "no id"}) + "\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="missing id"):
        migration._load_beads_records(issues_path)

    records = [
        _record("kanbus-1", updated_at="2026-03-09T00:00:00Z"),
        _record("kanbus-1", updated_at="2026-03-09T00:00:00Z", notes="longer payload"),
        _record("kanbus-2"),
        _record("kanbus-2"),
    ]
    deduped = migration._dedupe_beads_records(records, issues_path)
    assert len(deduped) == 2
    assert {r["id"] for r in deduped} == {"kanbus-1", "kanbus-2"}

    with pytest.raises(MigrationError, match="missing id"):
        migration._dedupe_beads_records([{"id": "x"}, {"title": "no id"}], issues_path)

    tied_records = [
        _record("kanbus-3", updated_at="2026-03-09T00:00:00Z", notes="short"),
        _record("kanbus-3", updated_at="2026-03-10T00:00:00Z", notes="long payload"),
        _record("kanbus-3", updated_at="2026-03-10T00:00:00Z", notes="long payload plus"),
    ]
    deduped_tied = migration._dedupe_beads_records(tied_records, issues_path)
    assert len(deduped_tied) == 1
    assert deduped_tied[0]["notes"] == "long payload plus"


def test_load_configuration_for_beads_builds_expected_defaults(tmp_path: Path) -> None:
    records = [
        _record("kanbus-1", issue_type="feature", status="blocked", priority=4),
        _record("kanbus-2", issue_type="epic", status="open", priority=1),
    ]
    cfg = migration._load_configuration_for_beads(tmp_path, records)
    assert cfg.project_key == "BD"
    assert "story" in cfg.types
    assert "blocked" in {status.key for status in cfg.statuses}
    assert 4 in cfg.priorities


def test_convert_record_and_validations(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = build_project_configuration()
    record_by_id = {"kanbus-parent": _record("kanbus-parent", issue_type="epic")}

    full = _record(
        "kanbus-1",
        issue_type="feature",
        dependencies=[{"type": "parent-child", "depends_on_id": "kanbus-parent"}],
        comments=[{"id": 1, "author": "A", "text": "Hi", "created_at": "2026-03-09T00:00:00Z"}],
        owner="owner",
        notes="notes",
        acceptance_criteria="ac",
        close_reason="done",
        created_by="creator",
        assignee="assignee",
        labels=["x"],
    )
    issue = migration._convert_record(full, record_by_id, cfg)
    assert issue.identifier == "kanbus-1"
    assert issue.issue_type == "story"
    assert issue.parent == "kanbus-parent"
    assert issue.custom["beads_owner"] == "owner"
    assert issue.custom["beads_issue_type"] == "feature"

    with_closed_at = _record("kanbus-closed", closed_at="2026-03-09T01:00:00Z")
    issue_closed = migration._convert_record(with_closed_at, record_by_id, cfg)
    assert issue_closed.closed_at is not None

    for key, value in [
        ("title", ""),
        ("issue_type", ""),
        ("status", ""),
    ]:
        bad = _record("bad", **{key: value})
        with pytest.raises(MigrationError):
            migration._convert_record(bad, record_by_id, cfg)

    with pytest.raises(MigrationError, match="priority is required"):
        migration._convert_record(_record("badp", priority=None), record_by_id, cfg)

    with pytest.raises(MigrationError, match="invalid priority"):
        migration._convert_record(_record("badp2", priority=99), record_by_id, cfg)


def test_convert_dependencies_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = build_project_configuration()
    record_by_id = {
        "p1": _record("p1", issue_type="epic"),
        "p2": _record("p2", issue_type="epic"),
        "d1": _record("d1", issue_type="task"),
    }

    warnings: list[str] = []
    monkeypatch.setattr(migration.click, "echo", lambda msg, err=True: warnings.append(msg))

    parent, deps = migration._convert_dependencies(
        [
            {"type": "parent-child", "depends_on_id": "p1"},
            {"type": "parent-child", "depends_on_id": "p2"},
            {"type": "blocks", "depends_on_id": "d1"},
        ],
        "kanbus-1",
        record_by_id,
        cfg,
        "task",
    )
    assert parent == "p1"
    assert len(deps) == 1
    assert deps[0].target == "d1"
    assert any("multiple parents" in w for w in warnings)

    with pytest.raises(MigrationError, match="invalid dependency"):
        migration._convert_dependencies([{"type": "blocks"}], "x", record_by_id, cfg, "task")

    with pytest.raises(MigrationError, match="missing dependency"):
        migration._convert_dependencies(
            [{"type": "blocks", "depends_on_id": "nope"}],
            "x",
            record_by_id,
            cfg,
            "task",
        )

    with pytest.raises(MigrationError, match="parent issue_type is required"):
        migration._convert_dependencies(
            [{"type": "parent-child", "depends_on_id": "missing-type"}],
            "x",
            {"missing-type": {"id": "missing-type"}},
            cfg,
            "task",
        )


def test_convert_dependencies_invalid_hierarchy_suggests_and_drops_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = build_project_configuration()
    record_by_id = {"p": _record("p", issue_type="story")}
    warnings: list[str] = []
    monkeypatch.setattr(migration.click, "echo", lambda msg, err=True: warnings.append(msg))

    parent, deps = migration._convert_dependencies(
        [{"type": "parent-child", "depends_on_id": "p"}],
        "kanbus-1",
        record_by_id,
        cfg,
        "epic",
    )
    assert parent is None
    assert deps == []
    assert any("Suggestion:" in w for w in warnings)


def test_comment_conversion_and_uuid() -> None:
    uuid_a = migration._beads_comment_uuid("kanbus-1", "1")
    uuid_b = migration._beads_comment_uuid("kanbus-1", "1")
    assert uuid_a == uuid_b

    comment = migration._convert_comment(
        "kanbus-1",
        {"id": 7, "author": "A", "text": "B", "created_at": "2026-03-09T00:00:00Z"},
        0,
    )
    assert comment.author == "A"
    assert comment.text == "B"

    with pytest.raises(MigrationError, match="invalid comment"):
        migration._convert_comment("kanbus-1", {"author": "", "text": "x", "created_at": "2026-03-09T00:00:00Z"}, 0)


def test_timestamp_normalization_and_validation_helpers() -> None:
    parsed = migration._parse_timestamp("2026-03-09T00:00:00Z", "updated_at")
    assert parsed.tzinfo == timezone.utc

    parsed_naive = migration._parse_timestamp("2026-03-09T00:00:00", "updated_at")
    assert parsed_naive.tzinfo == timezone.utc

    assert migration._normalize_fractional_seconds("2026-03-09T00:00:00Z") == "2026-03-09T00:00:00Z"
    assert (
        migration._normalize_fractional_seconds("2026-03-09T00:00:00.1+00:00")
        == "2026-03-09T00:00:00.100000+00:00"
    )
    assert (
        migration._normalize_fractional_seconds("2026-03-09T00:00:00.123456789+00:00")
        == "2026-03-09T00:00:00.123456+00:00"
    )
    assert migration._normalize_fractional_seconds("2026-03-09T00:00:00.ab+00:00") == "2026-03-09T00:00:00.ab+00:00"
    assert migration._normalize_fractional_seconds("2026-03-09T00:00:00.123456") == "2026-03-09T00:00:00.123456"

    with pytest.raises(MigrationError, match="updated_at is required"):
        migration._parse_timestamp(None, "updated_at")
    with pytest.raises(MigrationError, match="updated_at must be a string"):
        migration._parse_timestamp(123, "updated_at")
    with pytest.raises(MigrationError, match="invalid updated_at"):
        migration._parse_timestamp("bad", "updated_at")

    cfg = build_project_configuration()
    migration._validate_issue_type(cfg, "task")
    with pytest.raises(MigrationError, match="unknown issue type"):
        migration._validate_issue_type(cfg, "unknown")

    migration._validate_status(cfg, "task", "open")
    with pytest.raises(MigrationError, match="invalid status"):
        migration._validate_status(cfg, "task", "nope")
