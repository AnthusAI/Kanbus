from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kanbus.issue_lookup import IssueLookupError
from kanbus.models import RightNowConfiguration
from kanbus.project import ProjectMarkerError
from kanbus.right_now_command import (
    CANNOT_COMBINE_ALL_WITH_ISSUE_IDENTIFIERS,
    CANNOT_COMBINE_ALL_WITH_LIMIT,
    DEFAULT_RIGHT_NOW_LIMIT,
    DEFAULT_RIGHT_NOW_STATUS,
    EMPTY_STATUS_FILTER,
    NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS,
    RightNowCommandError,
    RightNowCommandOptions,
    _effective_right_now_limit,
    _format_updated_at,
    _load_configuration,
    _resolve_right_now_statuses,
    _resolve_tree_expanded,
    _validate_right_now_options,
    run_right_now_command,
)

from test_helpers import build_issue, build_project_configuration


def test_load_configuration_returns_none_on_missing_project(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "kanbus.right_now_command.get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing")),
    )
    assert _load_configuration(tmp_path) is None
    monkeypatch.setattr(
        "kanbus.right_now_command.get_configuration_path",
        lambda _root: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert _load_configuration(tmp_path) is None


def test_resolve_tree_expanded_uses_options_and_config() -> None:
    options = RightNowCommandOptions(expanded=True)
    assert _resolve_tree_expanded(options, None) is True
    options = RightNowCommandOptions(collapsed=True)
    assert _resolve_tree_expanded(options, None) is False
    assert _resolve_tree_expanded(RightNowCommandOptions(), None) is False
    configuration = build_project_configuration()
    configuration.right_now = RightNowConfiguration(default_tree_expanded=True)
    assert _resolve_tree_expanded(RightNowCommandOptions(), configuration) is True


def test_format_updated_at_adds_utc_when_naive() -> None:
    naive = datetime(2026, 9, 2, 12, 0, 0)
    rendered = _format_updated_at(naive)
    assert rendered.endswith("Z")
    aware = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    assert _format_updated_at(aware).endswith("Z")


def test_default_right_now_options_are_tree_and_recursive() -> None:
    options = RightNowCommandOptions()
    assert options.tree is True
    assert options.recursive is True
    _validate_right_now_options(options)


def test_validate_right_now_options_rejects_conflicts() -> None:
    with pytest.raises(RightNowCommandError, match=CANNOT_COMBINE_ALL_WITH_LIMIT):
        _validate_right_now_options(RightNowCommandOptions(show_all=True, limit=2))
    with pytest.raises(
        RightNowCommandError, match=CANNOT_COMBINE_ALL_WITH_ISSUE_IDENTIFIERS
    ):
        _validate_right_now_options(
            RightNowCommandOptions(show_all=True, issue_ids=("kanbus-a",))
        )
    with pytest.raises(
        RightNowCommandError, match=NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS
    ):
        _validate_right_now_options(RightNowCommandOptions(recursive=False))
    _validate_right_now_options(RightNowCommandOptions())


def test_resolve_right_now_statuses_defaults_to_in_progress_for_board() -> None:
    assert _resolve_right_now_statuses(None, False) == {DEFAULT_RIGHT_NOW_STATUS}
    assert _resolve_right_now_statuses(None, True) is None
    assert _resolve_right_now_statuses("all", False) is None
    assert _resolve_right_now_statuses("in_progress,open", False) == {
        "in_progress",
        "open",
    }
    with pytest.raises(RightNowCommandError, match=EMPTY_STATUS_FILTER):
        _resolve_right_now_statuses(" , ", False)


def test_effective_right_now_limit_uses_selection_policy() -> None:
    assert (
        _effective_right_now_limit(RightNowCommandOptions()) == DEFAULT_RIGHT_NOW_LIMIT
    )
    assert _effective_right_now_limit(RightNowCommandOptions(show_all=True)) == 0
    assert (
        _effective_right_now_limit(RightNowCommandOptions(issue_ids=("kanbus-a",))) == 0
    )
    assert (
        _effective_right_now_limit(
            RightNowCommandOptions(issue_ids=("kanbus-a",), limit=1)
        )
        == 1
    )
    assert _effective_right_now_limit(RightNowCommandOptions(limit=5)) == 5


def test_run_right_now_command_keeps_issue_when_reload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-now")
    issue.status = "in_progress"
    monkeypatch.setattr("kanbus.right_now_command.list_issues", lambda _root: [issue])
    monkeypatch.setattr(
        "kanbus.right_now_command.ensure_right_now_summaries", lambda *_a: None
    )
    monkeypatch.setattr(
        "kanbus.right_now_command.load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(IssueLookupError("missing after backfill")),
    )
    monkeypatch.setattr(
        "kanbus.right_now_command._load_configuration", lambda _root: None
    )
    output = run_right_now_command(
        tmp_path, RightNowCommandOptions(tree=False, raw=False)
    )
    assert "kanbus-now" in output
