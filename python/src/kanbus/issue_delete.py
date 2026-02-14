"""Issue deletion workflow."""

from __future__ import annotations

from pathlib import Path

from kanbus.issue_lookup import IssueLookupError, load_issue_from_project


class IssueDeleteError(RuntimeError):
    """Raised when issue deletion fails."""


def delete_issue(root: Path, identifier: str) -> None:
    """Delete an issue file from disk.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :raises IssueDeleteError: If deletion fails.
    """
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueDeleteError(str(error)) from error

    lookup.issue_path.unlink()
