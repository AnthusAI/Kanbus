"""Issue lookup helpers for project directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kanbus.issue_files import list_issue_identifiers, read_issue_from_file
from kanbus.models import IssueData
from kanbus.project import (
    ProjectMarkerError,
    discover_project_directories,
    find_project_local_directory,
    load_project_directory,
)


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

    Searches all project directories (including virtual projects and local
    directories) for the given identifier.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Issue lookup result.
    :rtype: IssueLookupResult
    :raises IssueLookupError: If the issue cannot be found.
    """
    try:
        project_dirs = discover_project_directories(root)
    except ProjectMarkerError as error:
        raise IssueLookupError(str(error)) from error

    if not project_dirs:
        raise IssueLookupError("project not initialized")

    for project_dir in project_dirs:
        for issues_dir in _search_directories(project_dir):
            issue_path = issues_dir / f"{identifier}.json"
            if issue_path.exists():
                issue = read_issue_from_file(issue_path)
                return IssueLookupResult(
                    issue=issue, issue_path=issue_path, project_dir=project_dir
                )

    raise IssueLookupError("not found")


def _search_directories(project_dir: Path) -> list[Path]:
    """Return issue directories to search for a given project directory."""
    dirs = [project_dir / "issues"]
    local_dir = find_project_local_directory(project_dir)
    if local_dir is not None:
        dirs.append(local_dir / "issues")
    return dirs


def resolve_issue_identifier(issues_dir: Path, project_key: str, candidate: str) -> str:
    """Resolve a full issue identifier from a user-provided value.

    Accepts a full identifier or a unique short identifier using the project key.

    :param issues_dir: Issues directory.
    :type issues_dir: Path
    :param project_key: Project key prefix.
    :type project_key: str
    :param candidate: Candidate identifier (full or short).
    :type candidate: str
    :return: Full issue identifier.
    :rtype: str
    :raises IssueLookupError: If no match or ambiguous short id.
    """
    issue_path = issues_dir / f"{candidate}.json"
    if issue_path.exists():
        return candidate

    matches = [
        identifier
        for identifier in list_issue_identifiers(issues_dir)
        if _short_id_matches(candidate, project_key, identifier)
    ]

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise IssueLookupError("not found")
    raise IssueLookupError("ambiguous short id")


def _short_id_matches(candidate: str, project_key: str, full_id: str) -> bool:
    if not candidate.startswith(project_key):
        return False
    if "-" not in candidate:
        return False
    prefix_key, prefix = candidate.split("-", 1)
    if prefix_key != project_key:
        return False
    if not prefix or len(prefix) > 6:
        return False
    if "-" not in full_id:
        return False
    full_key, full_suffix = full_id.split("-", 1)
    if full_key != project_key:
        return False
    return full_suffix.startswith(prefix)
