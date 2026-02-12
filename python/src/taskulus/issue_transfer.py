"""Local and shared issue transfer helpers."""

from __future__ import annotations

from pathlib import Path

from taskulus.issue_files import read_issue_from_file
from taskulus.models import IssueData
from taskulus.project import (
    ProjectMarkerError,
    ensure_project_local_directory,
    find_project_local_directory,
    load_project_directory,
)


class IssueTransferError(RuntimeError):
    """Raised when moving issues between shared and local storage fails."""


def promote_issue(root: Path, identifier: str) -> IssueData:
    """Move a local issue into the shared project directory.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Issue data that was promoted.
    :rtype: IssueData
    :raises IssueTransferError: If promotion fails.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise IssueTransferError(str(error)) from error

    local_dir = find_project_local_directory(project_dir)
    if local_dir is None:
        raise IssueTransferError("project-local not initialized")

    local_issue_path = local_dir / "issues" / f"{identifier}.json"
    if not local_issue_path.exists():
        raise IssueTransferError("not found")

    target_path = project_dir / "issues" / f"{identifier}.json"
    if target_path.exists():
        raise IssueTransferError("already exists")

    issue = read_issue_from_file(local_issue_path)
    local_issue_path.replace(target_path)
    return issue


def localize_issue(root: Path, identifier: str) -> IssueData:
    """Move a shared issue into the project-local directory.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Issue data that was localized.
    :rtype: IssueData
    :raises IssueTransferError: If localization fails.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise IssueTransferError(str(error)) from error

    shared_issue_path = project_dir / "issues" / f"{identifier}.json"
    if not shared_issue_path.exists():
        raise IssueTransferError("not found")

    local_dir = ensure_project_local_directory(project_dir)
    target_path = local_dir / "issues" / f"{identifier}.json"
    if target_path.exists():
        raise IssueTransferError("already exists")

    issue = read_issue_from_file(shared_issue_path)
    shared_issue_path.replace(target_path)
    return issue
