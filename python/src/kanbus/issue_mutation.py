"""Canonical write-side gate for issue mutations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

from kanbus.event_history import (
    EventRecord,
    create_event,
    delete_events_for_issues,
    events_dir_for_issue_path,
    events_enabled_for_events_directory,
    issue_deleted_payload,
    now_timestamp,
    write_events_batch,
    write_events_batch_with_setting,
)
from kanbus.issue_files import (
    delete_issue_file,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.models import IssueData
from kanbus.overlay import overlay_root, replace_overlay_issue_if_present


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
    :param before_issue: Previous issue state restored on event write failure.
        When omitted, a failed persist removes the newly written issue file.
    :type before_issue: Optional[IssueData]
    :param relocate_to: Optional destination path when the issue file should move.
    :type relocate_to: Optional[Path]
    """

    project_dir: Path
    issue_path: Path
    issue: IssueData
    actor_id: str
    events: List[EventRecord]
    before_issue: Optional[IssueData] = None
    relocate_to: Optional[Path] = None


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


class ConcurrentIssueModificationError(RuntimeError):
    """Raised when an issue changed on disk after the caller read it."""


@contextmanager
def _issue_write_lock(project_dir: Path, issue_identifier: str) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    lock_directory = overlay_root(project_dir) / "locks"
    lock_directory.mkdir(parents=True, exist_ok=True)
    with open(lock_directory / f"{issue_identifier}.lock", "a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _refuse_if_issue_changed_since_read(
    issue_path: Path, before_issue: IssueData
) -> None:
    if not issue_path.exists():
        return
    on_disk = read_issue_from_file(issue_path)
    if on_disk.updated_at != before_issue.updated_at:
        raise ConcurrentIssueModificationError(
            f"concurrent modification: {before_issue.identifier} changed since it "
            "was read; retry the command"
        )


def persist_issue_mutation(
    request: PersistIssueMutationRequest,
) -> PersistIssueMutationResult:
    """Persist an issue mutation under an advisory per-issue lock.

    See :func:`_persist_issue_mutation_locked` for the write sequence.
    """
    events_dir = events_dir_for_issue_path(
        request.project_dir, request.relocate_to or request.issue_path
    )
    events_enabled = events_enabled_for_events_directory(events_dir)
    return persist_issue_mutation_with_events_setting(request, events_enabled)


def persist_issue_mutation_with_events_setting(
    request: PersistIssueMutationRequest, events_enabled: bool
) -> PersistIssueMutationResult:
    """Persist an issue mutation using the events setting of a loaded configuration.

    :param request: Mutation request including issue, path, and events.
    :type request: PersistIssueMutationRequest
    :param events_enabled: The ``events`` setting from the loaded configuration.
    :type events_enabled: bool
    :return: Persisted issue and written events.
    :rtype: PersistIssueMutationResult
    """
    with _issue_write_lock(request.project_dir, request.issue.identifier):
        if request.before_issue is not None:
            _refuse_if_issue_changed_since_read(
                request.issue_path, request.before_issue
            )
        return _persist_issue_mutation_locked(request, events_enabled)


def _persist_issue_mutation_locked(
    request: PersistIssueMutationRequest, events_enabled: bool
) -> PersistIssueMutationResult:
    """Persist an issue mutation with updated_at and event history.

    :param request: Mutation request including issue, path, and events.
    :type request: PersistIssueMutationRequest
    :param events_enabled: The ``events`` setting from the loaded configuration.
    :type events_enabled: bool
    :return: Persisted issue and written events.
    :rtype: PersistIssueMutationResult
    :raises RuntimeError: If event writing fails after rollback attempt.
    """
    current_time = datetime.now(timezone.utc)
    persisted_issue = request.issue.model_copy(update={"updated_at": current_time})
    target_path = request.relocate_to or request.issue_path
    write_issue_to_file(persisted_issue, target_path)
    replace_overlay_issue_if_present(request.project_dir, persisted_issue)
    final_issue_path = target_path
    if request.relocate_to is not None:
        delete_issue_file(request.issue_path)
    events_dir = events_dir_for_issue_path(request.project_dir, final_issue_path)
    try:
        write_events_batch_with_setting(events_dir, request.events, events_enabled)
    except Exception as error:  # noqa: BLE001
        if request.relocate_to is not None and final_issue_path.exists():
            write_issue_to_file(persisted_issue, request.issue_path)
            delete_issue_file(final_issue_path)
        if request.before_issue is not None:
            write_issue_to_file(request.before_issue, request.issue_path)
            replace_overlay_issue_if_present(request.project_dir, request.before_issue)
        elif request.issue_path.exists():
            delete_issue_file(request.issue_path)
        raise RuntimeError(str(error)) from error
    return PersistIssueMutationResult(issue=persisted_issue, events=request.events)


def persist_issue_deletion(
    project_dir: Path,
    issue_path: Path,
    issue: IssueData,
    actor_id: str,
    *,
    retain_audit_event: bool = True,
) -> PersistIssueDeletionResult:
    """Delete an issue and optionally retain an issue_deleted audit event.

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
    :return: Deletion result including the audit event when retained.
    :rtype: PersistIssueDeletionResult
    :raises RuntimeError: If event cleanup or audit write fails after rollback.
    """
    occurred_at = now_timestamp()
    deletion_event = create_event(
        issue_id=issue.identifier,
        event_type="issue_deleted",
        actor_id=actor_id,
        payload=issue_deleted_payload(issue),
        occurred_at=occurred_at,
    )
    events_dir = events_dir_for_issue_path(project_dir, issue_path)
    delete_issue_file(issue_path)
    try:
        delete_events_for_issues(events_dir, {issue.identifier})
        if retain_audit_event:
            write_events_batch(events_dir, [deletion_event])
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(issue, issue_path)
        raise RuntimeError(str(error)) from error
    return PersistIssueDeletionResult(
        event=deletion_event if retain_audit_event else None
    )
