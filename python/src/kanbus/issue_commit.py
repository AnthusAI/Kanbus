"""Commit project/issues to git."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from kanbus.file_io import InitializationError, ensure_git_repository
from kanbus.project import ProjectMarkerError, load_project_directory

COMMIT_MESSAGE = "chore(kanbus): commit board state (issues)"

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
    """Result of a project/issues commit operation."""

    committed: bool


def commit_project_issues(root: Path) -> IssueCommitResult:
    """Stage and commit project/issues changes.

    Only ``project/issues/`` is staged. ``project/events/`` is never
    included. Git author identity is supplied via ephemeral ``-c`` flags
    (see ``GIT_COMMIT_CONFIG``); nothing is persisted to ``git config``.

    :param root: Repository root path.
    :type root: Path
    :return: Whether a new commit was created.
    :rtype: IssueCommitResult
    :raises IssueCommitError: If the commit operation fails.
    """
    try:
        ensure_git_repository(root)
    except InitializationError as error:
        raise IssueCommitError(str(error)) from error

    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise IssueCommitError(str(error)) from error

    issues_dir = project_dir / "issues"
    if not issues_dir.is_dir():
        raise IssueCommitError("project not initialized")

    root_path = root.resolve()
    issues_path = issues_dir.resolve().relative_to(root_path).as_posix()
    add_result = subprocess.run(
        ["git", "add", "--", issues_path],
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
        ["git", "diff", "--cached", "--quiet", "--", issues_path],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if staged_result.returncode == 0:
        return IssueCommitResult(committed=False)

    commit_result = subprocess.run(
        ["git", *GIT_COMMIT_CONFIG, "commit", "-m", COMMIT_MESSAGE, "--", issues_path],
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

    return IssueCommitResult(committed=True)
