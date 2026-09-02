"""Right-now CLI listing and formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from kanbus.config_loader import load_project_configuration
from kanbus.issue_listing import list_issues
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project import ProjectMarkerError, get_configuration_path
from kanbus.queries import sort_issues_by_recently_updated
from kanbus.right_now import get_right_now_summary

RIGHT_NOW_PLACEHOLDER = "(no right-now summary)"
DEFAULT_RIGHT_NOW_LIMIT = 30


@dataclass(frozen=True)
class RightNowCommandOptions:
    """Options for the right-now CLI command.

    :param limit: Maximum number of issues to include after sorting.
    :type limit: int
    :param tree: Whether to render a hierarchical tree.
    :type tree: bool
    :param expanded: Whether tree nodes default to expanded markers.
    :type expanded: bool
    :param collapsed: Whether tree nodes default to collapsed markers.
    :type collapsed: bool
    :param raw: Whether to omit right-now summaries.
    :type raw: bool
    :param as_json: Whether to emit JSON output.
    :type as_json: bool
    """

    limit: int = DEFAULT_RIGHT_NOW_LIMIT
    tree: bool = False
    expanded: bool = False
    collapsed: bool = False
    raw: bool = False
    as_json: bool = False


def run_right_now_command(
    root: Path,
    options: RightNowCommandOptions,
) -> str:
    """List recently-updated issues for the right-now CLI command.

    :param root: Repository root path.
    :type root: Path
    :param options: Right-now command options.
    :type options: RightNowCommandOptions
    :return: Formatted CLI output.
    :rtype: str
    :raises IssueListingError: When issue listing fails.
    """
    issues = list_issues(root)
    sorted_issues = sort_issues_by_recently_updated(issues)
    if options.limit > 0:
        sorted_issues = sorted_issues[: options.limit]
    configuration = _load_configuration(root)
    tree_expanded = _resolve_tree_expanded(options, configuration)
    if options.as_json:
        if options.tree:
            roots = _build_right_now_tree(sorted_issues)
            payload = [_serialize_tree_json_node(node, options.raw) for node in roots]
            return json.dumps(payload, indent=2) + "\n"
        payload = [
            _serialize_flat_json_entry(issue, options.raw) for issue in sorted_issues
        ]
        return json.dumps(payload, indent=2) + "\n"
    if options.tree:
        roots = _build_right_now_tree(sorted_issues)
        lines: List[str] = []
        for node in roots:
            lines.extend(
                _render_tree_node(node, tree_expanded=tree_expanded, raw=options.raw)
            )
        return "\n".join(lines) + ("\n" if lines else "")
    lines = [
        line
        for issue in sorted_issues
        for line in _render_flat_issue(issue, raw=options.raw)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def _load_configuration(root: Path) -> Optional[ProjectConfiguration]:
    try:
        return load_project_configuration(get_configuration_path(root))
    except (ProjectMarkerError, RuntimeError):
        return None


def _resolve_tree_expanded(
    options: RightNowCommandOptions,
    configuration: Optional[ProjectConfiguration],
) -> bool:
    if options.expanded:
        return True
    if options.collapsed:
        return False
    if configuration is not None:
        return configuration.right_now.default_tree_expanded
    return False


def _format_updated_at(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _render_flat_issue(issue: IssueData, raw: bool) -> List[str]:
    header = (
        f"{_format_updated_at(issue.updated_at)}  {issue.identifier}  {issue.title}"
    )
    if raw:
        return [header]
    summary = get_right_now_summary(issue)
    summary_text = summary if summary is not None else RIGHT_NOW_PLACEHOLDER
    return [header, f"    {summary_text}"]


@dataclass
class RightNowTreeNode:
    """Hierarchy node for right-now tree rendering.

    :param issue: Issue represented by this node.
    :type issue: IssueData
    :param children: Child nodes in display order.
    :type children: List[RightNowTreeNode]
    """

    issue: IssueData
    children: List["RightNowTreeNode"]


def _build_right_now_tree(issues: List[IssueData]) -> List[RightNowTreeNode]:
    identifiers = {issue.identifier for issue in issues}
    children_by_parent: Dict[str, List[IssueData]] = {}
    for issue in issues:
        if issue.parent is None:
            continue
        children_by_parent.setdefault(issue.parent, []).append(issue)
    for parent_identifier, children in children_by_parent.items():
        children_by_parent[parent_identifier] = sort_issues_by_recently_updated(
            children
        )
    roots = [
        issue
        for issue in issues
        if issue.parent is None or issue.parent not in identifiers
    ]
    roots = sort_issues_by_recently_updated(roots)

    def build_node(issue: IssueData) -> RightNowTreeNode:
        child_issues = children_by_parent.get(issue.identifier, [])
        return RightNowTreeNode(
            issue=issue,
            children=[build_node(child) for child in child_issues],
        )

    return [build_node(issue) for issue in roots]


def _collapse_marker(tree_expanded: bool) -> str:
    return "[-]" if tree_expanded else "[+]"


def _render_tree_node(
    node: RightNowTreeNode,
    *,
    tree_expanded: bool,
    raw: bool,
    depth: int = 0,
) -> List[str]:
    indent = "  " * depth
    marker = _collapse_marker(tree_expanded)
    issue = node.issue
    header = (
        f"{indent}{marker} {_format_updated_at(issue.updated_at)}  "
        f"{issue.identifier}  {issue.title}"
    )
    lines = [header]
    if not raw:
        summary = get_right_now_summary(issue)
        summary_text = summary if summary is not None else RIGHT_NOW_PLACEHOLDER
        lines.append(f"{indent}    {summary_text}")
    for child in node.children:
        lines.extend(
            _render_tree_node(
                child,
                tree_expanded=tree_expanded,
                raw=raw,
                depth=depth + 1,
            )
        )
    return lines


def _serialize_flat_json_entry(issue: IssueData, raw: bool) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "id": issue.identifier,
        "title": issue.title,
        "type": issue.issue_type,
        "status": issue.status,
        "updated_at": _format_updated_at(issue.updated_at),
    }
    if not raw:
        entry["right_now_summary"] = get_right_now_summary(issue)
    entry["parent"] = issue.parent
    return entry


def _serialize_tree_json_node(
    node: RightNowTreeNode,
    raw: bool,
) -> Dict[str, Any]:
    issue = node.issue
    entry: Dict[str, Any] = {
        "id": issue.identifier,
        "title": issue.title,
        "updated_at": _format_updated_at(issue.updated_at),
    }
    if not raw:
        entry["right_now_summary"] = get_right_now_summary(issue)
    entry["children"] = [
        _serialize_tree_json_node(child, raw) for child in node.children
    ]
    return entry
