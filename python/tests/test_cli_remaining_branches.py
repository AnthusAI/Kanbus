from __future__ import annotations

from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import click
from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.config_loader import ConfigurationError
from kanbus.hooks import HookEvent, HookExecutionError, HookPhase
from kanbus.issue_comment import IssueCommentError
from kanbus.issue_lookup import IssueLookupError
from kanbus.migration import MigrationError

from test_helpers import build_issue, build_project_configuration


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_run_lifecycle_hooks_helper_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = click.Context(click.Command("kanbus"))
    context.obj = None
    cli._run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_LIST,
        root=tmp_path,
    )

    context.obj = {"beads_mode": False, "no_hooks": False, "no_guidance": False}
    monkeypatch.setattr(
        cli,
        "run_lifecycle_hooks",
        lambda **_k: (_ for _ in ()).throw(HookExecutionError("hook fail")),
    )
    with pytest.raises(click.ClickException, match="hook fail"):
        cli._run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_LIST,
            root=tmp_path,
        )


def test_dep_parser_and_beads_remove_error_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = click.Context(click.Command("dep"))
    context.obj = {}

    with context.scope(cleanup=False):
        with pytest.raises(click.ClickException, match="usage"):
            cli.dep.callback(())
        with pytest.raises(click.ClickException, match="tree requires an identifier"):
            cli.dep.callback(("tree",))
        with pytest.raises(click.ClickException, match="tree requires an identifier"):
            cli.dep.callback(("tree", ""))
        with pytest.raises(click.ClickException, match="depth must be a number"):
            cli.dep.callback(("tree", "kanbus-1", "--depth", "x"))

    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "build_dependency_tree", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(cli, "render_dependency_tree", lambda *_a, **_k: "rendered")
    with context.scope(cleanup=False):
        cli.dep.callback(("tree", "kanbus-1", "--unknown", "value"))

    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(
        "kanbus.beads_write.remove_beads_dependency",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.BeadsWriteError("beads remove fail")),
    )
    with context.scope(cleanup=False):
        with pytest.raises(click.ClickException, match="beads remove fail"):
            cli.dep.callback(("kanbus-1", "remove", "blocked-by", "kanbus-2"))


def test_snyk_and_jira_configuration_error_callbacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("cfg fail")),
    )

    snyk_context = click.Context(cli.snyk_pull)
    with snyk_context.scope(cleanup=False):
        with pytest.raises(click.ClickException, match="cfg fail"):
            cli.snyk_pull.callback(False, None, None, None)

    jira_context = click.Context(cli.jira_pull)
    jira_context.obj = {"beads_mode": False, "no_hooks": False, "no_guidance": False}
    with jira_context.scope(cleanup=False):
        with pytest.raises(click.ClickException, match="cfg fail"):
            cli.jira_pull.callback(False)


def test_show_update_and_comment_remaining_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_resolve_beads_mode", lambda _ctx, _beads: (False, False))
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    config_calls = {"count": 0}

    def _load_config_show_then_ok(_p):
        config_calls["count"] += 1
        if config_calls["count"] == 1:
            raise ConfigurationError("cfg read fail")
        return build_project_configuration()

    monkeypatch.setattr(cli, "load_project_configuration", _load_config_show_then_ok)
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(cli, "load_issue_from_project", lambda *_a, **_k: SimpleNamespace(issue=build_issue("kanbus-1")))
    monkeypatch.setattr(cli, "format_issue_for_display", lambda *_a, **_k: "shown")
    result_show = _run(["show", "kanbus-1"])
    assert result_show.exit_code == 0
    assert "shown" in result_show.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]),
    )
    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: None)
    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueLookupError("missing before")),
    )
    monkeypatch.setattr(cli, "update_issue", lambda **_k: build_issue("kanbus-1"))
    emitted: list[str] = []
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: emitted.append("emit"))
    monkeypatch.setattr(cli, "format_issue_key", lambda identifier, project_context=False: identifier)
    result_update_regular = _run(["update", "kanbus-1", "--description", "desc", "--no-validate"])
    assert result_update_regular.exit_code == 0
    assert emitted

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr("kanbus.beads_write.add_beads_comment", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(MigrationError("after missing")),
    )
    result_comment_beads_after_missing = _run(["comment", "kanbus-1", "hello", "--no-validate"])
    assert result_comment_beads_after_missing.exit_code == 0

    monkeypatch.setattr(
        "kanbus.beads_write.add_beads_comment",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.BeadsWriteError("beads comment fail")),
    )
    result_comment_beads_fail = _run(["comment", "kanbus-1", "hello", "--no-validate"])
    assert result_comment_beads_fail.exit_code != 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    monkeypatch.setattr(
        cli,
        "add_comment",
        lambda **_k: (_ for _ in ()).throw(IssueCommentError("comment fail")),
    )
    result_comment_regular_fail = _run(["comment", "kanbus-1", "hello", "--no-validate"])
    assert result_comment_regular_fail.exit_code != 0
    assert "comment fail" in result_comment_regular_fail.output

    result_comment_required = _run(["comment", "kanbus-1"])
    assert result_comment_required.exit_code != 0
    assert "Comment text required" in result_comment_required.output


def test_create_update_move_delete_list_and_dep_remaining_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_resolve_beads_mode", lambda _ctx, _beads: (False, False))
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]),
    )
    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: None)
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "format_issue_for_display", lambda *_a, **_k: "formatted")
    monkeypatch.setattr(cli, "format_issue_key", lambda identifier, project_context=False: identifier)
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")

    issue = build_issue("kanbus-1")
    monkeypatch.setattr(
        cli,
        "create_issue",
        lambda **_k: SimpleNamespace(issue=issue, configuration=build_project_configuration()),
    )
    result_create_regular = _run(["create", "x", "--description", "desc", "--no-validate"])
    assert result_create_regular.exit_code == 0

    monkeypatch.setattr(cli, "_resolve_beads_mode", lambda _ctx, _beads: (True, True))
    monkeypatch.setattr(cli, "create_beads_issue", lambda **_k: issue)
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    result_create_beads = _run(["create", "x", "--description", "desc", "--no-validate"])
    assert result_create_beads.exit_code == 0
    monkeypatch.setattr(cli, "_resolve_beads_mode", lambda _ctx, _beads: (False, False))

    show_config_calls = {"count": 0}

    def _show_config(_p):
        show_config_calls["count"] += 1
        if show_config_calls["count"] == 1:
            return build_project_configuration(beads_compatibility=True)
        return build_project_configuration()

    monkeypatch.setattr(cli, "load_project_configuration", _show_config)
    monkeypatch.setattr(cli, "load_beads_issue", lambda *_a, **_k: issue)
    result_show_beads = _run(["show", "kanbus-1"])
    assert result_show_beads.exit_code == 0

    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _r: tmp_path)
    monkeypatch.setattr(cli, "load_beads_issue", lambda *_a, **_k: issue)
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(
        "kanbus.project.load_project_directory",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.ProjectMarkerError("no project")),
    )
    monkeypatch.setattr(cli, "update_beads_issue", lambda *_a, **_k: None)
    result_update_beads = _run(["update", "kanbus-1", "--description", "desc"])
    assert result_update_beads.exit_code == 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("cfg fail")),
    )
    monkeypatch.setattr(cli, "update_issue", lambda **_k: issue)
    result_move_regular = _run(["move", "kanbus-1", "task"])
    assert result_move_regular.exit_code == 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    result_move_beads_guard = _run(["move", "kanbus-1", "task"])
    assert result_move_beads_guard.exit_code != 0
    assert "not supported in beads mode" in result_move_beads_guard.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(
        cli,
        "load_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(MigrationError("missing")),
    )
    monkeypatch.setattr(cli, "delete_beads_issue", lambda *_a, **_k: None)
    result_delete = _run(["delete", "kanbus-1", "--yes"])
    assert result_delete.exit_code == 0

    monkeypatch.setattr(cli, "list_issues", lambda *_a, **_k: [issue])
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    monkeypatch.setattr(cli, "format_issue_line", lambda *_a, **_k: "line")
    result_list_pm = _run(["list"])
    assert result_list_pm.exit_code == 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("list cfg fail")),
    )
    result_list_cfg = _run(["list"])
    assert result_list_cfg.exit_code != 0
    assert "list cfg fail" in result_list_cfg.output

    # Direct dep callback for successful depth parse branch.
    context = click.Context(click.Command("dep"))
    context.obj = {}
    monkeypatch.setattr(cli, "build_dependency_tree", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(cli, "render_dependency_tree", lambda *_a, **_k: "rendered")
    with context.scope(cleanup=False):
        cli.dep.callback(("tree", "kanbus-1", "--depth", "2"))

    monkeypatch.setattr(
        cli,
        "get_configuration_path",
        lambda _r: (_ for _ in ()).throw(cli.ProjectMarkerError("project not initialized")),
    )
    jira_context = click.Context(cli.jira_pull)
    jira_context.obj = {"beads_mode": False, "no_hooks": False, "no_guidance": False}
    with jira_context.scope(cleanup=False):
        with pytest.raises(click.ClickException, match="Run \\\"kanbus init\\\""):
            cli.jira_pull.callback(False)


def test_cli_main_guard_line_executes() -> None:
    previous_argv = sys.argv[:]
    try:
        sys.argv = ["kanbus", "--help"]
        with pytest.raises(SystemExit):
            runpy.run_module("kanbus.cli", run_name="__main__")
    finally:
        sys.argv = previous_argv
