"""Canonical write-side gate for issue mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from kanbus.event_history import (
    EventRecord,
    create_event,
    delete_events_for_issues,
    events_dir_for_issue_path,
    issue_deleted_payload,
    now_timestamp,
    write_events_batch,
)
from kanbus.issue_files import write_issue_to_file
from kanbus.models import IssueData
from kanbus.right_now import (
    regenerate_right_now_ancestors,
    regenerate_right_now_for_issue_and_ancestors,
)


@dataclass(frozen=True)
class PersistIssueMutationRequest:
    """Request to persist an issue mutation through the write gate.

    :param project_dir: Shared project directory.
    :type project_dir: Path
    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    :param issue: Mutated issue data to persist.
    :type issue: IssueData
    :param actor_id: Identifier of the actor performing the mutation.
    :type actor_id: str
    :param events: Event records to write alongside the mutation.
    :type events: List[EventRecord]
    :param before_issue: Previous issue state for rollback on event write failure.
    :type before_issue: Optional[IssueData]
    :param relocate_to: Optional destination path when the issue file should move.
    :type relocate_to: Optional[Path]
    :param root: Repository root path for right-now regeneration.
    :type root: Path
    :param regenerate_right_now: Whether to regenerate right-now summaries after persist.
    :type regenerate_right_now: bool
    """

    project_dir: Path
    issue_path: Path
    issue: IssueData
    actor_id: str
    events: List[EventRecord]
    root: Path
    before_issue: Optional[IssueData] = None
    relocate_to: Optional[Path] = None
    regenerate_right_now: bool = True


@dataclass(frozen=True)
class PersistIssueMutationResult:
    """Result of persisting an issue mutation.

    :param issue: Persisted issue data with updated_at applied.
    :type issue: IssueData
    :param events: Event records that were written.
    :type events: List[EventRecord]
    """

    issue: IssueData
    events: List[EventRecord]


@dataclass(frozen=True)
class PersistIssueDeletionResult:
    """Result of persisting an issue deletion.

    :param event: The issue_deleted event record when retained.
    :type event: Optional[EventRecord]
    """

    event: Optional[EventRecord]


def persist_issue_mutation(
    request: PersistIssueMutationRequest,
) -> PersistIssueMutationResult:
    """Persist an issue mutation with updated_at and event history.

    :param request: Mutation request including issue, path, and events.
    :type request: PersistIssueMutationRequest
    :return: Persisted issue and written events.
    :rtype: PersistIssueMutationResult
    :raises RuntimeError: If event writing fails after rollback attempt.
    """
    current_time = datetime.now(timezone.utc)
    persisted_issue = request.issue.model_copy(update={"updated_at": current_time})
    rollback_issue = (
        request.before_issue if request.before_issue is not None else request.issue
    )
    write_issue_to_file(persisted_issue, request.issue_path)
    final_issue_path = request.issue_path
    if request.relocate_to is not None:
        request.issue_path.replace(request.relocate_to)
        final_issue_path = request.relocate_to
    events_dir = events_dir_for_issue_path(request.project_dir, final_issue_path)
    try:
        write_events_batch(events_dir, request.events)
    except Exception as error:  # noqa: BLE001
        if request.relocate_to is not None and final_issue_path.exists():
            final_issue_path.replace(request.issue_path)
        write_issue_to_file(rollback_issue, request.issue_path)
        raise RuntimeError(str(error)) from error
    if request.regenerate_right_now:
        regenerate_right_now_for_issue_and_ancestors(
            request.root,
            persisted_issue.identifier,
        )
    return PersistIssueMutationResult(issue=persisted_issue, events=request.events)


def persist_issue_deletion(
    root: Path,
    project_dir: Path,
    issue_path: Path,
    issue: IssueData,
    actor_id: str,
    *,
    retain_audit_event: bool = True,
    regenerate_right_now: bool = True,
) -> PersistIssueDeletionResult:
    """Delete an issue and optionally retain an issue_deleted audit event.

    :param root: Repository root path for right-now regeneration.
    :type root: Path
    :param project_dir: Shared project directory.
    :type project_dir: Path
    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    :param issue: Issue data being deleted.
    :type issue: IssueData
    :param actor_id: Identifier of the actor performing the deletion.
    :type actor_id: str
    :param retain_audit_event: Whether to keep a final issue_deleted event.
    :type retain_audit_event: bool
    :param regenerate_right_now: Whether to regenerate ancestor right-now summaries.
    :type regenerate_right_now: bool
    :return: Deletion result including the audit event when retained.
    :rtype: PersistIssueDeletionResult
    :raises RuntimeError: If event cleanup or audit write fails after rollback.
    """
    parent_identifier = issue.parent
    occurred_at = now_timestamp()
    deletion_event = create_event(
        issue_id=issue.identifier,
        event_type="issue_deleted",
        actor_id=actor_id,
        payload=issue_deleted_payload(issue),
        occurred_at=occurred_at,
    )
    events_dir = events_dir_for_issue_path(project_dir, issue_path)
    issue_path.unlink()
    try:
        delete_events_for_issues(events_dir, {issue.identifier})
        if retain_audit_event:
            write_events_batch(events_dir, [deletion_event])
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(issue, issue_path)
        raise RuntimeError(str(error)) from error
    if regenerate_right_now:
        regenerate_right_now_ancestors(root, parent_identifier)
    return PersistIssueDeletionResult(
        event=deletion_event if retain_audit_event else None
    )
