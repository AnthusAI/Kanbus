"""
File system helpers for initialization.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from taskulus.project import ensure_project_local_directory


class InitializationError(RuntimeError):
    """Raised when project initialization fails."""


def ensure_git_repository(root: Path) -> None:
    """Ensure the provided path is inside a git repository.

    :param root: Directory to check for a git repository.
    :type root: Path
    :raises InitializationError: If the path is not a git repository.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise InitializationError("not a git repository")


def initialize_project(root: Path, create_local: bool = False) -> None:
    """Initialize the Taskulus project directory structure.

    :param root: Repository root path.
    :type root: Path
    :param create_local: Whether to create a project-local directory.
    :type create_local: bool
    :raises InitializationError: If the project is already initialized.
    """
    project_dir = root / "project"
    if project_dir.exists():
        raise InitializationError("already initialized")

    issues_dir = project_dir / "issues"

    project_dir.mkdir(parents=True, exist_ok=False)
    issues_dir.mkdir(parents=True)
    if create_local:
        ensure_project_local_directory(project_dir)
