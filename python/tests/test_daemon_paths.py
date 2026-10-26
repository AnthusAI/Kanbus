from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import daemon_paths
from kanbus.config_loader import (
    ConfigurationError,
    configuration_load_count,
    reset_configuration_load_count,
)
from kanbus.project_context import ProjectContext


def test_get_daemon_socket_path_resolves_once_per_root(tmp_path: Path) -> None:
    (tmp_path / ".kanbus.yml").write_text("project_key: kanbus\n", encoding="utf-8")
    project_dir = (tmp_path / "project").resolve()
    project_dir.mkdir()

    reset_configuration_load_count()
    first = daemon_paths.get_daemon_socket_path(tmp_path)
    second = daemon_paths.get_daemon_socket_path(tmp_path)

    assert first == project_dir / ".cache" / "kanbus.sock"
    assert second == first
    assert configuration_load_count() == 1


def test_remember_project_directory_avoids_configuration_load(tmp_path: Path) -> None:
    (tmp_path / ".kanbus.yml").write_text("project_key: kanbus\n", encoding="utf-8")
    (tmp_path / "project").mkdir()
    context = ProjectContext.discover(tmp_path)
    assert context is not None

    reset_configuration_load_count()
    daemon_paths.remember_project_directory(context)
    path = daemon_paths.get_daemon_socket_path(tmp_path)

    assert path == context.project_dir / ".cache" / "kanbus.sock"
    assert configuration_load_count() == 0


def test_get_daemon_socket_path_without_configuration_uses_discovered_project(
    tmp_path: Path,
) -> None:
    project_dir = (tmp_path / "project").resolve()
    project_dir.mkdir()

    path = daemon_paths.get_daemon_socket_path(tmp_path)

    assert path == project_dir / ".cache" / "kanbus.sock"


def test_get_daemon_socket_path_propagates_configuration_errors(
    tmp_path: Path,
) -> None:
    (tmp_path / ".kanbus.yml").write_text("project_key: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid YAML"):
        daemon_paths.get_daemon_socket_path(tmp_path)


def test_get_index_cache_path_uses_project_cache(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    monkeypatch.setattr(daemon_paths, "load_project_directory", lambda _r: project_dir)
    assert (
        daemon_paths.get_index_cache_path(tmp_path)
        == project_dir / ".cache" / "index.json"
    )
