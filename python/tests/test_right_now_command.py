from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kanbus.models import RightNowConfiguration
from kanbus.project import ProjectMarkerError
from kanbus.right_now_command import (
    RightNowCommandOptions,
    _format_updated_at,
    _load_configuration,
    _resolve_tree_expanded,
)

from test_helpers import build_project_configuration


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
