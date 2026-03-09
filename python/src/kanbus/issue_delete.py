"""Issue deletion workflow."""

from __future__ import annotations

from pathlib import Path
from typing import List

from kanbus.issue_files import write_issue_to_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.event_history import (
    delete_events_for_issues,
    events_dir_for_issue_path,
)
from kanbus.issue_listing import load_issues_from_directory
from kanbus.project import find_project_local_directory
from kanbus.gossip import publish_issue_deleted


class IssueDeleteError(RuntimeError):
    """Raised when issue deletion fails."""


def get_descendant_identifiers(project_dir: Path, identifier: str) -> List[str]:
    """Return descendant issue identifiers in leaf-first order (children before parents).

    :param project_dir: Shared project directory.
    :type project_dir: Path
    :param identifier: Root issue identifier.
    :type identifier: str
    :return: List of descendant IDs, deepest first.
    :rtype: List[str]
    """
    parent_to_children: dict[str, List[str]] = {}
    issues_dir = project_dir / "issues"
    if issues_dir.is_dir():
        for issue in load_issues_from_directory(issues_dir):
            if issue.parent is not None:
                parent_to_children.setdefault(issue.parent, []).append(issue.identifier)
    local_dir = find_project_local_directory(project_dir)
    if local_dir is not None:
        local_issues_dir = local_dir / "issues"
        if local_issues_dir.is_dir():
            for issue in load_issues_from_directory(local_issues_dir):
                if issue.parent is not None:
                    parent_to_children.setdefault(issue.parent, []).append(
                        issue.identifier
                    )
    depth: dict[str, int] = {identifier: 0}
    queue: List[str] = [identifier]
    while queue:
        parent_id = queue.pop(0)
        for child_id in parent_to_children.get(parent_id, []):
            if child_id not in depth:
                depth[child_id] = depth[parent_id] + 1
                queue.append(child_id)
    descendants = [k for k in depth if k != identifier]
    return sorted(descendants, key=lambda x: -depth[x])


def delete_issue(root: Path, identifier: str) -> None:
    """Delete an issue file and all its event history from disk.

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

    issue_id = lookup.issue.identifier
    events_dir = events_dir_for_issue_path(lookup.project_dir, lookup.issue_path)
    lookup.issue_path.unlink()
    try:
        delete_events_for_issues(events_dir, {issue_id})
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(lookup.issue, lookup.issue_path)
        raise IssueDeleteError(str(error)) from error
    if lookup.issue_path.parent == lookup.project_dir / "issues":
        publish_issue_deleted(root, lookup.project_dir, issue_id, None)
