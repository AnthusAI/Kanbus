"""Tests for daemon path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskulus.daemon_paths import get_daemon_socket_path, get_index_cache_path
from taskulus.project import ProjectMarkerError, load_project_directory


def _write_project_marker(root: Path, project_dir: str) -> Path:
    marker = root / ".taskulus.yaml"
    marker.write_text(f"project_dir: {project_dir}\n", encoding="utf-8")
    return root / project_dir


def test_load_project_directory_requires_marker(tmp_path: Path) -> None:
    with pytest.raises(ProjectMarkerError, match="project not initialized"):
        load_project_directory(tmp_path)


def test_load_project_directory_requires_project_dir(tmp_path: Path) -> None:
    marker = tmp_path / ".taskulus.yaml"
    marker.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ProjectMarkerError, match="project directory not defined"):
        load_project_directory(tmp_path)


def test_daemon_paths_use_project_marker(tmp_path: Path) -> None:
    project_dir = _write_project_marker(tmp_path, "project")
    socket_path = get_daemon_socket_path(tmp_path)
    cache_path = get_index_cache_path(tmp_path)

    assert socket_path == project_dir / ".cache" / "taskulus.sock"
    assert cache_path == project_dir / ".cache" / "index.json"
