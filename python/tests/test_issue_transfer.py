from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import issue_transfer
from kanbus.issue_lookup import IssueLookupError

from test_helpers import build_issue


def write_issue(path: Path, issue_id: str) -> None:
    issue = build_issue(issue_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(issue.model_dump(by_alias=True, mode="json")),
        encoding="utf-8",
    )


def test_promote_issue_moves_local_to_shared_and_emits_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    local_issue = local_dir / "issues" / "kanbus-1.json"
    shared_issue = project_dir / "issues" / "kanbus-1.json"
    shared_issue.parent.mkdir(parents=True, exist_ok=True)
    write_issue(local_issue, "kanbus-1")

    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: SimpleNamespace(project_dir=project_dir),
    )
    monkeypatch.setattr(issue_transfer, "find_project_local_directory", lambda _p: local_dir)
    monkeypatch.setattr(issue_transfer, "get_current_user", lambda: "tester")
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        issue_transfer,
        "publish_issue_mutation",
        lambda *_args: calls.setdefault("publish_mutation", True),
    )

    issue = issue_transfer.promote_issue(root, "kanbus-1")

    assert issue.identifier == "kanbus-1"
    assert shared_issue.exists()
    assert not local_issue.exists()
    assert calls.get("publish_mutation") is True
    event_files = list((project_dir / "events").glob("*.json"))
    assert len(event_files) == 1
    payload = json.loads(event_files[0].read_text(encoding="utf-8"))
    assert payload["event_type"] == "issue_promoted"


def test_promote_issue_rolls_back_when_event_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    local_issue = local_dir / "issues" / "kanbus-2.json"
    shared_issue = project_dir / "issues" / "kanbus-2.json"
    shared_issue.parent.mkdir(parents=True, exist_ok=True)
    write_issue(local_issue, "kanbus-2")

    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: SimpleNamespace(project_dir=project_dir),
    )
    monkeypatch.setattr(issue_transfer, "find_project_local_directory", lambda _p: local_dir)
    monkeypatch.setattr(
        issue_transfer, "write_events_batch", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with pytest.raises(issue_transfer.IssueTransferError, match="boom"):
        issue_transfer.promote_issue(root, "kanbus-2")

    assert local_issue.exists()
    assert not shared_issue.exists()


def test_promote_issue_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    project_dir = root / "project"
    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: (_ for _ in ()).throw(IssueLookupError("missing")),
    )
    with pytest.raises(issue_transfer.IssueTransferError, match="missing"):
        issue_transfer.promote_issue(root, "kanbus-missing")

    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: SimpleNamespace(project_dir=project_dir),
    )
    monkeypatch.setattr(issue_transfer, "find_project_local_directory", lambda _p: None)
    with pytest.raises(issue_transfer.IssueTransferError, match="not found"):
        issue_transfer.promote_issue(root, "kanbus-missing")

    local_dir = root / "project-local"
    monkeypatch.setattr(issue_transfer, "find_project_local_directory", lambda _p: local_dir)
    with pytest.raises(issue_transfer.IssueTransferError, match="not found"):
        issue_transfer.promote_issue(root, "kanbus-missing")

    (local_dir / "issues").mkdir(parents=True, exist_ok=True)
    write_issue(local_dir / "issues" / "kanbus-dupe.json", "kanbus-dupe")
    target = project_dir / "issues" / "kanbus-dupe.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_issue(target, "kanbus-dupe")
    with pytest.raises(issue_transfer.IssueTransferError, match="already exists"):
        issue_transfer.promote_issue(root, "kanbus-dupe")


def test_localize_issue_moves_shared_to_local_and_emits_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    shared_issue = project_dir / "issues" / "kanbus-3.json"
    local_issue = local_dir / "issues" / "kanbus-3.json"
    local_issue.parent.mkdir(parents=True, exist_ok=True)
    write_issue(shared_issue, "kanbus-3")

    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: SimpleNamespace(project_dir=project_dir),
    )
    monkeypatch.setattr(issue_transfer, "ensure_project_local_directory", lambda _p: local_dir)
    monkeypatch.setattr(issue_transfer, "get_current_user", lambda: "tester")
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        issue_transfer,
        "publish_issue_deleted",
        lambda *_args: calls.setdefault("publish_deleted", True),
    )

    issue = issue_transfer.localize_issue(root, "kanbus-3")

    assert issue.identifier == "kanbus-3"
    assert local_issue.exists()
    assert not shared_issue.exists()
    assert calls.get("publish_deleted") is True
    event_files = list((local_dir / "events").glob("*.json"))
    assert len(event_files) == 1
    payload = json.loads(event_files[0].read_text(encoding="utf-8"))
    assert payload["event_type"] == "issue_localized"


def test_localize_issue_rolls_back_when_event_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    shared_issue = project_dir / "issues" / "kanbus-4.json"
    local_issue = local_dir / "issues" / "kanbus-4.json"
    local_issue.parent.mkdir(parents=True, exist_ok=True)
    write_issue(shared_issue, "kanbus-4")

    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: SimpleNamespace(project_dir=project_dir),
    )
    monkeypatch.setattr(issue_transfer, "ensure_project_local_directory", lambda _p: local_dir)
    monkeypatch.setattr(
        issue_transfer, "write_events_batch", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with pytest.raises(issue_transfer.IssueTransferError, match="boom"):
        issue_transfer.localize_issue(root, "kanbus-4")

    assert shared_issue.exists()
    assert not local_issue.exists()


def test_localize_issue_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    project_dir = root / "project"
    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: (_ for _ in ()).throw(IssueLookupError("missing")),
    )
    with pytest.raises(issue_transfer.IssueTransferError, match="missing"):
        issue_transfer.localize_issue(root, "kanbus-missing")

    monkeypatch.setattr(
        issue_transfer,
        "load_issue_from_project",
        lambda _root, _id: SimpleNamespace(project_dir=project_dir),
    )
    with pytest.raises(
        issue_transfer.IssueTransferError, match="issue is not in shared project"
    ):
        issue_transfer.localize_issue(root, "kanbus-missing")

    shared_issue = project_dir / "issues" / "kanbus-5.json"
    local_dir = root / "project-local"
    local_issue = local_dir / "issues" / "kanbus-5.json"
    write_issue(shared_issue, "kanbus-5")
    write_issue(local_issue, "kanbus-5")
    monkeypatch.setattr(issue_transfer, "ensure_project_local_directory", lambda _p: local_dir)
    with pytest.raises(issue_transfer.IssueTransferError, match="already exists"):
        issue_transfer.localize_issue(root, "kanbus-5")
