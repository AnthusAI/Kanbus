"""Tests for the per-command project context and configuration load counts."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from kanbus import cli
from kanbus.config_loader import (
    ConfigurationError,
    configuration_load_count,
    reset_configuration_load_count,
)
from kanbus.project_context import ProjectContext, require_project_context

INVALID_YAML_MESSAGE = "configuration is not valid YAML"


def _initialize_repository(root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("KANBUS_REALTIME_BROKER", "off")
    monkeypatch.chdir(root)
    (root / ".kanbus.yml").write_text("project_key: kanbus\n", encoding="utf-8")
    (root / "project" / "issues").mkdir(parents=True)
    (root / "project" / "events").mkdir(parents=True)
    result = CliRunner().invoke(
        cli.cli, ["create", "Seed issue", "--no-agent-provenance"]
    )
    assert result.exit_code == 0, result.output
    for line in result.output.splitlines():
        if line.startswith("ID: "):
            return line[len("ID: ") :].strip()
    raise AssertionError(f"seed issue identifier missing from: {result.output}")


def _loads_for(arguments: list[str]) -> int:
    reset_configuration_load_count()
    result = CliRunner().invoke(cli.cli, arguments)
    assert result.exit_code == 0, result.output
    return configuration_load_count()


def test_list_loads_configuration_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize_repository(tmp_path, monkeypatch)
    assert _loads_for(["list"]) == 1


def test_show_loads_configuration_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = _initialize_repository(tmp_path, monkeypatch)
    assert _loads_for(["show", identifier]) == 1


def test_create_loads_configuration_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize_repository(tmp_path, monkeypatch)
    assert _loads_for(["create", "Another issue", "--no-agent-provenance"]) == 1


def test_update_loads_configuration_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = _initialize_repository(tmp_path, monkeypatch)
    assert _loads_for(["update", identifier, "--status", "in_progress"]) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        ["list"],
        ["show", "kanbus-aaa"],
        ["create", "Broken", "--no-agent-provenance"],
        ["update", "kanbus-aaa", "--status", "in_progress"],
    ],
)
def test_malformed_configuration_fails_every_issue_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    _initialize_repository(tmp_path, monkeypatch)
    (tmp_path / ".kanbus.yml").write_text("project_key: [unclosed\n", encoding="utf-8")
    result = CliRunner().invoke(cli.cli, arguments)
    assert result.exit_code == 1
    assert INVALID_YAML_MESSAGE in result.output


def test_project_context_discover_returns_none_without_configuration(
    tmp_path: Path,
) -> None:
    assert ProjectContext.discover(tmp_path) is None
    with pytest.raises(Exception, match="project not initialized"):
        require_project_context(tmp_path)


def test_project_context_discover_propagates_malformed_configuration(
    tmp_path: Path,
) -> None:
    (tmp_path / ".kanbus.yml").write_text("project_key: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match=INVALID_YAML_MESSAGE):
        ProjectContext.discover(tmp_path)


def test_project_context_resolves_primary_project_directory(tmp_path: Path) -> None:
    (tmp_path / ".kanbus.yml").write_text("project_key: kanbus\n", encoding="utf-8")
    (tmp_path / "project" / "issues").mkdir(parents=True)
    context = ProjectContext.discover(tmp_path)
    assert context is not None
    assert context.repository_root == tmp_path.resolve()
    assert context.primary_project_directory() == (tmp_path / "project").resolve()
    assert context.overlay == context.configuration.overlay
