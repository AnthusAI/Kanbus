"""Dependency tree rendering utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from taskulus.issue_files import read_issue_from_file
from taskulus.models import DependencyLink, IssueData
from taskulus.project import ProjectMarkerError, load_project_directory

MAX_TREE_NODES = 25


class DependencyTreeError(RuntimeError):
    """Raised when dependency tree rendering fails."""


@dataclass(frozen=True)
class DependencyTreeNode:
    """Dependency tree node."""

    identifier: str
    title: str
    dependency_type: Optional[str]
    dependencies: List["DependencyTreeNode"]

    def to_dict(self) -> Dict[str, object]:
        """Serialize node to a dict.

        :return: Dictionary representation.
        :rtype: Dict[str, object]
        """
        payload: Dict[str, object] = {
            "id": self.identifier,
            "title": self.title,
            "dependencies": [child.to_dict() for child in self.dependencies],
        }
        if self.dependency_type is not None:
            payload["dependency_type"] = self.dependency_type
        return payload


def build_dependency_tree(
    root: Path, identifier: str, max_depth: Optional[int]
) -> DependencyTreeNode:
    """Build a dependency tree for the given issue.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier to start from.
    :type identifier: str
    :param max_depth: Optional maximum traversal depth.
    :type max_depth: Optional[int]
    :return: Dependency tree root.
    :rtype: DependencyTreeNode
    :raises DependencyTreeError: If tree building fails.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise DependencyTreeError(str(error)) from error

    issues_dir = project_dir / "issues"
    issues = _load_issues(issues_dir)
    if identifier not in issues:
        raise DependencyTreeError("not found")

    return _build_node(
        identifier=identifier,
        issues=issues,
        max_depth=max_depth,
        depth=0,
        visited=set(),
        dependency_type=None,
    )


def render_dependency_tree(
    node: DependencyTreeNode,
    output_format: str,
    max_nodes: int = MAX_TREE_NODES,
) -> str:
    """Render a dependency tree in the requested format.

    :param node: Dependency tree root.
    :type node: DependencyTreeNode
    :param output_format: Output format (text, json, dot).
    :type output_format: str
    :param max_nodes: Maximum nodes to render for text output.
    :type max_nodes: int
    :return: Rendered output string.
    :rtype: str
    :raises DependencyTreeError: If the format is unsupported.
    """
    if output_format == "json":
        return json.dumps(node.to_dict(), indent=2)
    if output_format == "dot":
        return _render_dot(node)
    if output_format == "text":
        return _render_ascii(node, max_nodes)
    raise DependencyTreeError("invalid format")


def _load_issues(issues_dir: Path) -> Dict[str, IssueData]:
    issues: Dict[str, IssueData] = {}
    for issue_path in sorted(issues_dir.glob("*.json"), key=lambda path: path.name):
        issue = read_issue_from_file(issue_path)
        issues[issue.identifier] = issue
    return issues


def _build_node(
    identifier: str,
    issues: Dict[str, IssueData],
    max_depth: Optional[int],
    depth: int,
    visited: Set[str],
    dependency_type: Optional[str],
) -> DependencyTreeNode:
    issue = issues[identifier]
    if identifier in visited:
        return DependencyTreeNode(
            identifier=issue.identifier,
            title=issue.title,
            dependency_type=dependency_type,
            dependencies=[],
        )
    visited.add(identifier)

    dependencies: List[DependencyTreeNode] = []
    if max_depth is None or depth < max_depth:
        for dependency in issue.dependencies:
            dependencies.append(
                _build_dependency(
                    dependency=dependency,
                    issues=issues,
                    max_depth=max_depth,
                    depth=depth + 1,
                    visited=visited,
                )
            )

    return DependencyTreeNode(
        identifier=issue.identifier,
        title=issue.title,
        dependency_type=dependency_type,
        dependencies=dependencies,
    )


def _build_dependency(
    dependency: DependencyLink,
    issues: Dict[str, IssueData],
    max_depth: Optional[int],
    depth: int,
    visited: Set[str],
) -> DependencyTreeNode:
    if dependency.target not in issues:
        raise DependencyTreeError(
            f"dependency target '{dependency.target}' does not exist"
        )
    return _build_node(
        identifier=dependency.target,
        issues=issues,
        max_depth=max_depth,
        depth=depth,
        visited=visited,
        dependency_type=dependency.dependency_type,
    )


def _render_ascii(node: DependencyTreeNode, max_nodes: int) -> str:
    lines: List[str] = []
    count = 0
    truncated = False

    def visit(current: DependencyTreeNode, prefix: str, is_last: bool) -> None:
        nonlocal count, truncated
        if count >= max_nodes:
            truncated = True
            return

        if prefix:
            connector = "`-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{current.identifier} {current.title}")
        else:
            lines.append(f"{current.identifier} {current.title}")
        count += 1

        if not current.dependencies:
            return

        child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
        last_index = len(current.dependencies) - 1
        for index, child in enumerate(current.dependencies):
            visit(child, child_prefix, index == last_index)

    visit(node, "", True)

    if truncated:
        lines.append("additional nodes omitted")
    return "\n".join(lines)


def _render_dot(node: DependencyTreeNode) -> str:
    edges: List[str] = []

    def visit(current: DependencyTreeNode) -> None:
        for child in current.dependencies:
            edges.append(f'  "{current.identifier}" -> "{child.identifier}";')
            visit(child)

    visit(node)
    lines = ["digraph dependencies {", *edges, "}"]
    return "\n".join(lines)
