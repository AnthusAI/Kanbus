"""Issue listing utilities."""

from __future__ import annotations

from pathlib import Path
from typing import List

from taskulus.cache import collect_issue_file_mtimes, load_cache_if_valid, write_cache
from taskulus.daemon_client import is_daemon_enabled, request_index_list
from taskulus.index import build_index_from_directory
from taskulus.issue_files import read_issue_from_file
from taskulus.models import IssueData
from taskulus.project import (
    ProjectMarkerError,
    discover_project_directories,
    find_project_local_directory,
    load_project_directory,
)
from taskulus.migration import MigrationError, load_beads_issues
from taskulus.queries import filter_issues, search_issues, sort_issues


class IssueListingError(RuntimeError):
    """Raised when listing issues fails."""


def list_issues(
    root: Path,
    status: str | None = None,
    issue_type: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    sort: str | None = None,
    search: str | None = None,
    include_local: bool = True,
    local_only: bool = False,
    beads_mode: bool = False,
) -> List[IssueData]:
    """List issues in the project.

    :param root: Repository root path.
    :type root: Path
    :return: List of issues.
    :rtype: List[IssueData]
    :param beads_mode: Whether to read from Beads JSONL instead of project files.
    :type beads_mode: bool
    :raises IssueListingError: If listing fails.
    """
    if local_only and not include_local:
        raise IssueListingError("local-only conflicts with no-local")
    if beads_mode:
        if local_only or not include_local:
            raise IssueListingError("beads mode does not support local filtering")
        try:
            issues = load_beads_issues(root)
        except MigrationError as error:
            raise IssueListingError(str(error)) from error
        return _apply_query(issues, status, issue_type, assignee, label, sort, search)
    try:
        project_dirs = discover_project_directories(root)
    except ProjectMarkerError as error:
        raise IssueListingError(str(error)) from error
    if not project_dirs:
        raise IssueListingError("project not initialized")

    if len(project_dirs) > 1:
        issues = _list_issues_across_projects(
            root, project_dirs, include_local, local_only
        )
        return _apply_query(issues, status, issue_type, assignee, label, sort, search)

    project_dir = project_dirs[0]
    local_dir = None
    if include_local or local_only:
        local_dir = find_project_local_directory(project_dir)
        if local_dir is not None or local_only:
            try:
                issues = _list_issues_with_local(
                    project_dir,
                    local_dir,
                    include_local,
                    local_only,
                )
                return _apply_query(
                    issues, status, issue_type, assignee, label, sort, search
                )
            except Exception as error:
                raise IssueListingError(str(error)) from error

    if is_daemon_enabled():
        try:
            payloads = request_index_list(root)
            issues = [IssueData.model_validate(payload) for payload in payloads]
            issues = [_tag_issue_source(issue, "shared") for issue in issues]
            return _apply_query(
                issues, status, issue_type, assignee, label, sort, search
            )
        except Exception as error:
            raise IssueListingError(str(error)) from error
    try:
        issues = _list_issues_locally(root)
        issues = [_tag_issue_source(issue, "shared") for issue in issues]
        return _apply_query(issues, status, issue_type, assignee, label, sort, search)
    except Exception as error:
        raise IssueListingError(str(error)) from error


def _list_issues_locally(root: Path) -> List[IssueData]:
    project_dir = load_project_directory(root)
    return _list_issues_for_project(project_dir)


def _list_issues_for_project(project_dir: Path) -> List[IssueData]:
    issues_dir = project_dir / "issues"
    cache_path = project_dir / ".cache" / "index.json"
    cached = load_cache_if_valid(cache_path, issues_dir)
    if cached is not None:
        return list(cached.by_id.values())
    index = build_index_from_directory(issues_dir)
    mtimes = collect_issue_file_mtimes(issues_dir)
    write_cache(index, cache_path, mtimes)
    return list(index.by_id.values())


def _list_issues_with_local(
    project_dir: Path,
    local_dir: Path | None,
    include_local: bool,
    local_only: bool,
) -> List[IssueData]:
    shared_issues = _list_issues_for_project(project_dir)
    shared_tagged = [_tag_issue_source(issue, "shared") for issue in shared_issues]

    local_tagged: List[IssueData] = []
    if local_dir is not None:
        issues_dir = local_dir / "issues"
        if issues_dir.exists():
            local_tagged = [
                _tag_issue_source(issue, "local")
                for issue in _load_issues_from_directory(issues_dir)
            ]

    if local_only:
        return local_tagged
    if include_local:
        return [*shared_tagged, *local_tagged]
    return shared_tagged


def _list_issues_across_projects(
    root: Path,
    project_dirs: List[Path],
    include_local: bool,
    local_only: bool,
) -> List[IssueData]:
    issues: List[IssueData] = []
    for project_dir in sorted(project_dirs):
        local_dir = None
        if include_local or local_only:
            local_dir = find_project_local_directory(project_dir)
        if local_only and local_dir is None:
            continue
        project_issues = _list_issues_with_local(
            project_dir,
            local_dir,
            include_local,
            local_only,
        )
        project_issues = [
            _tag_issue_project(issue, root, project_dir) for issue in project_issues
        ]
        issues.extend(project_issues)
    return issues


def _load_issues_from_directory(issues_dir: Path) -> List[IssueData]:
    issues = [
        read_issue_from_file(path)
        for path in sorted(issues_dir.glob("*.json"), key=lambda item: item.name)
    ]
    return issues


def _tag_issue_source(issue: IssueData, source: str) -> IssueData:
    custom = {**issue.custom, "source": source}
    return issue.model_copy(update={"custom": custom})


def _tag_issue_project(issue: IssueData, root: Path, project_dir: Path) -> IssueData:
    try:
        project_path = project_dir.relative_to(root)
    except ValueError:
        project_path = project_dir
    custom = {**issue.custom, "project_path": str(project_path)}
    return issue.model_copy(update={"custom": custom})


def _apply_query(
    issues: List[IssueData],
    status: str | None,
    issue_type: str | None,
    assignee: str | None,
    label: str | None,
    sort: str | None,
    search: str | None,
) -> List[IssueData]:
    filtered = filter_issues(issues, status, issue_type, assignee, label)
    searched = search_issues(filtered, search)
    return sort_issues(searched, sort)
