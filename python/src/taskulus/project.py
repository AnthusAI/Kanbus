"""Project marker loading utilities."""

from __future__ import annotations

from pathlib import Path

import yaml


class ProjectMarkerError(RuntimeError):
    """Raised when the project marker is missing or invalid."""


def load_project_directory(root: Path) -> Path:
    """Load the project directory from the .taskulus.yaml marker.

    :param root: Repository root path.
    :type root: Path
    :return: Path to the project directory.
    :rtype: Path
    :raises ProjectMarkerError: If the marker is missing or invalid.
    """
    marker_path = root / ".taskulus.yaml"
    if not marker_path.exists():
        raise ProjectMarkerError("project not initialized")

    data = yaml.safe_load(marker_path.read_text(encoding="utf-8")) or {}
    project_dir = data.get("project_dir")
    if not project_dir:
        raise ProjectMarkerError("project directory not defined")

    return root / project_dir
