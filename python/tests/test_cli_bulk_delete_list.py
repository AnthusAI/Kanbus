from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.config_loader import ConfigurationError
from kanbus.issue_delete import IssueDeleteError
from kanbus.issue_listing import IssueListingError
from kanbus.issue_lookup import IssueLookupError
from kanbus.issue_update import IssueUpdateError
from kanbus.queries import QueryError

from test_helpers import build_issue, build_project_configuration


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_bulk_update_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)

    result_beads = _run(
        ["--beads", "bulk", "update", "--id", "kanbus-1", "--set-status", "done"]
    )
    assert result_beads.exit_code != 0
    assert "not supported in beads mode" in result_beads.output

    result_missing_selector = _run(["bulk", "update", "--set-status", "done"])
    assert result_missing_selector.exit_code != 0
    assert "requires at least one selector" in result_missing_selector.output

    result_missing_setter = _run(["bulk", "update", "--id", "kanbus-1"])
    assert result_missing_setter.exit_code != 0
    assert "requires at least one setter" in result_missing_setter.output

    update_calls: list[tuple[str, bool]] = []

    def _update_issue(**kwargs):
        identifier = kwargs["identifier"]
        update_calls.append((identifier, kwargs["validate"]))
        return build_issue(identifier)

    monkeypatch.setattr(cli, "update_issue", _update_issue)
    monkeypatch.setattr(
        cli,
        "list_issues",
        lambda *_a, **_k: [build_issue("kanbus-1"), build_issue("kanbus-2")],
    )

    result_success = _run(
        [
            "bulk",
            "update",
            "--id",
            "kanbus-1",
            "--where-status",
            "open",
            "--set-status",
            "done",
            "--set-assignee",
            "ryan",
            "--no-validate",
        ]
    )
    assert result_success.exit_code == 0
    assert "Updated 2 issue(s)" in result_success.output
    assert update_calls == [("kanbus-1", False), ("kanbus-2", False)]

    monkeypatch.setattr(
        cli,
        "update_issue",
        lambda **_k: (_ for _ in ()).throw(IssueUpdateError("update fail")),
    )
    result_update_fail = _run(
        ["bulk", "update", "--id", "kanbus-1", "--set-status", "done"]
    )
    assert result_update_fail.exit_code != 0
    assert "update fail" in result_update_fail.output

    monkeypatch.setattr(cli, "update_issue", _update_issue)
    monkeypatch.setattr(
        cli,
        "list_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueListingError("list fail")),
    )
    result_list_fail = _run(
        ["bulk", "update", "--where-status", "open", "--set-status", "done"]
    )
    assert result_list_fail.exit_code != 0
    assert "list fail" in result_list_fail.output

    call_order = {"count": 0}

    def _update_issue_second_fails(**kwargs):
        call_order["count"] += 1
        if call_order["count"] == 2:
            raise IssueUpdateError("second update fail")
        return build_issue(kwargs["identifier"])

    monkeypatch.setattr(cli, "update_issue", _update_issue_second_fails)
    monkeypatch.setattr(cli, "list_issues", lambda *_a, **_k: [build_issue("kanbus-2")])
    result_second_update_fail = _run(
        [
            "bulk",
            "update",
            "--id",
            "kanbus-1",
            "--where-status",
            "open",
            "--set-status",
            "done",
        ]
    )
    assert result_second_update_fail.exit_code != 0
    assert "second update fail" in result_second_update_fail.output


def test_delete_paths_regular_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    monkeypatch.setattr(
        cli,
        "format_issue_key",
        lambda identifier, project_context=False: identifier,
    )

    monkeypatch.setattr(cli, "_delete_terminal_is_interactive", lambda: False)
    result_non_interactive = _run(["delete", "kanbus-1"])
    assert result_non_interactive.exit_code != 0
    assert "requires confirmation" in result_non_interactive.output

    issue = build_issue("kanbus-1")
    monkeypatch.setattr(cli, "_delete_terminal_is_interactive", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: False)
    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a, **_k: SimpleNamespace(issue=issue, project_dir=tmp_path / "proj"),
    )
    result_cancel = _run(["delete", "kanbus-1"])
    assert result_cancel.exit_code == 0
    assert "Delete cancelled." in result_cancel.output

    confirmations = iter([True, False])
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: next(confirmations))
    monkeypatch.setattr(
        cli,
        "get_descendant_identifiers",
        lambda *_a, **_k: ["d1", "d2", "d3", "d4", "d5", "d6"],
    )
    deleted: list[str] = []
    monkeypatch.setattr(
        cli, "delete_issue", lambda _root, issue_id: deleted.append(issue_id)
    )

    result_recursive = _run(["delete", "kanbus-1", "--recursive"])
    assert result_recursive.exit_code == 0
    assert deleted == ["kanbus-1"]

    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueLookupError("lookup fail")),
    )
    result_lookup_fail = _run(["delete", "kanbus-1", "--yes"])
    assert result_lookup_fail.exit_code != 0
    assert "lookup fail" in result_lookup_fail.output

    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a, **_k: SimpleNamespace(issue=issue, project_dir=tmp_path / "proj"),
    )
    monkeypatch.setattr(
        cli,
        "delete_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueDeleteError("delete fail")),
    )
    result_delete_fail = _run(["delete", "kanbus-1", "--yes"])
    assert result_delete_fail.exit_code != 0
    assert "delete fail" in result_delete_fail.output


def test_delete_paths_beads_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _cwd: tmp_path)
    monkeypatch.setattr(
        cli, "format_issue_key", lambda identifier, project_context=False: identifier
    )
    monkeypatch.setattr(
        cli, "load_beads_issue", lambda *_a, **_k: build_issue("kanbus-1")
    )

    monkeypatch.setattr(cli, "_delete_terminal_is_interactive", lambda: False)
    result_non_interactive = _run(["--beads", "delete", "kanbus-1"])
    assert result_non_interactive.exit_code != 0
    assert "requires confirmation" in result_non_interactive.output

    monkeypatch.setattr(cli, "_delete_terminal_is_interactive", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: False)
    result_cancel = _run(["--beads", "delete", "kanbus-1"])
    assert result_cancel.exit_code == 0
    assert "Delete cancelled." in result_cancel.output

    confirmations = iter([True, False])
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: next(confirmations))
    monkeypatch.setattr(
        cli,
        "get_beads_descendant_identifiers",
        lambda *_a, **_k: ["a", "b", "c", "d", "e", "f"],
    )
    recursive_flags: list[bool] = []
    monkeypatch.setattr(
        cli,
        "delete_beads_issue",
        lambda _root, _identifier, recursive: recursive_flags.append(recursive),
    )
    result_recursive = _run(["--beads", "delete", "kanbus-1", "--recursive"])
    assert result_recursive.exit_code == 0
    assert recursive_flags == [False]

    monkeypatch.setattr(
        cli,
        "delete_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.BeadsDeleteError("beads fail")),
    )
    result_fail = _run(["--beads", "delete", "kanbus-1", "--yes"])
    assert result_fail.exit_code != 0
    assert "beads fail" in result_fail.output


def test_list_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)

    regular_issue_a = build_issue("kanbus-1")
    regular_issue_b = build_issue("kanbus-2", custom={"project_path": "proj-b"})

    widths_calls: list[bool] = []
    monkeypatch.setattr(
        cli,
        "compute_widths",
        lambda issues, project_context: widths_calls.append(project_context)
        or {"id": 8},
    )
    monkeypatch.setattr(
        cli,
        "format_issue_line",
        lambda issue, porcelain, widths, project_context, configuration: (
            f"{issue.identifier}:{porcelain}:{project_context}:{configuration is not None}"
        ),
    )
    monkeypatch.setattr(
        cli,
        "list_issues",
        lambda *_a, **_k: [regular_issue_a, regular_issue_b],
    )
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(),
    )
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )

    result_regular = _run(["list", "--limit", "1", "--full-ids"])
    assert result_regular.exit_code == 0
    assert "kanbus-1:False:False:True" in result_regular.output
    assert widths_calls == [False]

    widths_calls.clear()
    monkeypatch.setattr(cli, "list_issues", lambda *_a, **_k: [regular_issue_a])
    result_project_context = _run(["list", "--limit", "1"])
    assert result_project_context.exit_code == 0
    assert "kanbus-1:False:True:True" in result_project_context.output
    assert widths_calls == [True]

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("config fail")),
    )
    result_config_fail = _run(["list"])
    assert result_config_fail.exit_code != 0
    assert "config fail" in result_config_fail.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(),
    )
    monkeypatch.setattr(
        cli,
        "list_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueListingError("list fail")),
    )
    result_list_fail = _run(["list"])
    assert result_list_fail.exit_code != 0
    assert "list fail" in result_list_fail.output

    monkeypatch.setattr(
        cli,
        "list_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(QueryError("query fail")),
    )
    result_query_fail = _run(["list"])
    assert result_query_fail.exit_code != 0
    assert "query fail" in result_query_fail.output

    beads_issue_a = build_issue("kanbus-3", priority=3)
    beads_issue_b = build_issue("kanbus-2", priority=1)
    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _cwd: tmp_path)
    monkeypatch.setattr(
        cli, "list_issues", lambda *_a, **_k: [beads_issue_a, beads_issue_b]
    )
    monkeypatch.setattr(
        cli,
        "compute_widths",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("unexpected widths")),
    )
    monkeypatch.setattr(
        cli,
        "format_issue_line",
        lambda issue, porcelain, widths, project_context, configuration: f"{issue.identifier}:{porcelain}:{project_context}:{configuration}",
    )

    result_beads = _run(["--beads", "list", "--porcelain", "--limit", "0"])
    assert result_beads.exit_code == 0
    lines = [line for line in result_beads.output.splitlines() if line.strip()]
    assert lines == [
        "kanbus-2:True:False:None",
        "kanbus-3:True:False:None",
    ]
