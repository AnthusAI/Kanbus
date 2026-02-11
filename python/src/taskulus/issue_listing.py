"""Issue listing utilities."""

from __future__ import annotations

from pathlib import Path
from typing import List

from taskulus.cache import collect_issue_file_mtimes, load_cache_if_valid, write_cache
from taskulus.daemon_client import is_daemon_enabled, request_index_list
from taskulus.daemon_paths import get_index_cache_path
from taskulus.index import build_index_from_directory
from taskulus.models import IssueData
from taskulus.project import load_project_directory


class IssueListingError(RuntimeError):
    """Raised when listing issues fails."""


def list_issues(root: Path) -> List[IssueData]:
    """List issues in the project.

    :param root: Repository root path.
    :type root: Path
    :return: List of issues.
    :rtype: List[IssueData]
    :raises IssueListingError: If listing fails.
    """
    if is_daemon_enabled():
        try:
            payloads = request_index_list(root)
            return [IssueData.model_validate(payload) for payload in payloads]
        except Exception as error:
            raise IssueListingError(str(error)) from error
    try:
        return _list_issues_locally(root)
    except Exception as error:
        raise IssueListingError(str(error)) from error


def _list_issues_locally(root: Path) -> List[IssueData]:
    project_dir = load_project_directory(root)
    issues_dir = project_dir / "issues"
    cache_path = get_index_cache_path(root)
    cached = load_cache_if_valid(cache_path, issues_dir)
    if cached is not None:
        return list(cached.by_id.values())
    index = build_index_from_directory(issues_dir)
    mtimes = collect_issue_file_mtimes(issues_dir)
    write_cache(index, cache_path, mtimes)
    return list(index.by_id.values())
