from __future__ import annotations

from pathlib import Path

import click

from kanbus import cli


def test_should_check_project_structure_ignores_setup_commands() -> None:
    context = click.Context(click.Command("kanbus"))
    context.invoked_subcommand = "setup"
    assert cli._should_check_project_structure(context) is False
    context.invoked_subcommand = "list"
    assert cli._should_check_project_structure(context) is True


def test_delete_terminal_is_interactive_respects_force_env(monkeypatch) -> None:
    monkeypatch.setenv("KANBUS_FORCE_INTERACTIVE", "1")
    assert cli._delete_terminal_is_interactive() is True


def test_resolve_beads_root_finds_parent_beads_directory(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    nested = root / "python" / "subdir"
    (root / ".beads").mkdir(parents=True)
    nested.mkdir(parents=True)
    assert cli._resolve_beads_root(nested) == root
