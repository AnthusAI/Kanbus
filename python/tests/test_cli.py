"""Tests for CLI command dispatch."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from taskulus.cli import cli
from taskulus.config import write_default_configuration
from taskulus.issue_files import write_issue_to_file
from taskulus.dependencies import DependencyError
from taskulus.doctor import DoctorError
from taskulus.issue_listing import IssueListingError
from taskulus.models import IssueData
from taskulus.queries import QueryError


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


def _run_cli(cwd: Path, args: list[str]) -> object:
    runner = CliRunner()
    previous = Path.cwd()
    try:
        os.chdir(cwd)
        return runner.invoke(cli, args)
    finally:
        os.chdir(previous)


def test_init_requires_git_repo(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, ["init"])
    assert result.exit_code == 1
    assert "not a git repository" in result.output


def test_init_rejects_existing_project(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["init"])
    assert result.exit_code == 1
    assert "already initialized" in result.output


def test_create_requires_title(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["create"])
    assert result.exit_code == 1
    assert "title is required" in result.output


def test_create_invalid_type_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["create", "Title", "--type", "invalid"])
    assert result.exit_code == 1
    assert "unknown issue type" in result.output


def test_show_json_output(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    result = _run_cli(tmp_path, ["show", "tsk-1", "--json"])
    assert result.exit_code == 0
    assert '"id": "tsk-1"' in result.output


def test_show_missing_issue_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["show", "tsk-missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_list_outputs_identifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    monkeypatch.setenv("TASKULUS_NO_DAEMON", "1")
    result = _run_cli(tmp_path, ["list"])
    assert result.exit_code == 0
    assert "tsk-1 Title" in result.output


def test_list_reports_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setattr(
        "taskulus.cli.list_issues",
        lambda _root: (_ for _ in ()).throw(IssueListingError("boom")),
    )
    result = _run_cli(tmp_path, ["list"])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_list_reports_query_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setattr(
        "taskulus.cli.list_issues",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(QueryError("invalid sort key")),
    )
    result = _run_cli(tmp_path, ["list", "--sort", "bad"])
    assert result.exit_code == 1
    assert "invalid sort key" in result.output


def test_dep_add_requires_target(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["dep", "add", "tsk-1"])
    assert result.exit_code == 1
    assert "dependency target is required" in result.output


def test_dep_remove_requires_target(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["dep", "remove", "tsk-1"])
    assert result.exit_code == 1
    assert "dependency target is required" in result.output


def test_dep_add_reports_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setattr(
        "taskulus.cli.add_dependency",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DependencyError("boom")),
    )
    result = _run_cli(tmp_path, ["dep", "add", "tsk-1", "--blocked-by", "tsk-2"])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_dep_remove_reports_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setattr(
        "taskulus.cli.remove_dependency",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DependencyError("boom")),
    )
    result = _run_cli(tmp_path, ["dep", "remove", "tsk-1", "--blocked-by", "tsk-2"])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_ready_reports_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setattr(
        "taskulus.cli.list_ready_issues",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(DependencyError("boom")),
    )
    result = _run_cli(tmp_path, ["ready"])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_daemon_status_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setenv("TASKULUS_NO_DAEMON", "1")
    result = _run_cli(tmp_path, ["daemon-status"])
    assert result.exit_code == 1
    assert "daemon disabled" in result.output


def test_daemon_stop_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    monkeypatch.setenv("TASKULUS_NO_DAEMON", "1")
    result = _run_cli(tmp_path, ["daemon-stop"])
    assert result.exit_code == 1
    assert "daemon disabled" in result.output


def test_daemon_status_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)

    def fake_status(_root: Path) -> dict[str, object]:
        return {"status": "ok"}

    monkeypatch.delenv("TASKULUS_NO_DAEMON", raising=False)
    monkeypatch.setattr("taskulus.cli.request_status", fake_status)

    result = _run_cli(tmp_path, ["daemon-status"])
    assert result.exit_code == 0
    assert '"status": "ok"' in result.output


def test_daemon_stop_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)

    def fake_shutdown(_root: Path) -> dict[str, object]:
        return {"status": "stopped"}

    monkeypatch.delenv("TASKULUS_NO_DAEMON", raising=False)
    monkeypatch.setattr("taskulus.cli.request_shutdown", fake_shutdown)

    result = _run_cli(tmp_path, ["daemon-stop"])
    assert result.exit_code == 0
    assert '"status": "stopped"' in result.output


def test_comment_command_updates_issue(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    result = _run_cli(tmp_path, ["comment", "tsk-1", "Note"])
    assert result.exit_code == 0


def test_comment_missing_issue_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["comment", "tsk-missing", "Note"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_update_command_invalid_transition(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    result = _run_cli(tmp_path, ["update", "tsk-1", "--status", "blocked"])
    assert result.exit_code == 1
    assert "invalid transition" in result.output


def test_update_missing_issue_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["update", "tsk-missing", "--title", "New"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_close_and_delete_commands(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")

    result = _run_cli(tmp_path, ["close", "tsk-1"])
    assert result.exit_code == 0
    result = _run_cli(tmp_path, ["delete", "tsk-1"])
    assert result.exit_code == 0


def test_close_missing_issue_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["close", "tsk-missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_delete_missing_issue_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)
    result = _run_cli(tmp_path, ["delete", "tsk-missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_doctor_command_reports_ok(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    project = _write_project(tmp_path)
    result = _run_cli(tmp_path, ["doctor"])
    assert result.exit_code == 0
    assert str(project) in result.output


def test_doctor_command_reports_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _write_project(tmp_path)

    def fake_doctor(_root: Path) -> object:
        raise DoctorError("boom")

    monkeypatch.setattr("taskulus.cli.run_doctor", fake_doctor)

    result = _run_cli(tmp_path, ["doctor"])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_migrate_command_success(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    issues_path = beads_dir / "issues.jsonl"
    issues_path.write_text(
        '{"id": "tsk-1", "title": "Title", "issue_type": "task", "status": "open", "priority": 2, "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    result = _run_cli(tmp_path, ["migrate"])
    assert result.exit_code == 0
    assert "migrated 1 issues" in result.output


def test_migrate_command_reports_error(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    result = _run_cli(tmp_path, ["migrate"])
    assert result.exit_code == 1
    assert "no .beads directory" in result.output


def test_module_main_invokes_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["taskulus.cli", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("taskulus.cli", run_name="__main__")
    assert excinfo.value.code == 0
