"""Dependency management utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from taskulus.issue_files import read_issue_from_file, write_issue_to_file
from taskulus.issue_lookup import IssueLookupError, load_issue_from_project
from taskulus.models import DependencyLink, IssueData
from taskulus.project import (
    ProjectMarkerError,
    discover_project_directories,
    find_project_local_directory,
)
from taskulus.migration import MigrationError, load_beads_issues

ALLOWED_DEPENDENCY_TYPES = {"blocked-by", "relates-to"}


class DependencyError(RuntimeError):
    """Raised when dependency operations fail."""


@dataclass(frozen=True)
class DependencyGraph:
    """Dependency graph built from blocked-by links."""

    edges: dict[str, list[str]]


def add_dependency(
    root: Path,
    source_id: str,
    target_id: str,
    dependency_type: str,
) -> IssueData:
    """Add a dependency to an issue.

    :param root: Repository root path.
    :type root: Path
    :param source_id: Issue identifier to update.
    :type source_id: str
    :param target_id: Dependency target issue identifier.
    :type target_id: str
    :param dependency_type: Dependency type to add.
    :type dependency_type: str
    :return: Updated issue data.
    :rtype: IssueData
    :raises DependencyError: If the dependency cannot be added.
    """
    _validate_dependency_type(dependency_type)
    try:
        source_lookup = load_issue_from_project(root, source_id)
        load_issue_from_project(root, target_id)
    except (IssueLookupError, ProjectMarkerError) as error:
        raise DependencyError(str(error)) from error

    if dependency_type == "blocked-by":
        _ensure_no_cycle(source_lookup.project_dir, source_id, target_id)

    if _has_dependency(source_lookup.issue, target_id, dependency_type):
        return source_lookup.issue

    updated_issue = source_lookup.issue.model_copy(
        update={
            "dependencies": [
                *source_lookup.issue.dependencies,
                DependencyLink(target=target_id, type=dependency_type),
            ]
        }
    )
    write_issue_to_file(updated_issue, source_lookup.issue_path)
    return updated_issue


def remove_dependency(
    root: Path,
    source_id: str,
    target_id: str,
    dependency_type: str,
) -> IssueData:
    """Remove a dependency from an issue.

    :param root: Repository root path.
    :type root: Path
    :param source_id: Issue identifier to update.
    :type source_id: str
    :param target_id: Dependency target issue identifier.
    :type target_id: str
    :param dependency_type: Dependency type to remove.
    :type dependency_type: str
    :return: Updated issue data.
    :rtype: IssueData
    :raises DependencyError: If the dependency cannot be removed.
    """
    _validate_dependency_type(dependency_type)
    try:
        source_lookup = load_issue_from_project(root, source_id)
    except (IssueLookupError, ProjectMarkerError) as error:
        raise DependencyError(str(error)) from error

    filtered = [
        dependency
        for dependency in source_lookup.issue.dependencies
        if not (
            dependency.target == target_id
            and dependency.dependency_type == dependency_type
        )
    ]
    updated_issue = source_lookup.issue.model_copy(update={"dependencies": filtered})
    write_issue_to_file(updated_issue, source_lookup.issue_path)
    return updated_issue


def list_ready_issues(
    root: Path,
    include_local: bool = True,
    local_only: bool = False,
    beads_mode: bool = False,
) -> List[IssueData]:
    """List issues that are not blocked by dependencies.

    :param root: Repository root path.
    :type root: Path
    :param beads_mode: Whether to read from Beads JSONL instead of project files.
    :type beads_mode: bool
    :return: Ready issues.
    :rtype: List[IssueData]
    :raises DependencyError: If listing fails.
    """
    if local_only and not include_local:
        raise DependencyError("local-only conflicts with no-local")
    if beads_mode:
        if local_only or not include_local:
            raise DependencyError("beads mode does not support local filtering")
        try:
            issues = load_beads_issues(root)
        except MigrationError as error:
            raise DependencyError(str(error)) from error
        return [
            issue
            for issue in issues
            if issue.status != "closed" and not _blocked_by_dependency(issue)
        ]
    try:
        project_dirs = discover_project_directories(root)
    except ProjectMarkerError as error:
        raise DependencyError(str(error)) from error
    if not project_dirs:
        raise DependencyError("project not initialized")

    issues: List[IssueData] = []
    if len(project_dirs) == 1:
        issues = _load_ready_issues_for_project(
            root, project_dirs[0], include_local, local_only, tag_project=False
        )
    else:
        for project_dir in sorted(project_dirs):
            issues.extend(
                _load_ready_issues_for_project(
                    root, project_dir, include_local, local_only, tag_project=True
                )
            )

    ready = [
        issue
        for issue in issues
        if issue.status != "closed" and not _blocked_by_dependency(issue)
    ]
    return ready


def _load_ready_issues_for_project(
    root: Path,
    project_dir: Path,
    include_local: bool,
    local_only: bool,
    tag_project: bool,
) -> List[IssueData]:
    issues_dir = project_dir / "issues"
    shared_issues = _load_issues_from_directory(issues_dir)
    shared_tagged = [_tag_issue_source(issue, "shared") for issue in shared_issues]
    if tag_project:
        shared_tagged = [
            _tag_issue_project(issue, root, project_dir) for issue in shared_tagged
        ]

    local_tagged: List[IssueData] = []
    if include_local or local_only:
        local_dir = find_project_local_directory(project_dir)
        if local_dir is not None:
            local_issues_dir = local_dir / "issues"
            if local_issues_dir.exists():
                local_tagged = [
                    _tag_issue_source(issue, "local")
                    for issue in _load_issues_from_directory(local_issues_dir)
                ]
                if tag_project:
                    local_tagged = [
                        _tag_issue_project(issue, root, project_dir)
                        for issue in local_tagged
                    ]

    if local_only:
        return local_tagged
    if include_local:
        return [*shared_tagged, *local_tagged]
    return shared_tagged


def _load_issues_from_directory(issues_dir: Path) -> List[IssueData]:
    return [
        read_issue_from_file(path)
        for path in sorted(issues_dir.glob("*.json"), key=lambda item: item.name)
    ]


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


def _blocked_by_dependency(issue: IssueData) -> bool:
    return any(
        dependency.dependency_type == "blocked-by" for dependency in issue.dependencies
    )


def _validate_dependency_type(dependency_type: str) -> None:
    if dependency_type not in ALLOWED_DEPENDENCY_TYPES:
        raise DependencyError("invalid dependency type")


def _has_dependency(issue: IssueData, target_id: str, dependency_type: str) -> bool:
    return any(
        dependency.target == target_id and dependency.dependency_type == dependency_type
        for dependency in issue.dependencies
    )


def _ensure_no_cycle(project_dir: Path, source_id: str, target_id: str) -> None:
    graph = _build_dependency_graph(project_dir)
    graph.edges.setdefault(source_id, []).append(target_id)
    if _detect_cycle(graph, source_id):
        raise DependencyError("cycle detected")


def _build_dependency_graph(project_dir: Path) -> DependencyGraph:
    issues_dir = project_dir / "issues"
    edges: dict[str, list[str]] = {}
    for issue_path in issues_dir.glob("*.json"):
        issue = read_issue_from_file(issue_path)
        blocked_targets = [
            dependency.target
            for dependency in issue.dependencies
            if dependency.dependency_type == "blocked-by"
        ]
        if blocked_targets:
            edges[issue.identifier] = blocked_targets
    return DependencyGraph(edges=edges)


def _detect_cycle(graph: DependencyGraph, start: str) -> bool:
    visited: set[str] = set()
    stack: set[str] = set()

    def visit(node: str) -> bool:
        if node in stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        stack.add(node)
        for neighbor in graph.edges.get(node, []):
            if visit(neighbor):
                return True
        stack.remove(node)
        return False

    return visit(start)
