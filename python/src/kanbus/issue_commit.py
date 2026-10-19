"""Commit board state (issues and events) to git."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from kanbus.file_io import InitializationError, ensure_git_repository
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.project import (
    ProjectMarkerError,
    get_configuration_path,
    load_project_directory,
)

COMMIT_MESSAGE = "chore(kanbus): commit board state"

# Ephemeral git identity for kbs commit subprocess only. These -c flags are not
# written to .git/config, so agent worktrees can commit without caller identity.
GIT_COMMIT_CONFIG = [
    "-c",
    "user.email=kanbus@localhost",
    "-c",
    "user.name=Kanbus",
]


class IssueCommitError(RuntimeError):
    """Raised when committing project issues fails."""


@dataclass(frozen=True)
class IssueCommitResult:
    """Result of a board state commit operation.

    :param committed: Whether a new commit was created.
    :type committed: bool
    :param includes_events: Whether project/events was part of the commit scope.
    :type includes_events: bool
    """

    committed: bool
    includes_events: bool


def commit_project_issues(root: Path) -> IssueCommitResult:
    """Stage and commit board state changes.

    ``project/issues/`` is always staged. ``project/events/`` is staged as
    well, in the same commit, unless the configuration sets ``events: false``.
    Git author identity is supplied via ephemeral ``-c`` flags (see
    ``GIT_COMMIT_CONFIG``); nothing is persisted to ``git config``.

    :param root: Repository root path.
    :type root: Path
    :return: Whether a new commit was created and which scope it covered.
    :rtype: IssueCommitResult
    :raises IssueCommitError: If the commit operation fails.
    """
    try:
        ensure_git_repository(root)
    except InitializationError as error:
        raise IssueCommitError(str(error)) from error

    try:
        project_dir = load_project_directory(root)
        configuration = load_project_configuration(get_configuration_path(root))
    except (ProjectMarkerError, ConfigurationError) as error:
        raise IssueCommitError(str(error)) from error

    issues_dir = project_dir / "issues"
    if not issues_dir.is_dir():
        raise IssueCommitError("project not initialized")

    root_path = root.resolve()
    committed_paths = [issues_dir.resolve().relative_to(root_path).as_posix()]
    events_dir = project_dir / "events"
    includes_events = configuration.events and events_dir.is_dir()
    if includes_events:
        committed_paths.append(events_dir.resolve().relative_to(root_path).as_posix())

    add_result = subprocess.run(
        ["git", "add", "--", *committed_paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if add_result.returncode != 0:
        message = (
            add_result.stderr.strip() or add_result.stdout.strip() or "git add failed"
        )
        raise IssueCommitError(message)

    staged_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *committed_paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if staged_result.returncode == 0:
        return IssueCommitResult(committed=False, includes_events=includes_events)

    commit_result = subprocess.run(
        [
            "git",
            *GIT_COMMIT_CONFIG,
            "commit",
            "-m",
            COMMIT_MESSAGE,
            "--",
            *committed_paths,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit_result.returncode != 0:
        message = (
            commit_result.stderr.strip()
            or commit_result.stdout.strip()
            or "git commit failed"
        )
        raise IssueCommitError(message)

    return IssueCommitResult(committed=True, includes_events=includes_events)
