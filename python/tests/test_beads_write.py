from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import beads_write
from kanbus.models import DependencyLink

from test_helpers import build_issue


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _record(issue_id: str, **overrides):
    base = {
        "id": issue_id,
        "title": issue_id,
        "description": "",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "owner": "dev",
        "created_at": "2026-03-09T00:00:00Z",
        "created_by": "dev",
        "updated_at": "2026-03-09T00:00:00Z",
        "comments": [],
        "dependencies": [],
    }
    base.update(overrides)
    return base


def test_slug_sequence_and_slug_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    beads_write.set_test_beads_slug_sequence(["abc", "xyz"])
    assert beads_write._next_beads_slug() == "abc"
    assert beads_write._next_beads_slug() == "xyz"
    assert beads_write._next_beads_slug() is None

    beads_write.set_test_beads_slug_sequence(["qqq"])
    assert beads_write._generate_slug() == "qqq"

    monkeypatch.setattr(beads_write.secrets, "choice", lambda alphabet: alphabet[0])
    beads_write.set_test_beads_slug_sequence(None)
    assert beads_write._generate_slug() == "aaa"


def test_basic_helpers() -> None:
    assert beads_write._beads_comment_uuid("kanbus-1", "1") == beads_write._beads_comment_uuid("kanbus-1", "1")

    assert beads_write._derive_prefix({"kb-aaa", "kb-bbb"}) == "kb"
    with pytest.raises(beads_write.BeadsWriteError, match="invalid beads id"):
        beads_write._derive_prefix({"nohyphen"})

    assert beads_write._next_child_suffix({"kb-1.1", "kb-1.9", "other"}, "kb-1") == 10

    assert beads_write._generate_identifier({"kb-aaa"}, "kb", parent="kb-1") == "kb-1.1"


def test_generate_identifier_collision_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = {"kb-aaa"}
    monkeypatch.setattr(beads_write, "_generate_slug", lambda: "aaa")
    with pytest.raises(beads_write.BeadsWriteError, match="unable to generate unique id"):
        beads_write._generate_identifier(existing, "kb", parent=None)


def test_create_beads_issue_error_paths(tmp_path: Path) -> None:
    with pytest.raises(beads_write.BeadsWriteError, match="no .beads directory"):
        beads_write.create_beads_issue(tmp_path, "T", None, None, None, None, None)

    beads = tmp_path / ".beads"
    beads.mkdir()
    with pytest.raises(beads_write.BeadsWriteError, match="no issues.jsonl"):
        beads_write.create_beads_issue(tmp_path, "T", None, None, None, None, None)

    issues_path = beads / "issues.jsonl"
    issues_path.write_text("", encoding="utf-8")
    with pytest.raises(beads_write.BeadsWriteError, match="no beads issues available"):
        beads_write.create_beads_issue(tmp_path, "T", None, None, None, None, None)


def test_create_beads_issue_success_without_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(issues_path, [_record("kb-aaa")])

    monkeypatch.setattr(beads_write, "get_current_user", lambda: "dev")
    monkeypatch.setattr(beads_write, "_generate_slug", lambda: "bbb")
    monkeypatch.setattr(
        beads_write,
        "load_project_directory",
        lambda _root: (_ for _ in ()).throw(RuntimeError("no project")),
    )

    issue = beads_write.create_beads_issue(
        tmp_path,
        "New",
        issue_type="task",
        priority=1,
        assignee="me",
        parent=None,
        description="d",
    )
    assert issue.identifier == "kb-bbb"
    records = beads_write._load_beads_records(issues_path)
    assert any(record.get("id") == "kb-bbb" for record in records)


def test_create_beads_issue_parent_not_found_and_event_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(issues_path, [_record("kb-aaa")])

    monkeypatch.setattr(beads_write, "_generate_slug", lambda: "bbb")
    monkeypatch.setattr(beads_write, "get_current_user", lambda: "dev")

    with pytest.raises(beads_write.BeadsWriteError, match="not found"):
        beads_write.create_beads_issue(tmp_path, "x", None, None, None, "missing", None)

    monkeypatch.setattr(beads_write, "load_project_directory", lambda _root: tmp_path / "project")
    monkeypatch.setattr(beads_write, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(beads_write, "create_event", lambda **kwargs: SimpleNamespace(event_id="evt-1"))
    monkeypatch.setattr(beads_write, "events_dir_for_project", lambda _p: tmp_path / "events")
    monkeypatch.setattr(
        beads_write,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )

    original = issues_path.read_text(encoding="utf-8")
    with pytest.raises(beads_write.BeadsWriteError, match="event fail"):
        beads_write.create_beads_issue(tmp_path, "x", None, None, None, None, None)
    assert issues_path.read_text(encoding="utf-8") == original


def test_update_beads_issue_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(issues_path, [_record("kb-aaa", labels=["a"])])

    monkeypatch.setattr(beads_write, "load_beads_issue", lambda _root, _id: build_issue("kb-aaa"))

    with pytest.raises(beads_write.BeadsWriteError, match="not found"):
        beads_write.update_beads_issue(tmp_path, "missing")

    monkeypatch.setattr(beads_write, "load_project_directory", lambda _root: (_ for _ in ()).throw(RuntimeError("no project")))
    updated = beads_write.update_beads_issue(
        tmp_path,
        "kb-aaa",
        status="in_progress",
        title="New",
        description="D",
        priority=1,
        assignee="me",
        add_labels=["b"],
        remove_labels=["a"],
    )
    assert updated.identifier == "kb-aaa"

    monkeypatch.setattr(beads_write, "load_project_directory", lambda _root: tmp_path / "project")
    monkeypatch.setattr(beads_write, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(beads_write, "build_update_events", lambda *_a: [SimpleNamespace(event_id="evt-1")])
    monkeypatch.setattr(beads_write, "events_dir_for_project", lambda _p: tmp_path / "events")
    monkeypatch.setattr(
        beads_write,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )

    original = issues_path.read_text(encoding="utf-8")
    with pytest.raises(beads_write.BeadsWriteError, match="event fail"):
        beads_write.update_beads_issue(tmp_path, "kb-aaa", set_labels=["x"])
    assert issues_path.read_text(encoding="utf-8") == original


def test_add_beads_comment_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(issues_path, [_record("kb-aaa")])

    with pytest.raises(beads_write.BeadsWriteError, match="not found"):
        beads_write.add_beads_comment(tmp_path, "missing", "a", "t")

    monkeypatch.setattr(
        beads_write,
        "load_project_directory",
        lambda _root: (_ for _ in ()).throw(RuntimeError("no project")),
    )
    with pytest.raises(beads_write.BeadsWriteError, match="no project"):
        beads_write.add_beads_comment(tmp_path, "kb-aaa", "a", "t")

    monkeypatch.setattr(beads_write, "load_project_directory", lambda _root: tmp_path / "project")
    monkeypatch.setattr(beads_write, "load_beads_issue", lambda _root, _id: build_issue("kb-aaa"))
    monkeypatch.setattr(beads_write, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(beads_write, "get_current_user", lambda: "dev")
    monkeypatch.setattr(beads_write, "create_event", lambda **kwargs: SimpleNamespace(event_id="evt-1"))
    monkeypatch.setattr(beads_write, "comment_payload", lambda *_a: {"ok": True})
    monkeypatch.setattr(beads_write, "events_dir_for_project", lambda _p: tmp_path / "events")
    monkeypatch.setattr(
        beads_write,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )

    original = issues_path.read_text(encoding="utf-8")
    with pytest.raises(beads_write.BeadsWriteError, match="event fail"):
        beads_write.add_beads_comment(tmp_path, "kb-aaa", "a", "t")
    assert issues_path.read_text(encoding="utf-8") == original


def test_descendants_and_delete_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(
        issues_path,
        [
            _record("root"),
            _record("c1", parent="root"),
            _record("c2", parent="root"),
            _record("g1", parent="c1"),
        ],
    )

    assert beads_write.get_beads_descendant_identifiers(tmp_path, "root") == ["g1", "c1", "c2"]

    missing_root = tmp_path / "missing"
    assert beads_write.get_beads_descendant_identifiers(missing_root, "x") == []

    monkeypatch.setattr(beads_write, "load_project_directory", lambda _root: tmp_path / "project")
    monkeypatch.setattr(beads_write, "events_dir_for_project", lambda _p: tmp_path / "events")
    monkeypatch.setattr(beads_write, "delete_events_for_issues", lambda *_a: None)
    monkeypatch.setattr(beads_write, "publish_issue_deleted", lambda *_a: None)

    beads_write._delete_single_beads_issue(tmp_path, issues_path, "c1")
    remaining = beads_write._load_beads_records(issues_path)
    assert all(record.get("id") != "c1" for record in remaining)

    with pytest.raises(beads_write.BeadsDeleteError, match="not found"):
        beads_write._delete_single_beads_issue(tmp_path, issues_path, "missing")

    with pytest.raises(beads_write.BeadsDeleteError, match="no .beads directory"):
        beads_write.delete_beads_issue(tmp_path / "x", "a")


def test_delete_beads_issue_recursive_and_load_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(issues_path, [_record("root"), _record("child", parent="root")])

    monkeypatch.setattr(beads_write, "load_beads_issue", lambda _root, identifier: build_issue(identifier))
    called: list[str] = []
    monkeypatch.setattr(beads_write, "_delete_single_beads_issue", lambda _r, _p, i: called.append(i))

    beads_write.delete_beads_issue(tmp_path, "root", recursive=True)
    assert called == ["child", "root"]

    monkeypatch.setattr(
        beads_write,
        "load_beads_issue",
        lambda _root, _id: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    with pytest.raises(beads_write.BeadsDeleteError, match="missing"):
        beads_write.delete_beads_issue(tmp_path, "root")


def test_add_and_remove_beads_dependency_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(
        issues_path,
        [
            _record("a", dependencies=[]),
            _record("b", parent="a", dependencies=[]),
            _record("c", parent=None, dependencies=[]),
        ],
    )

    with pytest.raises(beads_write.BeadsWriteError, match="target issue z not found"):
        beads_write.add_beads_dependency(tmp_path, "a", "z", "blocked-by")

    with pytest.raises(beads_write.BeadsWriteError, match="own child"):
        beads_write.add_beads_dependency(tmp_path, "a", "b", "blocked-by")

    with pytest.raises(beads_write.BeadsWriteError, match="own parent"):
        beads_write.add_beads_dependency(tmp_path, "b", "a", "blocked-by")

    beads_write.add_beads_dependency(tmp_path, "a", "c", "blocked-by")
    with pytest.raises(beads_write.BeadsWriteError, match="already exists"):
        beads_write.add_beads_dependency(tmp_path, "a", "c", "blocked-by")

    with pytest.raises(beads_write.BeadsWriteError, match="not found"):
        beads_write.add_beads_dependency(tmp_path, "missing", "c", "blocked-by")

    monkeypatch.setattr(beads_write, "load_project_directory", lambda _root: tmp_path / "project")
    monkeypatch.setattr(beads_write, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(beads_write, "get_current_user", lambda: "dev")
    monkeypatch.setattr(beads_write, "create_event", lambda **kwargs: SimpleNamespace(event_id="evt"))
    monkeypatch.setattr(beads_write, "dependency_payload", lambda *_a: {"ok": True})
    monkeypatch.setattr(beads_write, "events_dir_for_project", lambda _p: tmp_path / "events")
    monkeypatch.setattr(
        beads_write,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )

    original = issues_path.read_text(encoding="utf-8")
    with pytest.raises(beads_write.BeadsWriteError, match="event fail"):
        beads_write.add_beads_dependency(tmp_path, "a", "c", "relates-to")
    assert issues_path.read_text(encoding="utf-8") == original

    # remove dependency paths
    with pytest.raises(beads_write.BeadsWriteError, match="not found"):
        beads_write.remove_beads_dependency(tmp_path, "missing", "c", "blocked-by")

    with pytest.raises(beads_write.BeadsWriteError, match="not found"):
        beads_write.remove_beads_dependency(tmp_path, "a", "c", "missing-type")

    with pytest.raises(beads_write.BeadsWriteError, match="event fail"):
        beads_write.remove_beads_dependency(tmp_path, "a", "c", "blocked-by")


def test_load_records_and_append_record(tmp_path: Path) -> None:
    issues_path = tmp_path / ".beads" / "issues.jsonl"
    _write_jsonl(issues_path, [_record("a")])

    beads_write._append_beads_record(issues_path, _record("b"))
    records = beads_write._load_beads_records(issues_path)
    assert [record.get("id") for record in records] == ["a", "b"]
