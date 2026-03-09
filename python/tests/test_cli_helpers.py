from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click

from kanbus import cli


def test_should_check_project_structure_ignores_setup_commands() -> None:
    context = click.Context(click.Command("kanbus"))
    context.invoked_subcommand = None
    assert cli._should_check_project_structure(context) is False
    context.invoked_subcommand = "setup"
    assert cli._should_check_project_structure(context) is False
    context.invoked_subcommand = "list"
    assert cli._should_check_project_structure(context) is True


def test_delete_terminal_is_interactive_respects_force_env(monkeypatch) -> None:
    monkeypatch.setenv("KANBUS_FORCE_INTERACTIVE", "1")
    assert cli._delete_terminal_is_interactive() is True


def test_delete_terminal_is_interactive_false_without_tty(monkeypatch) -> None:
    monkeypatch.delenv("KANBUS_FORCE_INTERACTIVE", raising=False)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    assert cli._delete_terminal_is_interactive() is False


def test_resolve_beads_root_finds_parent_beads_directory(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    nested = root / "python" / "subdir"
    (root / ".beads").mkdir(parents=True)
    nested.mkdir(parents=True)
    assert cli._resolve_beads_root(nested) == root


def test_resolve_beads_root_uses_configuration_marker_parent(
    monkeypatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".kanbus.yml"
    marker.write_text("project_key: kanbus\n", encoding="utf-8")
    monkeypatch.setattr(cli, "get_configuration_path", lambda _cwd: marker)
    assert cli._resolve_beads_root(tmp_path / "nested") == tmp_path


def test_resolve_beads_mode_uses_commandline_override() -> None:
    context = click.Context(click.Command("kanbus"))
    context.get_parameter_source = lambda _name: click.core.ParameterSource.COMMANDLINE
    assert cli._resolve_beads_mode(context, beads_mode=True) == (True, True)


def test_maybe_prompt_project_repair_repairs_when_confirmed(monkeypatch, tmp_path: Path) -> None:
    context = click.Context(click.Command("kanbus"))
    context.invoked_subcommand = "list"
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda _root, allow_uninitialized: SimpleNamespace(
            missing_project_dir=True,
            missing_issues_dir=False,
            missing_events_dir=True,
        ),
    )
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda _prompt, default: True)
    repaired: list[Path] = []
    monkeypatch.setattr(
        cli,
        "repair_project_structure",
        lambda root, _plan: repaired.append(root),
    )
    messages: list[str] = []
    monkeypatch.setattr(
        cli.click,
        "echo",
        lambda message, err: messages.append(message),
    )

    cli._maybe_prompt_project_repair(context)

    assert repaired == [tmp_path]
    assert messages == ["Project structure repaired."]


def test_maybe_prompt_project_repair_skips_when_no_plan(monkeypatch, tmp_path: Path) -> None:
    context = click.Context(click.Command("kanbus"))
    context.invoked_subcommand = "list"
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda _root, allow_uninitialized: None,
    )
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    confirmed: list[bool] = []
    monkeypatch.setattr(
        cli.click,
        "confirm",
        lambda _prompt, default: confirmed.append(True),
    )

    cli._maybe_prompt_project_repair(context)

    assert confirmed == []


def test_maybe_prompt_project_repair_permission_and_noninteractive_paths(
    monkeypatch, tmp_path: Path
) -> None:
    context = click.Context(click.Command("kanbus"))
    context.invoked_subcommand = "list"
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("denied")),
    )
    cli._maybe_prompt_project_repair(context)

    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda _root, allow_uninitialized: SimpleNamespace(
            missing_project_dir=True,
            missing_issues_dir=True,
            missing_events_dir=True,
        ),
    )
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    cli._maybe_prompt_project_repair(context)


def test_maybe_prompt_project_repair_includes_missing_issues_in_prompt(
    monkeypatch, tmp_path: Path
) -> None:
    context = click.Context(click.Command("kanbus"))
    context.invoked_subcommand = "list"
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda _root, allow_uninitialized: SimpleNamespace(
            missing_project_dir=False,
            missing_issues_dir=True,
            missing_events_dir=False,
        ),
    )
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    prompts: list[str] = []
    monkeypatch.setattr(
        cli.click,
        "confirm",
        lambda prompt, default=False: prompts.append(prompt) or False,
    )
    cli._maybe_prompt_project_repair(context)
    assert prompts and "project/issues" in prompts[0]
