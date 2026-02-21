"""Event history recording and retrieval helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from kanbus.models import IssueData

EVENT_SCHEMA_VERSION = 1


class EventRecord(BaseModel):
    """Event history record for a single issue action."""

    schema_version: int = Field(default=EVENT_SCHEMA_VERSION)
    event_id: str
    issue_id: str
    event_type: str
    occurred_at: str
    actor_id: str
    payload: Dict[str, Any]


def now_timestamp() -> str:
    """Return the current UTC timestamp formatted for filenames."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def event_filename(occurred_at: str, event_id: str) -> str:
    return f"{occurred_at}__{event_id}.json"


def create_event(
    issue_id: str,
    event_type: str,
    actor_id: str,
    payload: Dict[str, Any],
    occurred_at: Optional[str] = None,
) -> EventRecord:
    timestamp = occurred_at or now_timestamp()
    return EventRecord(
        event_id=str(uuid4()),
        issue_id=issue_id,
        event_type=event_type,
        occurred_at=timestamp,
        actor_id=actor_id,
        payload=payload,
    )


def events_dir_for_project(project_dir: Path) -> Path:
    return project_dir / "events"


def events_dir_for_local(project_dir: Path) -> Path:
    parent = project_dir.parent
    if parent is None:
        raise RuntimeError("project-local path unavailable")
    return parent / "project-local" / "events"


def events_dir_for_issue_path(project_dir: Path, issue_path: Path) -> Path:
    local_dir = project_dir.parent / "project-local"
    if local_dir.is_dir() and issue_path.is_relative_to(local_dir):
        return local_dir / "events"
    return events_dir_for_project(project_dir)


def events_dir_for_issue(project_dir: Path, issue_id: str) -> Path:
    local_dir = project_dir.parent / "project-local"
    if local_dir.is_dir():
        local_issue = local_dir / "issues" / f"{issue_id}.json"
        if local_issue.exists():
            return local_dir / "events"
    return events_dir_for_project(project_dir)


def write_events_batch(events_dir: Path, events: Iterable[EventRecord]) -> List[Path]:
    events_list = list(events)
    if not events_list:
        return []
    events_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for event in events_list:
        filename = event_filename(event.occurred_at, event.event_id)
        final_path = events_dir / filename
        temp_path = events_dir / f".{filename}.tmp"
        try:
            with temp_path.open("x", encoding="utf-8") as handle:
                handle.write(event.model_dump_json(indent=2))
                handle.flush()
            temp_path.replace(final_path)
            written.append(final_path)
        except Exception as error:  # noqa: BLE001
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            rollback_event_files(written)
            raise RuntimeError(str(error)) from error
    return written


def rollback_event_files(paths: Iterable[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def issue_created_payload(issue: IssueData) -> Dict[str, Any]:
    return {
        "title": issue.title,
        "description": issue.description,
        "issue_type": issue.issue_type,
        "status": issue.status,
        "priority": issue.priority,
        "assignee": issue.assignee,
        "parent": issue.parent,
        "labels": issue.labels,
    }


def issue_deleted_payload(issue: IssueData) -> Dict[str, Any]:
    return {
        "title": issue.title,
        "issue_type": issue.issue_type,
        "status": issue.status,
    }


def state_transition_payload(from_status: str, to_status: str) -> Dict[str, Any]:
    return {"from_status": from_status, "to_status": to_status}


def comment_payload(comment_id: str, comment_author: str) -> Dict[str, Any]:
    return {"comment_id": comment_id, "comment_author": comment_author}


def comment_updated_payload(comment_id: str, comment_author: str) -> Dict[str, Any]:
    return {
        "comment_id": comment_id,
        "comment_author": comment_author,
        "changed_fields": ["text"],
    }


def dependency_payload(dependency_type: str, target_id: str) -> Dict[str, Any]:
    return {"dependency_type": dependency_type, "target_id": target_id}


def transfer_payload(from_location: str, to_location: str) -> Dict[str, Any]:
    return {"from_location": from_location, "to_location": to_location}


def field_update_payload(
    before: IssueData, after: IssueData
) -> Optional[Dict[str, Any]]:
    changes: Dict[str, Dict[str, Any]] = {}

    def push(field: str, from_value: Any, to_value: Any) -> None:
        if from_value == to_value:
            return
        changes[field] = {"from": from_value, "to": to_value}

    push("title", before.title, after.title)
    push("description", before.description, after.description)
    push("assignee", before.assignee, after.assignee)
    push("priority", before.priority, after.priority)
    push("labels", before.labels, after.labels)
    push("parent", before.parent, after.parent)

    if not changes:
        return None
    return {"changes": changes}


def build_update_events(
    before: IssueData, after: IssueData, actor_id: str, occurred_at: str
) -> List[EventRecord]:
    events: List[EventRecord] = []
    if before.status != after.status:
        events.append(
            create_event(
                issue_id=after.identifier,
                event_type="state_transition",
                actor_id=actor_id,
                payload=state_transition_payload(before.status, after.status),
                occurred_at=occurred_at,
            )
        )
    payload = field_update_payload(before, after)
    if payload is not None:
        events.append(
            create_event(
                issue_id=after.identifier,
                event_type="field_updated",
                actor_id=actor_id,
                payload=payload,
                occurred_at=occurred_at,
            )
        )
    return events
