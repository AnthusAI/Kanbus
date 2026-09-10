from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.content_validation import ContentValidationError
from kanbus.issue_close import IssueCloseError
from kanbus.issue_creation import IssueCreationError
from kanbus.issue_lookup import IssueLookupError
from kanbus.issue_transfer import IssueTransferError
from kanbus.issue_update import IssueUpdateError
from kanbus.migration import MigrationError

from test_helpers import build_issue, build_update_result, build_project_configuration


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
        lambda **_k: SimpleNamespace(
            issue=issue, configuration=build_project_configuration()
        ),
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

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
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
    monkeypatch.setattr(
        cli, "load_issue_from_project", lambda _r, _i: SimpleNamespace(issue=issue)
    )
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        "kanbus.console_snapshot.get_issues_for_root",
        lambda _r: (_ for _ in ()).throw(RuntimeError("ignore")),
    )
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
    monkeypatch.setattr(
        cli, "format_issue_key", lambda identifier, project_context=False: identifier
    )
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
    result_beads_ok = _run(
        ["--beads", "update", "kanbus-1", "--set-labels", "a,b", "--no-validate"]
    )
    assert result_beads_ok.exit_code == 0
    assert "Updated kanbus-1" in result_beads_ok.output

    monkeypatch.setattr(
        cli,
        "update_beads_issue",
        lambda *_a, **_k: (_ for _ in ()).throw(
            cli.BeadsWriteError("beads update fail")
        ),
    )
    result_beads_fail = _run(["--beads", "update", "kanbus-1", "--no-validate"])
    assert result_beads_fail.exit_code != 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    monkeypatch.setattr(
        cli, "load_issue_from_project", lambda _r, _i: SimpleNamespace(issue=issue)
    )
    monkeypatch.setattr(
        cli, "update_issue", lambda **_k: build_update_result("kanbus-1")
    )
    result_regular_ok = _run(["update", "kanbus-1", "--claim", "--no-validate"])
    assert result_regular_ok.exit_code == 0

    monkeypatch.setattr(
        cli,
        "update_issue",
        lambda **_k: build_update_result("kanbus-1", changed=False),
    )
    result_no_op = _run(["update", "kanbus-1", "--status", "open", "--no-validate"])
    assert result_no_op.exit_code == 0
    assert "No changes for kanbus-1" in result_no_op.output

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
    monkeypatch.setattr(
        cli, "format_issue_key", lambda identifier, project_context=False: identifier
    )
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

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=False),
    )
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        cli, "update_issue", lambda **_k: build_update_result("kanbus-1")
    )
    result_move = _run(["move", "kanbus-1", "bug"])
    assert result_move.exit_code == 0

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    assert _run(["move", "kanbus-1", "bug"]).exit_code != 0

    monkeypatch.setattr(
        cli,
        "update_issue",
        lambda **_k: (_ for _ in ()).throw(IssueUpdateError("move fail")),
    )
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=False),
    )
    assert _run(["move", "kanbus-1", "bug"]).exit_code != 0

    monkeypatch.setattr(cli, "promote_issue", lambda *_a: None)
    monkeypatch.setattr(cli, "localize_issue", lambda *_a: None)
    monkeypatch.setattr(
        cli, "load_issue_from_project", lambda _r, _i: SimpleNamespace(issue=issue)
    )
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

    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]),
    )
    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: None)
    monkeypatch.setattr(cli, "emit_signals", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
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
        lambda **_k: SimpleNamespace(
            issue=issue, comment=SimpleNamespace(id="c1", agent=None)
        ),
    )
    result_comment = _run(["comment", "kanbus-1", "hello"])
    assert result_comment.exit_code == 0

    monkeypatch.setattr(
        cli,
        "validate_code_blocks",
        lambda _t: (_ for _ in ()).throw(ContentValidationError("bad comment")),
    )
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
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
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
    monkeypatch.setattr(
        "kanbus.policy_loader.load_policies", lambda _p: [("p.policy", object())]
    )
    monkeypatch.setattr(
        "kanbus.policy_evaluator.evaluate_policies", lambda *_a, **_k: []
    )
    monkeypatch.setattr(
        "kanbus.workflows.validate_status_value", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "kanbus.workflows.validate_status_transition", lambda *_a, **_k: None
    )

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
    monkeypatch.setattr(
        cli, "format_issue_key", lambda identifier, project_context=False: identifier
    )
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


def test_comment_update_cli_error_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)

    missing_identifier = _run(["comment"])
    assert missing_identifier.exit_code != 0
    assert "issue identifier is required" in missing_identifier.output

    missing_comment_id = _run(["comment", "update", "kanbus-1"])
    assert missing_comment_id.exit_code != 0
    assert (
        "comment update requires an issue id and comment id"
        in missing_comment_id.output
    )

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("pm")),
    )
    missing_text = _run(["comment", "update", "kanbus-1", "c1"])
    assert missing_text.exit_code != 0
    assert "comment text is required" in missing_text.output

    beads_update = _run(["--beads", "comment", "update", "kanbus-1", "c1", "hello"])
    assert beads_update.exit_code != 0
    assert "beads mode does not support comment update" in beads_update.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
    compatibility_update = _run(["comment", "update", "kanbus-1", "c1", "hello"])
    assert compatibility_update.exit_code != 0
    assert "beads mode does not support comment update" in compatibility_update.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=False),
    )
    monkeypatch.setattr(
        cli,
        "apply_text_quality_signals",
        lambda text: SimpleNamespace(text=text, warnings=[], suggestions=[]),
    )
    monkeypatch.setattr(
        cli,
        "validate_code_blocks",
        lambda _t: (_ for _ in ()).throw(ContentValidationError("bad comment update")),
    )
    invalid_update = _run(["comment", "update", "kanbus-1", "c1", "```json\n{\n```"])
    assert invalid_update.exit_code != 0
    assert "bad comment update" in invalid_update.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=False),
    )
    monkeypatch.setattr(cli, "validate_code_blocks", lambda _t: None)
    monkeypatch.setattr(cli, "update_comment", lambda *_a, **_k: None)
    signals: list[object] = []
    monkeypatch.setattr(cli, "emit_signals", lambda *a, **k: signals.append((a, k)))
    success_update = _run(["comment", "update", "kanbus-1", "c1", "hello"])
    assert success_update.exit_code == 0
    assert signals

    monkeypatch.setattr(
        cli,
        "update_comment",
        lambda *_a, **_k: (_ for _ in ()).throw(cli.IssueCommentError("update failed")),
    )
    failed_update = _run(["comment", "update", "kanbus-1", "c1", "hello"])
    assert failed_update.exit_code != 0
    assert "update failed" in failed_update.output


def test_cost_summarize_and_now_generate_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_enforce_kanbus_version", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_maybe_prompt_project_repair", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "kanbus.project.get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        "kanbus.config_loader.load_project_configuration",
        lambda _p: build_project_configuration(),
    )

    missing_logs = _run(["cost"])
    assert missing_logs.exit_code == 0
    assert "No LLM usage logs found" in missing_logs.output

    log_path = tmp_path / "project" / "events" / "llm_usage.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                "",
                '{"timestamp":"2020-01-01T00:00:00+00:00","tokens":5,"cost":0.1}',
                '{"timestamp":"2099-01-01T00:00:00+00:00","tokens":7,"cost":0.2}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with_days = _run(["cost", "--days", "7"])
    assert with_days.exit_code == 0
    assert "Total Tokens: 7" in with_days.output
    assert "0.2000" in with_days.output

    monkeypatch.setattr(
        "kanbus.summarize.compaction_summarize",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("summarize failed")),
    )
    summarize_fail = _run(["summarize", "kanbus-1"])
    assert summarize_fail.exit_code != 0
    assert "summarize failed" in summarize_fail.output

    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(IssueLookupError("missing now")),
    )
    generate_missing = _run(["now-generate-internal", "kanbus-1"])
    assert generate_missing.exit_code != 0
    assert "missing now" in generate_missing.output

    monkeypatch.setattr(
        cli,
        "load_issue_from_project",
        lambda *_a: SimpleNamespace(issue=build_issue("kanbus-1")),
    )
    monkeypatch.setattr(cli, "build_leaf_right_now_context", lambda _issue: "ctx")
    monkeypatch.setattr(
        cli,
        "generate_right_now_summary",
        lambda *_a: (_ for _ in ()).throw(cli.RightNowError("gen fail")),
    )
    generate_fail = _run(["now-generate-internal", "kanbus-1"])
    assert generate_fail.exit_code != 0
    assert "gen fail" in generate_fail.output

    monkeypatch.setattr(cli, "generate_right_now_summary", lambda *_a: "now text")
    generate_ok = _run(["now-generate-internal", "kanbus-1"])
    assert generate_ok.exit_code == 0
    assert "now text" in generate_ok.output


def test_wiki_and_dependabot_cli_error_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_enforce_kanbus_version", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_maybe_prompt_project_repair", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "check_wiki_page_links", lambda *_a: [])
    monkeypatch.setattr(cli, "render_wiki_page", lambda *_a, **_k: "html")
    monkeypatch.setattr(
        cli,
        "resolve_wiki_page_path",
        lambda *_a: (_ for _ in ()).throw(cli.WikiError("resolve fail")),
    )
    render_json = _run(["wiki", "render", "index.md", "--json"])
    assert render_json.exit_code != 0
    assert "resolve fail" in render_json.output

    monkeypatch.setattr(
        cli,
        "init_wiki",
        lambda *_a: (_ for _ in ()).throw(cli.WikiError("init fail")),
    )
    init_fail = _run(["wiki", "init"])
    assert init_fail.exit_code != 0
    assert "init fail" in init_fail.output

    monkeypatch.setattr(
        cli,
        "get_configuration_path",
        lambda _p: (_ for _ in ()).throw(cli.ProjectMarkerError("no project")),
    )
    monkeypatch.setattr(
        cli,
        "_format_project_marker_error",
        lambda error: str(error),
    )
    dependabot_marker = _run(["github", "dependabot", "pull"])
    assert dependabot_marker.exit_code != 0
    assert "no project" in dependabot_marker.output

    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(cli.ConfigurationError("cfg")),
    )
    dependabot_config = _run(["github", "dependabot", "pull"])
    assert dependabot_config.exit_code != 0
    assert "bad" in dependabot_config.output or "cfg" in dependabot_config.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(),
    )
    monkeypatch.setattr(
        "kanbus.github_security_sync.pull_dependabot_from_github",
        lambda *_a, **_k: (_ for _ in ()).throw(
            __import__(
                "kanbus.github_security_sync", fromlist=["GithubSecuritySyncError"]
            ).GithubSecuritySyncError("sync fail")
        ),
    )
    dependabot_sync = _run(
        [
            "github",
            "dependabot",
            "pull",
            "--dry-run",
            "--repo",
            "org/repo",
            "--min-severity",
            "high",
            "--state",
            "open",
            "--parent-epic",
            "epic-1",
        ]
    )
    assert dependabot_sync.exit_code != 0
    assert "sync fail" in dependabot_sync.output

    monkeypatch.setattr(
        "kanbus.github_security_sync.pull_dependabot_from_github_beads",
        lambda *_a, **_k: SimpleNamespace(pulled=1, updated=2, skipped=3),
    )
    beads_pull = _run(["--beads", "gh", "dependabot", "pull"])
    assert beads_pull.exit_code == 0
    assert "pulled 1 new" in beads_pull.output
