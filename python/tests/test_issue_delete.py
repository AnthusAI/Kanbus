from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import kanbus.issue_delete as issue_delete
from test_helpers import build_issue


def _write_issue(project_dir: Path, issue_id: str, parent: str | None = None) -> None:
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    issue = build_issue(issue_id, parent=parent)
    payload = issue.model_dump(by_alias=True, mode="json")
    (issues_dir / f"{issue_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_get_descendant_identifiers_includes_shared_and_local_leaf_first(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    _write_issue(project_dir, "kanbus-root")
    _write_issue(project_dir, "kanbus-child", parent="kanbus-root")
    _write_issue(project_dir, "kanbus-leaf", parent="kanbus-child")

    local_project = tmp_path / "project-local"
    _write_issue(local_project, "kanbus-local-child", parent="kanbus-root")

    descendants = issue_delete.get_descendant_identifiers(project_dir, "kanbus-root")

    assert descendants == ["kanbus-leaf", "kanbus-child", "kanbus-local-child"]


def test_delete_issue_restores_file_when_event_delete_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    issue_path = issues_dir / "kanbus-1.json"
    issue_path.write_text('{"id": "kanbus-1"}\n', encoding="utf-8")
    issue = build_issue("kanbus-1")
    lookup = SimpleNamespace(
        issue=issue, issue_path=issue_path, project_dir=project_dir
    )

    monkeypatch.setattr(issue_delete, "load_issue_from_project", lambda _r, _i: lookup)
    monkeypatch.setattr(
        issue_delete,
        "delete_events_for_issues",
        lambda _events_dir, _ids: (_ for _ in ()).throw(
            RuntimeError("event delete failed")
        ),
    )

    with pytest.raises(issue_delete.IssueDeleteError, match="event delete failed"):
        issue_delete.delete_issue(tmp_path, "kanbus-1")

    assert issue_path.exists()
    restored = json.loads(issue_path.read_text(encoding="utf-8"))
    assert restored["id"] == "kanbus-1"


def test_delete_issue_publishes_deleted_for_shared_issue_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    issue_path = issues_dir / "kanbus-2.json"
    issue_path.write_text('{"id": "kanbus-2"}\n', encoding="utf-8")
    issue = build_issue("kanbus-2")
    lookup = SimpleNamespace(
        issue=issue, issue_path=issue_path, project_dir=project_dir
    )
    published: list[tuple[Path, Path, str, None]] = []

    monkeypatch.setattr(issue_delete, "load_issue_from_project", lambda _r, _i: lookup)
    monkeypatch.setattr(
        issue_delete, "delete_events_for_issues", lambda _events_dir, _ids: None
    )
    monkeypatch.setattr(
        issue_delete,
        "publish_issue_deleted",
        lambda root, project, issue_id, event_id: published.append(
            (root, project, issue_id, event_id)
        ),
    )

    issue_delete.delete_issue(tmp_path, "kanbus-2")

    assert not issue_path.exists()
    assert published == [(tmp_path, project_dir, "kanbus-2", None)]


def test_delete_issue_does_not_publish_for_local_issue_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    local_issues_dir = tmp_path / "project-local" / "issues"
    local_issues_dir.mkdir(parents=True, exist_ok=True)
    issue_path = local_issues_dir / "kanbus-3.json"
    issue_path.write_text('{"id": "kanbus-3"}\n', encoding="utf-8")
    issue = build_issue("kanbus-3")
    lookup = SimpleNamespace(
        issue=issue, issue_path=issue_path, project_dir=project_dir
    )
    published: list[tuple[Path, Path, str, None]] = []

    monkeypatch.setattr(issue_delete, "load_issue_from_project", lambda _r, _i: lookup)
    monkeypatch.setattr(
        issue_delete, "delete_events_for_issues", lambda _events_dir, _ids: None
    )
    monkeypatch.setattr(
        issue_delete,
        "publish_issue_deleted",
        lambda root, project, issue_id, event_id: published.append(
            (root, project, issue_id, event_id)
        ),
    )

    issue_delete.delete_issue(tmp_path, "kanbus-3")

    assert not issue_path.exists()
    assert published == []


def test_delete_issue_wraps_lookup_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        issue_delete,
        "load_issue_from_project",
        lambda _r, _i: (_ for _ in ()).throw(issue_delete.IssueLookupError("missing")),
    )
    with pytest.raises(issue_delete.IssueDeleteError, match="missing"):
        issue_delete.delete_issue(tmp_path, "kanbus-missing")
