"""Tests for issue creation, update, display, and deletion."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from taskulus.config import write_default_configuration
from taskulus.issue_close import IssueCloseError, close_issue
from taskulus.issue_creation import IssueCreationError, create_issue
from taskulus.issue_delete import IssueDeleteError, delete_issue
from taskulus.issue_display import format_issue_for_display
from taskulus.issue_files import read_issue_from_file, write_issue_to_file
from taskulus.issue_lookup import IssueLookupError, load_issue_from_project
from taskulus.issue_update import IssueUpdateError, update_issue
from taskulus.issue_lookup import IssueLookupResult
from taskulus.models import IssueData
from taskulus.project import ProjectMarkerError


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)


def _write_project(root: Path, project_dir: str = "project") -> Path:
    marker = root / ".taskulus.yaml"
    marker.write_text(f"project_dir: {project_dir}\n", encoding="utf-8")
    project_path = root / project_dir
    (project_path / "issues").mkdir(parents=True)
    write_default_configuration(project_path / "config.yaml")
    return project_path


def _make_issue(identifier: str, issue_type: str = "task") -> IssueData:
    now = datetime.now(timezone.utc)
    return IssueData(
        id=identifier,
        title="Test",
        type=issue_type,
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


def test_create_issue_requires_project_marker(tmp_path: Path) -> None:
    with pytest.raises(IssueCreationError, match="project not initialized"):
        create_issue(
            root=tmp_path,
            title="Title",
            issue_type=None,
            priority=None,
            assignee=None,
            parent=None,
            labels=[],
            description="",
        )


def test_create_issue_rejects_invalid_type(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueCreationError, match="unknown issue type"):
        create_issue(
            root=tmp_path,
            title="Title",
            issue_type="invalid",
            priority=None,
            assignee=None,
            parent=None,
            labels=[],
            description="",
        )


def test_create_issue_rejects_invalid_priority(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueCreationError, match="invalid priority"):
        create_issue(
            root=tmp_path,
            title="Title",
            issue_type=None,
            priority=9,
            assignee=None,
            parent=None,
            labels=[],
            description="",
        )


def test_create_issue_rejects_missing_parent(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueCreationError, match="not found"):
        create_issue(
            root=tmp_path,
            title="Title",
            issue_type=None,
            priority=None,
            assignee=None,
            parent="tsk-missing",
            labels=[],
            description="",
        )


def test_create_issue_rejects_invalid_parent_child(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    parent = _make_issue("tsk-parent", issue_type="bug")
    write_issue_to_file(parent, project / "issues" / "tsk-parent.json")
    with pytest.raises(IssueCreationError, match="invalid parent-child"):
        create_issue(
            root=tmp_path,
            title="Title",
            issue_type="task",
            priority=None,
            assignee=None,
            parent="tsk-parent",
            labels=[],
            description="",
        )


def test_issue_display_includes_description() -> None:
    issue = _make_issue("tsk-1")
    issue = issue.model_copy(update={"description": "Details"})
    text = format_issue_for_display(issue)
    assert "Description:" in text
    assert "Details" in text


def test_issue_display_omits_description_when_empty() -> None:
    issue = _make_issue("tsk-1")
    text = format_issue_for_display(issue)
    assert "Description:" not in text


def test_load_issue_from_project_errors(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueLookupError, match="not found"):
        load_issue_from_project(tmp_path, "tsk-missing")


def test_load_issue_from_project_requires_marker(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with pytest.raises(IssueLookupError, match="project not initialized"):
        load_issue_from_project(tmp_path, "tsk-1")


def test_update_issue_rejects_missing_issue(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueUpdateError, match="not found"):
        update_issue(tmp_path, "tsk-missing", None, None, None)


def test_update_issue_requires_project_marker(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with pytest.raises(IssueUpdateError, match="project not initialized"):
        update_issue(tmp_path, "tsk-1", None, None, None)


def test_update_issue_rejects_invalid_transition(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    with pytest.raises(IssueUpdateError, match="invalid transition"):
        update_issue(tmp_path, "tsk-1", None, None, "blocked")


def test_update_issue_reports_project_marker_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    issue_path = project / "issues" / "tsk-1.json"
    write_issue_to_file(issue, issue_path)

    def fake_lookup(_root: Path, _identifier: str) -> IssueLookupResult:
        return IssueLookupResult(issue=issue, issue_path=issue_path)

    def fake_project_dir(_root: Path) -> Path:
        raise ProjectMarkerError("project not initialized")

    monkeypatch.setattr("taskulus.issue_update.load_issue_from_project", fake_lookup)
    monkeypatch.setattr(
        "taskulus.issue_update.load_project_directory", fake_project_dir
    )

    with pytest.raises(IssueUpdateError, match="project not initialized"):
        update_issue(tmp_path, "tsk-1", None, None, None)


def test_update_issue_applies_title_and_description(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")

    updated = update_issue(tmp_path, "tsk-1", "New", "Body", None)

    assert updated.title == "New"
    assert updated.description == "Body"


def test_close_issue_wraps_update_errors(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueCloseError, match="not found"):
        close_issue(tmp_path, "tsk-missing")


def test_delete_issue_missing(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(IssueDeleteError, match="not found"):
        delete_issue(tmp_path, "tsk-missing")


def test_delete_issue_removes_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    issue_path = project / "issues" / "tsk-1.json"
    write_issue_to_file(issue, issue_path)

    delete_issue(tmp_path, "tsk-1")

    assert not issue_path.exists()
    with pytest.raises(IssueLookupError, match="not found"):
        load_issue_from_project(tmp_path, "tsk-1")


def test_close_issue_sets_status_closed(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")

    closed = close_issue(tmp_path, "tsk-1")

    assert closed.status == "closed"
    assert closed.closed_at is not None


def test_read_issue_from_file_round_trip(tmp_path: Path) -> None:
    issue = _make_issue("tsk-1")
    issue_path = tmp_path / "tsk-1.json"
    write_issue_to_file(issue, issue_path)

    loaded = read_issue_from_file(issue_path)

    assert loaded.identifier == "tsk-1"
