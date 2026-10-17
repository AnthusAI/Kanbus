"""Issue file input/output helpers."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional, Set, TypeVar

from kanbus.models import IssueData
from kanbus.daemon_client import (
    DaemonClientError,
    is_daemon_enabled,
    request_virtuus,
)
from virtuus import Table

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _issue_table(issues_directory: Path) -> Table:
    """Open canonical issue files through Virtuus."""
    table = Table(
        "issues",
        primary_key="id",
        directory=str(issues_directory),
        validation="warn",
        storage="memory",
        pretty_json=True,
    )
    table.add_gsi("by_status", "status")
    table.add_gsi("by_type", "type")
    table.add_gsi("by_parent", "parent")
    table.add_gsi("by_label", "labels[*]")
    table.add_gsi("blocked_by", "dependencies[dependency_type=blocked-by].target")
    table.load_from_dir()
    return table


def _service_spec(issues_directory: Path) -> dict[str, object]:
    return {
        "name": "issues",
        "primary_key": "id",
        "directory": str(issues_directory),
        "validation": "error",
        "pretty_json": True,
        "reconcile_seconds": 0,
        "indexes": [
            {"name": "by_status", "partition_key": "status"},
            {"name": "by_type", "partition_key": "type"},
            {"name": "by_parent", "partition_key": "parent"},
            {"name": "by_label", "partition_key": "labels[*]"},
            {
                "name": "blocked_by",
                "partition_key": "dependencies[dependency_type=blocked-by].target",
            },
        ],
    }


def _project_root(issues_directory: Path) -> Path:
    """Find the Kanbus root associated with an issue directory."""
    for candidate in (issues_directory, *issues_directory.parents):
        if (candidate / ".kanbus.yml").is_file():
            return candidate
    parent = issues_directory.parent
    if parent.name in {"project", "project-local"}:
        return parent.parent
    return parent


def _use_service(issues_directory: Path) -> bool:
    """Return whether this directory belongs to a daemon-addressable project."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    root = _project_root(issues_directory)
    return is_daemon_enabled() and (root / ".kanbus.yml").is_file()


def _service_request(issues_directory: Path, request: dict[str, object]) -> object:
    """Open the retained table and execute one service operation."""
    root = _project_root(issues_directory)
    opened = request_virtuus(
        root, {"action": "open_table", "spec": _service_spec(issues_directory)}
    )
    if not isinstance(opened, dict) or not isinstance(opened.get("handle"), str):
        raise RuntimeError("Virtuus daemon returned no table handle")
    request["handle"] = opened["handle"]
    return request_virtuus(root, request)


def _service_request_with_fallback(
    issues_directory: Path,
    request: dict[str, object],
    fallback: Callable[[], T],
    from_service: Callable[[object], T],
) -> T:
    """Run one issue operation through the daemon with synchronous fallback.

    The daemon is a just-in-time accelerator and never required for
    correctness: on any daemon failure, fall back to direct storage access
    with only a debug-level log.
    """
    if not _use_service(issues_directory):
        return fallback()
    try:
        return from_service(_service_request(issues_directory, request))
    except (DaemonClientError, RuntimeError) as error:
        logger.debug(
            "Virtuus daemon request failed (%s); falling back to direct storage access",
            error,
        )
        return fallback()


def list_issue_identifiers(issues_directory: Path) -> Set[str]:
    """List issue identifiers based on JSON filenames.

    :param issues_directory: Directory containing issue files.
    :type issues_directory: Path
    :return: Set of issue identifiers.
    :rtype: Set[str]
    """
    if not issues_directory.is_dir():
        return set()
    return _service_request_with_fallback(
        issues_directory,
        {"action": "scan"},
        lambda: {path.stem for path in issues_directory.glob("*.json")},
        lambda records: {
            str(record["id"])
            for record in records
            if isinstance(record, dict) and "id" in record
        },
    )


def read_issue_from_file(issue_path: Path) -> IssueData:
    """Read an issue from a JSON file.

    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    :return: Parsed issue data.
    :rtype: IssueData
    """
    record = _service_request_with_fallback(
        issue_path.parent,
        {"action": "get", "pk": issue_path.stem},
        lambda: _issue_table(issue_path.parent).get(issue_path.stem),
        lambda response: response,
    )
    if record is None:
        raise FileNotFoundError(issue_path)
    return IssueData.model_validate(record)


def read_issues_from_directory(issues_directory: Path) -> list[IssueData]:
    """Load canonical issue files through one Virtuus table scan."""
    if not issues_directory.is_dir():
        return []
    records = _service_request_with_fallback(
        issues_directory,
        {"action": "scan"},
        lambda: _issue_table(issues_directory).scan(),
        lambda response: response,
    )
    _ensure_no_skipped_issue_files(issues_directory, records)
    return sorted(
        (IssueData.model_validate(record) for record in records),
        key=lambda issue: issue.identifier,
    )


def _ensure_no_skipped_issue_files(issues_directory: Path, records: object) -> None:
    """Raise when Virtuus skipped any issue file while loading the table.

    Warn-mode validation silently skips files it cannot parse, which would
    otherwise make listing succeed while ignoring corrupt issue files.
    """
    if not isinstance(records, list):
        return
    loaded = {
        str(record["id"])
        for record in records
        if isinstance(record, dict) and "id" in record
    }
    filenames = {path.stem for path in issues_directory.glob("*.json")}
    missing = sorted(filenames - loaded)
    if missing:
        raise ValueError(f"invalid issue files: {', '.join(missing)}")


PERSISTED_ISSUE_KEYS = frozenset(
    {
        "id",
        "title",
        "description",
        "type",
        "status",
        "priority",
        "assignee",
        "creator",
        "parent",
        "labels",
        "dependencies",
        "comments",
        "created_at",
        "updated_at",
        "closed_at",
        "agent",
        "right_now_summary",
        "right_now_updated_at",
        "custom",
    }
)


def _without_empty_agent_fields(agent: Optional[dict]) -> Optional[dict]:
    if not agent:
        return None
    return {
        key: value
        for key, value in agent.items()
        if not (key == "settings" and not value) and value is not None
    }


def _persisted_issue_record(issue: IssueData, issue_path: Path) -> dict:
    """Build the JSON record with the same keys the Rust CLI persists."""
    record = issue.model_dump(by_alias=True, mode="json")
    record.pop("agent_assignment", None)
    agent = _without_empty_agent_fields(record.get("agent"))
    if agent is None:
        record.pop("agent", None)
    else:
        record["agent"] = agent
    persisted_comments = []
    for comment in record.get("comments", []):
        persisted = {
            key: value
            for key, value in comment.items()
            if value is not None and key not in ("data", "agent")
        }
        if comment.get("data"):
            persisted["data"] = comment["data"]
        comment_agent = _without_empty_agent_fields(comment.get("agent"))
        if comment_agent is not None:
            persisted["agent"] = comment_agent
        persisted_comments.append(persisted)
    record["comments"] = persisted_comments
    try:
        existing = json.loads(issue_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = None
    if isinstance(existing, dict):
        for key, value in existing.items():
            if key not in PERSISTED_ISSUE_KEYS:
                record.setdefault(key, value)
        _restore_full_precision_timestamps(record, existing)
    return record


def _microsecond_prefix(timestamp: object) -> Optional[str]:
    if not isinstance(timestamp, str):
        return None
    seconds, _, fraction = timestamp.partition(".")
    digits = "".join(character for character in fraction if character.isdigit())
    return f"{seconds.rstrip('Z')}.{digits[:6].ljust(6, '0')}"


def _restore_full_precision_timestamps(record: dict, existing: dict) -> None:
    """Keep nanosecond timestamps Python's datetime cannot represent."""
    for key in ("created_at", "updated_at", "closed_at", "right_now_updated_at"):
        previous = existing.get(key)
        if (
            isinstance(previous, str)
            and _microsecond_prefix(previous) == _microsecond_prefix(record.get(key))
            and _microsecond_prefix(previous) is not None
        ):
            record[key] = previous
    existing_comments = {
        comment.get("id"): comment
        for comment in existing.get("comments", [])
        if isinstance(comment, dict) and comment.get("id")
    }
    for comment in record.get("comments", []):
        previous = existing_comments.get(comment.get("id"), {}).get("created_at")
        if (
            isinstance(previous, str)
            and _microsecond_prefix(previous) is not None
            and _microsecond_prefix(previous) == _microsecond_prefix(comment.get("created_at"))
        ):
            comment["created_at"] = previous


def write_issue_to_file(issue: IssueData, issue_path: Path) -> None:
    """Write an issue to a JSON file with pretty formatting.

    :param issue: Issue data to serialize.
    :type issue: IssueData
    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    """
    if issue_path.is_dir():
        raise IsADirectoryError(issue_path)
    record = _persisted_issue_record(issue, issue_path)

    def _write_directly() -> None:
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        _issue_table(issue_path.parent).put(record)

    _service_request_with_fallback(
        issue_path.parent,
        {"action": "put", "record": record},
        _write_directly,
        lambda response: None,
    )


def delete_issue_file(issue_path: Path) -> None:
    """Delete an issue through the resident Virtuus table when available."""
    _service_request_with_fallback(
        issue_path.parent,
        {"action": "delete", "pk": issue_path.stem},
        lambda: (
            _issue_table(issue_path.parent).delete(issue_path.stem)
            if issue_path.exists()
            else None
        ),
        lambda response: None,
    )
