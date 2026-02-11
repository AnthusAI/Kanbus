"""Tests for file IO helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskulus.file_io import (
    InitializationError,
    ensure_git_repository,
    write_project_marker,
)


def test_ensure_git_repository_fails_outside_repo(tmp_path: Path) -> None:
    with pytest.raises(InitializationError, match="not a git repository"):
        ensure_git_repository(tmp_path)


def test_ensure_git_repository_succeeds_in_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    ensure_git_repository(tmp_path)


def test_write_project_marker(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_project_marker(tmp_path, project_dir)
    marker = tmp_path / ".taskulus.yaml"
    assert marker.exists()
    contents = marker.read_text(encoding="utf-8")
    assert "project_dir" in contents
