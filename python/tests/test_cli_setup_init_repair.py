from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.config_loader import ConfigurationError
from kanbus.file_io import InitializationError
from kanbus.project import ProjectMarkerError


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_setup_agents_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(cli, "ensure_agents_file", lambda root, force: calls.append(("agents", force)))
    monkeypatch.setattr(cli, "_ensure_project_guard_files", lambda root: calls.append(("guards", False)))

    result = _run(["setup", "agents", "--force"])
    assert result.exit_code == 0
    assert calls == [("agents", True), ("guards", False)]


def test_init_command_and_setup_agents_prompt_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "ensure_git_repository", lambda _root: None)
    monkeypatch.setattr(cli, "_maybe_run_setup_agents", lambda _root: None)
    init_calls: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        cli,
        "initialize_project",
        lambda root, create_local: init_calls.append((root, create_local)),
    )

    cli.init.callback(True)
    assert init_calls == [(tmp_path, True)]

    monkeypatch.setattr(
        cli,
        "initialize_project",
        lambda *_a, **_k: (_ for _ in ()).throw(InitializationError("init fail")),
    )
    with pytest.raises(cli.click.ClickException, match="init fail"):
        cli.init.callback(False)


def test_maybe_run_setup_agents_prompt_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    called: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        cli,
        "ensure_agents_file",
        lambda root, force=False: called.append((root, force)),
    )
    cli._maybe_run_setup_agents(tmp_path)
    assert called == []

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: False)
    cli._maybe_run_setup_agents(tmp_path)
    assert called == []

    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: True)
    cli._maybe_run_setup_agents(tmp_path)
    assert called == [(tmp_path, False)]


def test_repair_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(ProjectMarkerError("pm fail")),
    )
    with pytest.raises(cli.click.ClickException, match="pm fail"):
        cli.repair.callback(True)

    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(ConfigurationError("cfg fail")),
    )
    with pytest.raises(cli.click.ClickException, match="cfg fail"):
        cli.repair.callback(True)

    messages: list[str] = []
    monkeypatch.setattr(cli.click, "echo", lambda message: messages.append(message))
    monkeypatch.setattr(cli, "detect_repairable_project_issues", lambda *_a, **_k: None)
    cli.repair.callback(True)
    assert "already healthy" in messages[-1]

    plan = SimpleNamespace(
        missing_project_dir=True,
        missing_issues_dir=True,
        missing_events_dir=True,
    )
    monkeypatch.setattr(cli, "detect_repairable_project_issues", lambda *_a, **_k: plan)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    with pytest.raises(cli.click.ClickException, match="re-run with --yes"):
        cli.repair.callback(False)

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: False)
    cli.repair.callback(False)
    assert "Repair cancelled." in messages[-1]

    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: True)
    repaired: list[Path] = []
    monkeypatch.setattr(cli, "repair_project_structure", lambda root, _plan: repaired.append(root))
    cli.repair.callback(False)
    assert "Project structure repaired." in messages[-1]
    assert repaired == [tmp_path]


def test_resolve_beads_mode_projectmarker_and_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = cli.click.Context(cli.click.Command("kanbus"))
    context.get_parameter_source = lambda _name: cli.click.core.ParameterSource.DEFAULT

    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ProjectMarkerError("no project")),
    )
    assert cli._resolve_beads_mode(context, beads_mode=False) == (False, False)

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("bad config")),
    )
    with pytest.raises(cli.click.ClickException, match="bad config"):
        cli._resolve_beads_mode(context, beads_mode=False)
