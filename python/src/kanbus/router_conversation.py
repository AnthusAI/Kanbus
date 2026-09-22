"""Durable, issue-attached evidence for delegated agent work.

The router result is an optional automation hint.  This module records the
provider conversation independently so a bad result schema can never make a
useful agent turn disappear.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kanbus.issue_router import IssueRouterError, record_router_event


def redact_text(value: str) -> str:
    """Remove common credential-shaped values before recording raw output."""
    import re

    value = re.sub(r"\b(sk-[A-Za-z0-9_-]{12,})\b", "[REDACTED]", value)
    value = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+",
        r"\1[REDACTED]",
        value,
    )
    return value


def record_conversation(
    project_dir: Path,
    package_id: str,
    *,
    action: str,
    provider: str,
    claim_id: str,
    revision: int,
    session_id: str | None = None,
    lifecycle: str | None = None,
    message: str | None = None,
    worktree: str | None = None,
    branch: str | None = None,
    command_summary: str | None = None,
    test_summary: str | None = None,
    log: str | None = None,
    error: str | None = None,
    resumed_session: str | None = None,
) -> str:
    """Append a provider-neutral, redacted conversation event."""
    payload: dict[str, Any] = {
        "action": action,
        "provider": provider,
        "claim_id": claim_id,
        "revision": revision,
    }
    for key, value in {
        "session_id": session_id,
        "lifecycle": lifecycle,
        "message": message,
        "worktree": worktree,
        "branch": branch,
        "command_summary": command_summary,
        "test_summary": test_summary,
        "log": log,
        "error": error,
        "resumed_session": resumed_session,
    }.items():
        if value:
            payload[key] = redact_text(value)
    return record_router_event(
        project_dir,
        package_id=package_id,
        event_type="router_conversation",
        payload=payload,
    )


def codex_session_id(jsonl: str) -> str | None:
    """Find Codex's thread/session identifier from JSONL without assuming one event shape."""
    for line in jsonl.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        for key in ("thread_id", "session_id", "conversation_id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        for container in (item.get("item"), item.get("payload")):
            if isinstance(container, dict):
                for key in ("thread_id", "session_id", "conversation_id"):
                    value = container.get(key)
                    if isinstance(value, str) and value:
                        return value
    return None


def latest_conversation(project_dir: Path, package_id: str) -> dict[str, Any] | None:
    """Return the latest persisted conversation record for one package."""
    events: list[dict[str, Any]] = []
    for path in (project_dir / "events").glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            record.get("issue_id") == f"router:{package_id}"
            and record.get("event_type") == "router.conversation"
            and isinstance(record.get("payload"), dict)
        ):
            events.append(record)
    if not events:
        return None
    return max(
        events, key=lambda item: (item.get("occurred_at", ""), item.get("event_id", ""))
    )


def require_session(project_dir: Path, package_id: str) -> str:
    """Return the saved provider session or a user-facing recovery error."""
    record = latest_conversation(project_dir, package_id)
    session_id = (record or {}).get("payload", {}).get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise IssueRouterError(
            f'no recoverable agent session for package "{package_id}"'
        )
    return session_id
