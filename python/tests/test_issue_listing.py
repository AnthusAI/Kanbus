"""Tests for issue listing."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from taskulus.config import write_default_configuration
from taskulus.issue_listing import IssueListingError, list_issues
from taskulus.issue_files import write_issue_to_file
from taskulus.models import IssueData
from taskulus.cache import collect_issue_file_mtimes, write_cache


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
        title="Test",
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


def test_list_issues_uses_daemon_payloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)

    payload = _make_issue("tsk-1").model_dump(by_alias=True, mode="json")

    monkeypatch.setattr("taskulus.issue_listing.is_daemon_enabled", lambda: True)
    monkeypatch.setattr(
        "taskulus.issue_listing.request_index_list", lambda root: [payload]
    )

    issues = list_issues(tmp_path)

    assert len(issues) == 1
    assert issues[0].identifier == "tsk-1"


def test_list_issues_daemon_failure_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)

    def raise_error(root: Path) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("taskulus.issue_listing.is_daemon_enabled", lambda: True)
    monkeypatch.setattr("taskulus.issue_listing.request_index_list", raise_error)

    with pytest.raises(IssueListingError, match="boom"):
        list_issues(tmp_path)


def test_list_issues_local_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")

    monkeypatch.setattr("taskulus.issue_listing.is_daemon_enabled", lambda: False)
    issues = list_issues(tmp_path)

    assert len(issues) == 1
    assert issues[0].identifier == "tsk-1"


def test_list_issues_uses_cached_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    monkeypatch.setattr("taskulus.issue_listing.is_daemon_enabled", lambda: False)

    cache_path = project / ".cache" / "index.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    mtimes = collect_issue_file_mtimes(project / "issues")
    write_cache(
        index=type(
            "Index",
            (),
            {"by_id": {issue.identifier: issue}, "reverse_dependencies": {}},
        )(),
        cache_path=cache_path,
        file_mtimes=mtimes,
    )

    issues = list_issues(tmp_path)

    assert len(issues) == 1
    assert issues[0].identifier == "tsk-1"


def test_list_issues_local_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setattr("taskulus.issue_listing.is_daemon_enabled", lambda: False)
    monkeypatch.setattr(
        "taskulus.issue_listing._list_issues_locally",
        lambda _root: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(IssueListingError, match="boom"):
        list_issues(tmp_path)
