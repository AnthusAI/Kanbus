"""Tests for dependency operations."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from taskulus.config import write_default_configuration
from taskulus.dependencies import DependencyError, add_dependency, list_ready_issues
from taskulus.issue_lookup import IssueLookupResult
from taskulus.project import ProjectMarkerError
from taskulus.issue_files import read_issue_from_file, write_issue_to_file
from taskulus.models import DependencyLink, IssueData


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)


def _write_project(root: Path) -> Path:
    marker = root / ".taskulus.yaml"
    marker.write_text("project_dir: project\n", encoding="utf-8")
    project_path = root / "project"
    (project_path / "issues").mkdir(parents=True)
    write_default_configuration(project_path / "config.yaml")
    return project_path


def _make_issue(identifier: str) -> IssueData:
    now = datetime.now(timezone.utc)
    return IssueData(
        id=identifier,
        title="Title",
        type="task",
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


def test_add_dependency_rejects_invalid_type(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(DependencyError, match="invalid dependency type"):
        add_dependency(tmp_path, "tsk-1", "tsk-2", "invalid")


def test_add_dependency_rejects_missing_issue(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    with pytest.raises(DependencyError, match="not found"):
        add_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")


def test_add_dependency_returns_existing_dependency(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    other = _make_issue("tsk-2")
    issue = issue.model_copy(
        update={"dependencies": [DependencyLink(target="tsk-2", type="blocked-by")]}
    )
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    write_issue_to_file(other, project / "issues" / "tsk-2.json")

    updated = add_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")

    assert len(updated.dependencies) == 1
    assert updated.dependencies[0].target == "tsk-2"


def test_add_dependency_writes_link(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    other = _make_issue("tsk-2")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    write_issue_to_file(other, project / "issues" / "tsk-2.json")

    add_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")

    updated = read_issue_from_file(project / "issues" / "tsk-1.json")
    assert updated.dependencies[0].target == "tsk-2"
    assert updated.dependencies[0].dependency_type == "blocked-by"


def test_add_dependency_rejects_missing_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    other = _make_issue("tsk-2")
    issue_path = project / "issues" / "tsk-1.json"
    write_issue_to_file(issue, issue_path)
    write_issue_to_file(other, project / "issues" / "tsk-2.json")

    def fake_lookup(_root: Path, _identifier: str) -> IssueLookupResult:
        return IssueLookupResult(issue=issue, issue_path=issue_path)

    def fake_project_dir(_root: Path) -> Path:
        raise ProjectMarkerError("project not initialized")

    monkeypatch.setattr("taskulus.dependencies.load_issue_from_project", fake_lookup)
    monkeypatch.setattr(
        "taskulus.dependencies.load_project_directory", fake_project_dir
    )

    with pytest.raises(DependencyError, match="project not initialized"):
        add_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")


def test_add_dependency_detects_cycle(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue_a = _make_issue("tsk-a")
    issue_b = _make_issue("tsk-b")
    issue_a = issue_a.model_copy(
        update={"dependencies": [DependencyLink(target="tsk-b", type="blocked-by")]}
    )
    write_issue_to_file(issue_a, project / "issues" / "tsk-a.json")
    write_issue_to_file(issue_b, project / "issues" / "tsk-b.json")

    with pytest.raises(DependencyError, match="cycle detected"):
        add_dependency(tmp_path, "tsk-b", "tsk-a", "blocked-by")


def test_remove_dependency_removes_existing_link(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    other = _make_issue("tsk-2")
    issue = issue.model_copy(
        update={"dependencies": [DependencyLink(target="tsk-2", type="blocked-by")]}
    )
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    write_issue_to_file(other, project / "issues" / "tsk-2.json")

    from taskulus.dependencies import remove_dependency

    updated = remove_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")

    assert updated.dependencies == []


def test_remove_dependency_noops_when_missing_link(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    other = _make_issue("tsk-2")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    write_issue_to_file(other, project / "issues" / "tsk-2.json")

    from taskulus.dependencies import remove_dependency

    updated = remove_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")

    assert updated.dependencies == []


def test_remove_dependency_rejects_missing_issue(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    from taskulus.dependencies import remove_dependency

    with pytest.raises(DependencyError, match="not found"):
        remove_dependency(tmp_path, "tsk-1", "tsk-2", "blocked-by")


def test_list_ready_issues_filters_blocked(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    ready_issue = _make_issue("tsk-ready")
    blocked_issue = _make_issue("tsk-blocked")
    blocked_issue = blocked_issue.model_copy(
        update={"dependencies": [DependencyLink(target="tsk-ready", type="blocked-by")]}
    )
    write_issue_to_file(ready_issue, project / "issues" / "tsk-ready.json")
    write_issue_to_file(blocked_issue, project / "issues" / "tsk-blocked.json")

    ready = list_ready_issues(tmp_path)
    identifiers = {issue.identifier for issue in ready}

    assert "tsk-ready" in identifiers
    assert "tsk-blocked" not in identifiers


def test_list_ready_issues_rejects_missing_project(tmp_path: Path) -> None:
    with pytest.raises(DependencyError, match="project not initialized"):
        list_ready_issues(tmp_path)


def test_list_ready_issues_includes_open_without_dependencies(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    ready_issue = _make_issue("tsk-ready")
    ready_issue = ready_issue.model_copy(update={"status": "in_progress"})
    closed_issue = _make_issue("tsk-closed")
    closed_issue = closed_issue.model_copy(update={"status": "closed"})
    write_issue_to_file(ready_issue, project / "issues" / "tsk-ready.json")
    write_issue_to_file(closed_issue, project / "issues" / "tsk-closed.json")

    ready = list_ready_issues(tmp_path)
    identifiers = {issue.identifier for issue in ready}

    assert "tsk-ready" in identifiers
    assert "tsk-closed" not in identifiers
