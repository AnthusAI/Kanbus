"""
File system helpers for initialization.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from taskulus.config import write_default_configuration


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


def write_project_marker(root: Path, project_dir: Path) -> None:
    """Write the .taskulus.yaml project marker.

    :param root: Repository root.
    :type root: Path
    :param project_dir: Project directory path.
    :type project_dir: Path
    """
    marker_path = root / ".taskulus.yaml"
    marker_path.write_text(
        yaml.safe_dump({"project_dir": project_dir.name}, sort_keys=False),
        encoding="utf-8",
    )


def initialize_project(root: Path, project_dir_name: str) -> None:
    """Initialize the Taskulus project directory structure.

    :param root: Repository root path.
    :type root: Path
    :param project_dir_name: Name of the project directory to create.
    :type project_dir_name: str
    :raises InitializationError: If the project is already initialized.
    """
    marker_path = root / ".taskulus.yaml"
    if marker_path.exists():
        raise InitializationError("already initialized")

    project_dir = root / project_dir_name
    issues_dir = project_dir / "issues"
    wiki_dir = project_dir / "wiki"

    project_dir.mkdir(parents=True, exist_ok=False)
    issues_dir.mkdir(parents=True)
    wiki_dir.mkdir(parents=True)

    write_default_configuration(project_dir / "config.yaml")
    (wiki_dir / "index.md").write_text("# Taskulus Wiki\n", encoding="utf-8")
    write_project_marker(root, project_dir)
