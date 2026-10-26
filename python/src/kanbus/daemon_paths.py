"""Daemon socket and cache paths."""

from __future__ import annotations

import threading
from pathlib import Path

from kanbus.project import (
    ProjectMarkerError,
    load_project_directory,
    resolve_project_path,
)
from kanbus.project_context import ProjectContext

_resolved_project_directories: dict[Path, Path] = {}
_resolved_project_directories_lock = threading.Lock()


def remember_project_directory(context: ProjectContext) -> None:
    """Record the primary project directory resolved by a project context.

    Every issue file operation asks for the daemon socket path. Recording the
    directory the command already resolved keeps those lookups from reloading
    the configuration. A context whose primary directory is ignored records
    nothing; the socket lookup then reports the same error as before.

    :param context: Project context built at command entry.
    :type context: ProjectContext
    """
    try:
        context.labeled_projects()
        project_dir = context.primary_project_directory()
    except ProjectMarkerError:
        return
    with _resolved_project_directories_lock:
        _resolved_project_directories[resolve_project_path(context.repository_root)] = (
            project_dir
        )


def _daemon_project_directory(root: Path) -> Path:
    key = resolve_project_path(root)
    with _resolved_project_directories_lock:
        remembered = _resolved_project_directories.get(key)
    if remembered is not None:
        return remembered
    context = ProjectContext.discover(root)
    if context is not None:
        context.labeled_projects()
        project_dir = context.primary_project_directory()
    else:
        project_dir = load_project_directory(root)
    with _resolved_project_directories_lock:
        _resolved_project_directories[key] = project_dir
    return project_dir


def get_daemon_socket_path(root: Path) -> Path:
    """Return the daemon socket path for a repository.

    :param root: Repository root path.
    :type root: Path
    :return: Path to daemon socket file.
    :rtype: Path
    """
    return _daemon_project_directory(root) / ".cache" / "kanbus.sock"


def get_index_cache_path(root: Path) -> Path:
    """Return the index cache file path for a repository.

    :param root: Repository root path.
    :type root: Path
    :return: Path to index cache file.
    :rtype: Path
    """
    project_dir = load_project_directory(root)
    return project_dir / ".cache" / "index.json"
