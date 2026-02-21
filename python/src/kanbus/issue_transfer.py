"""Local and shared issue transfer helpers."""

from __future__ import annotations

from pathlib import Path

from kanbus.issue_files import read_issue_from_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueData
from kanbus.project import (
    ensure_project_local_directory,
    find_project_local_directory,
)
from kanbus.event_history import (
    create_event,
    events_dir_for_local,
    events_dir_for_project,
    now_timestamp,
    transfer_payload,
    write_events_batch,
)
from kanbus.users import get_current_user


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
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueTransferError(str(error)) from error
    project_dir = lookup.project_dir

    local_dir = find_project_local_directory(project_dir)
    if local_dir is None:
        raise IssueTransferError("not found")

    local_issue_path = local_dir / "issues" / f"{identifier}.json"
    if not local_issue_path.exists():
        raise IssueTransferError("not found")

    target_path = project_dir / "issues" / f"{identifier}.json"
    if target_path.exists():
        raise IssueTransferError("already exists")

    issue = read_issue_from_file(local_issue_path)
    local_issue_path.replace(target_path)
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=issue.identifier,
        event_type="issue_promoted",
        actor_id=actor_id,
        payload=transfer_payload("local", "shared"),
        occurred_at=occurred_at,
    )
    try:
        events_dir = events_dir_for_project(project_dir)
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        target_path.replace(local_issue_path)
        raise IssueTransferError(str(error)) from error
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
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueTransferError(str(error)) from error
    project_dir = lookup.project_dir

    shared_issue_path = project_dir / "issues" / f"{identifier}.json"
    if not shared_issue_path.exists():
        raise IssueTransferError("issue is not in shared project")

    local_dir = ensure_project_local_directory(project_dir)
    target_path = local_dir / "issues" / f"{identifier}.json"
    if target_path.exists():
        raise IssueTransferError("already exists")

    issue = read_issue_from_file(shared_issue_path)
    shared_issue_path.replace(target_path)
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=issue.identifier,
        event_type="issue_localized",
        actor_id=actor_id,
        payload=transfer_payload("shared", "local"),
        occurred_at=occurred_at,
    )
    try:
        events_dir = events_dir_for_local(project_dir)
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        target_path.replace(shared_issue_path)
        raise IssueTransferError(str(error)) from error
    return issue
