"""Issue deletion workflow."""

from __future__ import annotations

from pathlib import Path

from kanbus.issue_files import write_issue_to_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.event_history import (
    create_event,
    events_dir_for_issue_path,
    issue_deleted_payload,
    now_timestamp,
    write_events_batch,
)
from kanbus.users import get_current_user


class IssueDeleteError(RuntimeError):
    """Raised when issue deletion fails."""


def delete_issue(root: Path, identifier: str) -> None:
    """Delete an issue file from disk.

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

    lookup.issue_path.unlink()
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=lookup.issue.identifier,
        event_type="issue_deleted",
        actor_id=actor_id,
        payload=issue_deleted_payload(lookup.issue),
        occurred_at=occurred_at,
    )
    events_dir = events_dir_for_issue_path(lookup.project_dir, lookup.issue_path)
    try:
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(lookup.issue, lookup.issue_path)
        raise IssueDeleteError(str(error)) from error
