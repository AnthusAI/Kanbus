"""Dependency management utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from taskulus.issue_files import read_issue_from_file, write_issue_to_file
from taskulus.issue_lookup import IssueLookupError, load_issue_from_project
from taskulus.models import DependencyLink, IssueData
from taskulus.project import ProjectMarkerError, load_project_directory

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
        try:
            _ensure_no_cycle(root, source_id, target_id)
        except ProjectMarkerError as error:
            raise DependencyError(str(error)) from error

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


def list_ready_issues(root: Path) -> List[IssueData]:
    """List issues that are not blocked by dependencies.

    :param root: Repository root path.
    :type root: Path
    :return: Ready issues.
    :rtype: List[IssueData]
    :raises DependencyError: If listing fails.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise DependencyError(str(error)) from error

    issues_dir = project_dir / "issues"
    issues = [
        read_issue_from_file(path)
        for path in sorted(issues_dir.glob("*.json"), key=lambda item: item.name)
    ]
    ready = [
        issue
        for issue in issues
        if issue.status != "closed" and not _blocked_by_dependency(issue)
    ]
    return ready


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


def _ensure_no_cycle(root: Path, source_id: str, target_id: str) -> None:
    graph = _build_dependency_graph(root)
    graph.edges.setdefault(source_id, []).append(target_id)
    if _detect_cycle(graph, source_id):
        raise DependencyError("cycle detected")


def _build_dependency_graph(root: Path) -> DependencyGraph:
    project_dir = load_project_directory(root)
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
