"""Issue deletion workflow."""

from __future__ import annotations

from pathlib import Path
from typing import List

from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.issue_listing import load_issues_from_directory
from kanbus.issue_mutation import persist_issue_deletion
from kanbus.project import find_project_local_directory
from kanbus.gossip import publish_issue_deleted
from kanbus.users import get_current_user


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


def delete_issue(
    root: Path, identifier: str, *, retain_audit_event: bool = True
) -> None:
    """Delete an issue file and its event history from disk.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :param retain_audit_event: Whether to keep a final issue_deleted event.
    :type retain_audit_event: bool
    :raises IssueDeleteError: If deletion fails.
    """
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueDeleteError(str(error)) from error

    issue_id = lookup.issue.identifier
    actor_id = get_current_user()
    try:
        result = persist_issue_deletion(
            lookup.project_dir,
            lookup.issue_path,
            lookup.issue,
            actor_id,
            retain_audit_event=retain_audit_event,
        )
    except Exception as error:  # noqa: BLE001
        raise IssueDeleteError(str(error)) from error
    if lookup.issue_path.parent == lookup.project_dir / "issues":
        event_id = result.event.event_id if result.event is not None else None
        publish_issue_deleted(root, lookup.project_dir, issue_id, event_id)
