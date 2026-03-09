from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.content_validation import ContentValidationError
from kanbus.issue_close import IssueCloseError
from kanbus.issue_comment import IssueCommentError
from kanbus.issue_creation import IssueCreationError
from kanbus.issue_lookup import IssueLookupError
from kanbus.issue_transfer import IssueTransferError
from kanbus.issue_update import IssueUpdateError
from kanbus.migration import MigrationError

from test_helpers import build_issue, build_project_configuration


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_create_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "format_issue_for_display", lambda *_a, **_k: "formatted")

    assert _run(["create"]).exit_code != 0
    assert _run(["create", "x", "--focus"]).exit_code != 0

    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]),
    )
    monkeypatch.setattr(
        cli,
        "validate_code_blocks",
        lambda _text: (_ for _ in ()).throw(ContentValidationError("bad block")),
    )
    result_validate_fail = _run(["create", "x", "--description", "```json\n{\n```"])
    assert result_validate_fail.exit_code != 0
    assert "bad block" in result_validate_fail.output

    monkeypatch.setattr(cli, "validate_code_blocks", lambda _text: None)

    result_beads_local = _run(["--beads", "create", "x", "--local"])
    assert result_beads_local.exit_code != 0
    assert "does not support local issues" in result_beads_local.output

    issue = build_issue("kanbus-1")
    monkeypatch.setattr(cli, "create_beads_issue", lambda **_k: issue)
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: None)
    result_beads_ok = _run(["--beads", "create", "x"])
    assert result_beads_ok.exit_code == 0
    assert "formatted" in result_beads_ok.output

    monkeypatch.setattr(
        cli,
        "create_beads_issue",
        lambda **_k: (_ for _ in ()).throw(cli.BeadsWriteError("beads create fail")),
    )
    result_beads_fail = _run(["--beads", "create", "x"])
    assert result_beads_fail.exit_code != 0
    assert "beads create fail" in result_beads_fail.output

    monkeypatch.setattr(
        cli,
        "create_issue",
        lambda **_k: SimpleNamespace(issue=issue, configuration=build_project_configuration()),
    )
    result_regular_ok = _run(["create", "x", "--no-validate"])
    assert result_regular_ok.exit_code == 0

    monkeypatch.setattr(
        cli,
        "create_issue",
        lambda **_k: (_ for _ in ()).throw(IssueCreationError("create fail")),
    )
    result_regular_fail = _run(["create", "x", "--no-validate"])
    assert result_regular_fail.exit_code != 0
    assert "create fail" in result_regular_fail.output


def test_show_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "format_issue_for_display", lambda *_a, **_k: "shown")

    issue = build_issue("kanbus-1")

    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: build_project_configuration(beads_compatibility=True))
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _r: tmp_path)
    monkeypatch.setattr(cli, "load_beads_issue", lambda _r, _i: issue)

    result_json = _run(["show", "kanbus-1", "--json"])
    assert result_json.exit_code == 0
    assert '"id": "kanbus-1"' in result_json.output

    result_text = _run(["show", "kanbus-1"])
    assert result_text.exit_code == 0
    assert "shown" in result_text.output

    monkeypatch.setattr(
        cli,
        "load_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(MigrationError("not found")),
    )
    result_beads_fail = _run(["show", "kanbus-1"])
    assert result_beads_fail.exit_code != 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=False),
    )
    monkeypatch.setattr(cli, "load_issue_from_project", lambda _r, _i: SimpleNamespace(issue=issue))
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr("kanbus.console_snapshot.get_issues_for_root", lambda _r: (_ for _ in ()).throw(RuntimeError("ignore")))
    result_regular_ok = _run(["show", "kanbus-1"])
    assert result_regular_ok.exit_code == 0

    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueLookupError("lookup fail")),
    )
    result_regular_fail = _run(["show", "kanbus-1"])
    assert result_regular_fail.exit_code != 0


def test_update_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "format_issue_key", lambda identifier, project_context=False: identifier)
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]),
    )

    monkeypatch.setattr(
        cli,
        "validate_code_blocks",
        lambda _text: (_ for _ in ()).throw(ContentValidationError("bad update")),
    )
    result_validate_fail = _run(["update", "kanbus-1", "--description", "x"])
    assert result_validate_fail.exit_code != 0

    monkeypatch.setattr(cli, "validate_code_blocks", lambda _text: None)

    result_beads_parent_fail = _run(["--beads", "update", "kanbus-1", "--parent", "p1"])
    assert result_beads_parent_fail.exit_code != 0

    issue = build_issue("kanbus-1")
    monkeypatch.setattr(cli, "load_beads_issue", lambda _r, _i: issue)
    monkeypatch.setattr(cli, "update_beads_issue", lambda *_a, **_k: None)
    result_beads_ok = _run(["--beads", "update", "kanbus-1", "--set-labels", "a,b", "--no-validate"])
    assert result_beads_ok.exit_code == 0
    assert "Updated kanbus-1" in result_beads_ok.output

    monkeypatch.setattr(
        cli,
        "update_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.BeadsWriteError("beads update fail")),
    )
    result_beads_fail = _run(["--beads", "update", "kanbus-1", "--no-validate"])
    assert result_beads_fail.exit_code != 0

    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")))
    monkeypatch.setattr(cli, "load_issue_from_project", lambda _r, _i: SimpleNamespace(issue=issue))
    monkeypatch.setattr(cli, "update_issue", lambda **_k: issue)
    result_regular_ok = _run(["update", "kanbus-1", "--claim", "--no-validate"])
    assert result_regular_ok.exit_code == 0

    monkeypatch.setattr(
        cli,
        "update_issue",
        lambda **_k: (_ for _ in ()).throw(IssueUpdateError("update fail")),
    )
    result_regular_fail = _run(["update", "kanbus-1", "--no-validate"])
    assert result_regular_fail.exit_code != 0


def test_close_move_promote_localize_comment_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "format_issue_key", lambda identifier, project_context=False: identifier)
    issue = build_issue("kanbus-1")

    monkeypatch.setattr(cli, "close_issue", lambda _r, _i: issue)
    result_close = _run(["close", "kanbus-1"])
    assert result_close.exit_code == 0
    assert "Closed kanbus-1" in result_close.output

    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _r: tmp_path)
    close_lookup_calls = {"count": 0}

    def _load_beads_issue_for_close(*_a, **_k):
        close_lookup_calls["count"] += 1
        if close_lookup_calls["count"] == 1:
            raise MigrationError("missing before")
        return issue

    monkeypatch.setattr(cli, "load_beads_issue", _load_beads_issue_for_close)
    monkeypatch.setattr(cli, "update_beads_issue", lambda *_a, **_k: None)
    result_close_beads = _run(["--beads", "close", "kanbus-1"])
    assert result_close_beads.exit_code == 0

    monkeypatch.setattr(
        cli,
        "update_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(MigrationError("close beads fail")),
    )
    result_close_beads_fail = _run(["--beads", "close", "kanbus-1"])
    assert result_close_beads_fail.exit_code != 0
    assert "close beads fail" in result_close_beads_fail.output

    monkeypatch.setattr(
        cli,
        "close_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(IssueCloseError("close fail")),
    )
    assert _run(["close", "kanbus-1"]).exit_code != 0

    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: build_project_configuration(beads_compatibility=False))
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(cli, "update_issue", lambda **_k: issue)
    result_move = _run(["move", "kanbus-1", "bug"])
    assert result_move.exit_code == 0

    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: build_project_configuration(beads_compatibility=True))
    assert _run(["move", "kanbus-1", "bug"]).exit_code != 0

    monkeypatch.setattr(
        cli,
        "update_issue",
        lambda **_k: (_ for _ in ()).throw(IssueUpdateError("move fail")),
    )
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: build_project_configuration(beads_compatibility=False))
    assert _run(["move", "kanbus-1", "bug"]).exit_code != 0

    monkeypatch.setattr(cli, "promote_issue", lambda *_a: None)
    monkeypatch.setattr(cli, "localize_issue", lambda *_a: None)
    monkeypatch.setattr(cli, "load_issue_from_project", lambda _r, _i: SimpleNamespace(issue=issue))
    assert _run(["promote", "kanbus-1"]).exit_code == 0
    assert _run(["localize", "kanbus-1"]).exit_code == 0

    calls = {"count": 0}

    def _lookup_once_then_fail(_r, _i):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(issue=issue)
        raise IssueLookupError("missing after")

    monkeypatch.setattr(cli, "load_issue_from_project", _lookup_once_then_fail)
    assert _run(["promote", "kanbus-1"]).exit_code == 0

    calls["count"] = 0
    monkeypatch.setattr(cli, "load_issue_from_project", _lookup_once_then_fail)
    assert _run(["localize", "kanbus-1"]).exit_code == 0

    monkeypatch.setattr(
        cli,
        "promote_issue",
        lambda *_a: (_ for _ in ()).throw(IssueTransferError("promote fail")),
    )
    assert _run(["promote", "kanbus-1"]).exit_code != 0

    monkeypatch.setattr(
        cli,
        "localize_issue",
        lambda *_a: (_ for _ in ()).throw(IssueTransferError("localize fail")),
    )
    assert _run(["localize", "kanbus-1"]).exit_code != 0

    monkeypatch.setattr(cli, "apply_text_quality_signals", lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]))
    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: None)
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr("kanbus.beads_write.add_beads_comment", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "load_beads_issue", lambda *_a, **_k: issue)
    body_file = tmp_path / "comment.txt"
    body_file.write_text("from file", encoding="utf-8")
    result_comment_body_file = _run(
        ["comment", "kanbus-1", "--body-file", str(body_file), "--no-validate"]
    )
    assert result_comment_body_file.exit_code == 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    monkeypatch.setattr(
        cli,
        "add_comment",
        lambda **_k: SimpleNamespace(issue=issue, comment=SimpleNamespace(id="c1")),
    )
    result_comment = _run(["comment", "kanbus-1", "hello"])
    assert result_comment.exit_code == 0

    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: (_ for _ in ()).throw(ContentValidationError("bad comment")))
    assert _run(["comment", "kanbus-1", "hello"]).exit_code != 0


def test_update_beads_policy_signal_and_delete_beads_compat_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _r: tmp_path)
    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text.strip(), warnings=[], suggestions=[]),
    )
    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: None)
    monkeypatch.setattr(
        "kanbus.project.load_project_directory",
        lambda _root: tmp_path / "project",
    )
    (tmp_path / "project" / "policies").mkdir(parents=True)
    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _p: [("p.policy", object())])
    monkeypatch.setattr("kanbus.policy_evaluator.evaluate_policies", lambda *_a, **_k: [])
    monkeypatch.setattr("kanbus.workflows.validate_status_value", lambda *_a, **_k: None)
    monkeypatch.setattr("kanbus.workflows.validate_status_transition", lambda *_a, **_k: None)

    before_issue = build_issue("kanbus-1", labels=["keep", "drop"])
    load_calls = {"count": 0}

    def _load_beads_issue(*_a, **_k):
        load_calls["count"] += 1
        if load_calls["count"] == 1:
            return before_issue
        return build_issue(
            "kanbus-1",
            status="done",
            priority=1,
            labels=["a", "c"],
            custom=before_issue.custom,
        )

    monkeypatch.setattr(cli, "load_beads_issue", _load_beads_issue)
    monkeypatch.setattr(cli, "load_beads_issues", lambda _r: [before_issue])
    monkeypatch.setattr(cli, "update_beads_issue", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "format_issue_key", lambda identifier, project_context=False: identifier)
    emitted: list[str] = []
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: emitted.append("emit"))

    result_update = _run(
        [
            "update",
            "kanbus-1",
            "--title",
            "Updated",
            "--description",
            "  desc  ",
            "--status",
            "done",
            "--priority",
            "1",
            "--assignee",
            "dev",
            "--set-labels",
            "a,b",
            "--add-label",
            "c",
            "--remove-label",
            "b",
        ]
    )
    assert result_update.exit_code == 0
    assert "Updated kanbus-1" in result_update.output
    assert emitted

    monkeypatch.setattr(
        cli,
        "format_issue_key",
        lambda identifier, project_context=False: identifier,
    )
    monkeypatch.setattr(
        cli,
        "load_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(MigrationError("missing")),
    )
    monkeypatch.setattr(cli, "delete_beads_issue", lambda *_a, **_k: None)
    result_delete = _run(["delete", "kanbus-1", "--yes"])
    assert result_delete.exit_code == 0
    assert "Deleted kanbus-1" in result_delete.output

    monkeypatch.setattr(
        "kanbus.beads_write.add_beads_comment",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(cli, "load_beads_issue", lambda *_a, **_k: before_issue)
    result_comment = _run(["comment", "kanbus-1", "hello", "--no-validate"])
    assert result_comment.exit_code == 0
