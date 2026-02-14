"""
File system helpers for initialization.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
import yaml

from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.project_management_template import (
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE,
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
)
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
    config_path = root / ".taskulus.yml"
    if not config_path.exists():
        config_path.write_text(
            yaml.safe_dump(DEFAULT_CONFIGURATION, sort_keys=False),
            encoding="utf-8",
        )
    _write_project_guard_files(project_dir)
    template_path = root / DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME
    if not template_path.exists():
        template_path.write_text(
            DEFAULT_PROJECT_MANAGEMENT_TEMPLATE,
            encoding="utf-8",
        )
    if create_local:
        ensure_project_local_directory(project_dir)


def _write_project_guard_files(project_dir: Path) -> None:
    agents_path = project_dir / "AGENTS.md"
    agents_path.write_text(
        "\n".join(
            [
                "# DO NOT EDIT HERE",
                "",
                "Editing anything under project/ directly is hacking the data and is a sin against The Way.",
                "Do not read or write in this folder. Use Taskulus commands instead.",
                "",
                "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    do_not_edit = project_dir / "DO_NOT_EDIT"
    do_not_edit.write_text(
        "\n".join(
            [
                "DO NOT EDIT ANYTHING IN project/",
                "This folder is guarded by The Way.",
                "All changes must go through Taskulus (see ../AGENTS.md and ../CONTRIBUTING_AGENT.md).",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
