"""Tests for doctor diagnostics."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskulus.config import write_default_configuration
from taskulus.doctor import DoctorError, run_doctor


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)


def _write_project(root: Path, project_dir: str) -> Path:
    marker = root / ".taskulus.yaml"
    marker.write_text(f"project_dir: {project_dir}\n", encoding="utf-8")
    project_path = root / project_dir
    project_path.mkdir(parents=True)
    write_default_configuration(project_path / "config.yaml")
    return project_path


def test_run_doctor_requires_git_repo(tmp_path: Path) -> None:
    with pytest.raises(DoctorError, match="not a git repository"):
        run_doctor(tmp_path)


def test_run_doctor_requires_project_marker(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    with pytest.raises(DoctorError, match="project not initialized"):
        run_doctor(tmp_path)


def test_run_doctor_requires_valid_config(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    project_path = tmp_path / "project"
    marker = tmp_path / ".taskulus.yaml"
    marker.write_text("project_dir: project\n", encoding="utf-8")
    project_path.mkdir(parents=True)
    (project_path / "config.yaml").write_text("{}\n", encoding="utf-8")
    with pytest.raises(DoctorError):
        run_doctor(tmp_path)


def test_run_doctor_success(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    project_path = _write_project(tmp_path, "project")
    result = run_doctor(tmp_path)
    assert result.project_dir == project_path
