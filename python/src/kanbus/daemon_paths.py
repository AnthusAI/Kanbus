"""Daemon socket and cache paths."""

from __future__ import annotations

from pathlib import Path

from kanbus.project import load_project_directory


def get_daemon_socket_path(root: Path) -> Path:
    """Return the daemon socket path for a repository.

    :param root: Repository root path.
    :type root: Path
    :return: Path to daemon socket file.
    :rtype: Path
    """
    project_dir = load_project_directory(root)
    return project_dir / ".cache" / "kanbus.sock"


def get_index_cache_path(root: Path) -> Path:
    """Return the index cache file path for a repository.

    :param root: Repository root path.
    :type root: Path
    :return: Path to index cache file.
    :rtype: Path
    """
    project_dir = load_project_directory(root)
    return project_dir / ".cache" / "index.json"
