"""Issue lookup helpers for project directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from taskulus.issue_files import read_issue_from_file
from taskulus.models import IssueData
from taskulus.project import ProjectMarkerError, load_project_directory


class IssueLookupError(RuntimeError):
    """Raised when an issue lookup fails."""


@dataclass(frozen=True)
class IssueLookupResult:
    """Result of issue lookup."""

    issue: IssueData
    issue_path: Path
    project_dir: Path


def load_issue_from_project(root: Path, identifier: str) -> IssueLookupResult:
    """Load an issue by identifier from a project directory.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Issue lookup result.
    :rtype: IssueLookupResult
    :raises IssueLookupError: If the issue cannot be found.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise IssueLookupError(str(error)) from error

    issue_path = project_dir / "issues" / f"{identifier}.json"
    if not issue_path.exists():
        raise IssueLookupError("not found")

    issue = read_issue_from_file(issue_path)
    return IssueLookupResult(
        issue=issue, issue_path=issue_path, project_dir=project_dir
    )
