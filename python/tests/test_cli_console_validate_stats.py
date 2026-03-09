from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.console_snapshot import ConsoleSnapshotError
from kanbus.maintenance import ProjectStatsError, ProjectValidationError


def _run(args: list[str]) -> object:
    runner = CliRunner()
    return runner.invoke(cli.cli, args)


def test_console_snapshot_success_and_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "build_console_snapshot", lambda _root: {"ok": True})

    result = _run(["console", "snapshot"])
    assert result.exit_code == 0
    assert '"ok": true' in result.output

    monkeypatch.setattr(
        cli,
        "build_console_snapshot",
        lambda _root: (_ for _ in ()).throw(ConsoleSnapshotError("snap fail")),
    )
    result_error = _run(["console", "snapshot"])
    assert result_error.exit_code != 0
    assert "snap fail" in result_error.output


@pytest.mark.parametrize(
    "args",
    [
        ["console", "focus", "kanbus-1"],
        ["console", "focus", "kanbus-1", "--comment", "c1"],
        ["console", "unfocus"],
        ["console", "view", "issues"],
        ["console", "search", "text"],
        ["console", "search", "--clear"],
        ["console", "maximize"],
        ["console", "restore"],
        ["console", "close-detail"],
        ["console", "toggle-settings"],
        ["console", "reload"],
        ["console", "set-setting", "mode", "dark"],
        ["console", "collapse", "open"],
        ["console", "collapse-column", "open"],
        ["console", "expand", "open"],
        ["console", "expand-column", "open"],
        ["console", "select", "kanbus-1"],
    ],
)
def test_console_deprecated_commands(args: list[str]) -> None:
    result = _run(args)
    assert result.exit_code != 0
    assert "deprecated" in result.output.lower()


def test_console_status_and_get_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(cli, "fetch_console_ui_state", lambda _root: None)
    result_none = _run(["console", "status"])
    assert result_none.exit_code == 0
    assert "Console server is not running." in result_none.output

    state = {
        "focused_issue_id": "kanbus-1",
        "view_mode": "issues",
        "search_query": "abc",
    }
    monkeypatch.setattr(cli, "fetch_console_ui_state", lambda _root: state)
    result_status = _run(["console", "status"])
    assert "focus:  kanbus-1" in result_status.output
    assert "view:   issues" in result_status.output
    assert "search: abc" in result_status.output

    result_focus = _run(["console", "get", "focus"])
    assert result_focus.exit_code == 0
    assert "kanbus-1" in result_focus.output

    result_view = _run(["console", "get", "view"])
    assert result_view.exit_code == 0
    assert "issues" in result_view.output

    result_search = _run(["console", "get", "search"])
    assert result_search.exit_code == 0
    assert "abc" in result_search.output

    monkeypatch.setattr(cli, "fetch_console_ui_state", lambda _root: {})
    assert "none" in _run(["console", "get", "focus"]).output
    assert "none" in _run(["console", "get", "view"]).output
    assert "none" in _run(["console", "get", "search"]).output

    monkeypatch.setattr(cli, "fetch_console_ui_state", lambda _root: None)
    assert "Console server is not running." in _run(["console", "get", "focus"]).output
    assert "Console server is not running." in _run(["console", "get", "view"]).output
    assert "Console server is not running." in _run(["console", "get", "search"]).output


def test_validate_command_success_and_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    called: list[Path] = []
    monkeypatch.setattr(cli, "validate_project", lambda root: called.append(root))

    result = _run(["validate"])
    assert result.exit_code == 0
    assert called == [tmp_path]

    monkeypatch.setattr(
        cli,
        "validate_project",
        lambda _root: (_ for _ in ()).throw(ProjectValidationError("invalid project")),
    )
    result_error = _run(["validate"])
    assert result_error.exit_code != 0
    assert "invalid project" in result_error.output


def test_stats_command_success_and_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "collect_project_stats",
        lambda _root: SimpleNamespace(
            total=3,
            open_count=2,
            closed_count=1,
            type_counts={"task": 2, "bug": 1},
        ),
    )

    result = _run(["stats"])
    assert result.exit_code == 0
    assert "total issues: 3" in result.output
    assert "open issues: 2" in result.output
    assert "closed issues: 1" in result.output
    assert "type: bug: 1" in result.output
    assert "type: task: 2" in result.output

    monkeypatch.setattr(
        cli,
        "collect_project_stats",
        lambda _root: (_ for _ in ()).throw(ProjectStatsError("stats fail")),
    )
    result_error = _run(["stats"])
    assert result_error.exit_code != 0
    assert "stats fail" in result_error.output
