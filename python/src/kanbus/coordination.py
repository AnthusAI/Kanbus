"""Git-backed, append-only soft coordination leases.

The event log is the durable source of claim history. This Level 1 reducer is
intentionally soft: concurrent workers can both record claims, then derive the
same winner from the immutable event set.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kanbus.event_history import create_event, write_events_batch
from kanbus.models import CoordinationConfiguration


class CoordinationError(RuntimeError):
    """A coordination operation could not be completed."""


@dataclass(frozen=True)
class LeaseState:
    """Derived current state for one resource."""

    resource: str
    owner: str | None = None
    claim_id: str | None = None
    expires_at: datetime | None = None
    active: bool = False
    event_id: str | None = None
    operation_event_id: str | None = None
    claimed_at: datetime | None = None
    contention_window_ends_at: datetime | None = None
    revision: int | None = None


def parse_duration(value: str) -> int:
    """Parse a positive integer duration expressed in seconds, minutes, or hours.

    :param value: Duration such as ``5s``, ``2m``, or ``1h``.
    :type value: str
    :return: Duration in seconds.
    :rtype: int
    :raises CoordinationError: If the duration is not a positive ``s``/``m``/``h`` value.
    """
    match = re.fullmatch(r"([1-9][0-9]*)([smh])", value)
    if match is None:
        raise CoordinationError(
            "duration must be a positive integer followed by s, m, or h"
        )
    amount = int(match.group(1))
    factor = {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    return amount * factor


def utc_now() -> datetime:
    """Return the current UTC time, exposed for deterministic tests."""
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    """Format a timestamp as millisecond RFC3339 UTC."""
    normalized = value.astimezone(UTC)
    return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """Parse an RFC3339 timestamp and normalize it to UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_coordination_events(events_dir: Path, resource: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not events_dir.is_dir():
        return records
    for path in events_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(record, dict)
            and record.get("issue_id") == resource
            and record.get("event_type")
            in {
                "coordination.claim",
                "coordination.renew",
                "coordination.release",
            }
            and isinstance(record.get("payload"), dict)
        ):
            try:
                record["_occurred_at"] = parse_timestamp(record["occurred_at"])
            except (KeyError, TypeError, ValueError):
                continue
            records.append(record)
    return sorted(
        records,
        key=lambda record: (record["_occurred_at"], str(record.get("event_id", ""))),
    )


def inspect_lease(
    events_dir: Path,
    resource: str,
    *,
    now: datetime | None = None,
    additional_events: list[dict[str, Any]] | None = None,
) -> LeaseState:
    """Reduce immutable coordination events to the current soft lease state.

    Claims inside an epoch's first-claim contention window compete by the
    stable tuple ``(claim_id, owner, event_id)``. Later claims do not displace
    the winner until its lease expires or is released.

    :param events_dir: Directory containing the project's event records.
    :type events_dir: Path
    :param resource: Resource whose history should be reduced.
    :type resource: str
    :param now: Optional evaluation time, primarily used by deterministic tests.
    :type now: Optional[datetime]
    :return: Current active owner or an eligible state.
    :rtype: LeaseState
    """
    evaluation_time = (now or utc_now()).astimezone(UTC)
    events = [
        record
        for record in _merge_coordination_events(
            _load_coordination_events(events_dir, resource),
            additional_events or [],
            resource,
        )
        if record["_occurred_at"] <= evaluation_time
    ]

    candidates: list[dict[str, Any]] = []
    window_ends_at: datetime | None = None
    owner: str | None = None
    claim_id: str | None = None
    selected_event_id: str | None = None
    claimed_at: datetime | None = None
    expires_at: datetime | None = None
    released = False

    def is_active(at: datetime) -> bool:
        return not released and expires_at is not None and expires_at > at

    for event in events:
        occurred_at: datetime = event["_occurred_at"]
        event_type = event["event_type"]
        payload: dict[str, Any] = event["payload"]

        if event_type == "coordination.claim":
            if not candidates or not is_active(occurred_at):
                candidates = [event]
                window = int(payload["contention_window_s"])
                window_ends_at = occurred_at + timedelta(seconds=window)
                expires_at = parse_timestamp(payload["lease_expires_at"])
                owner = str(payload["owner"])
                claim_id = str(payload["claim_id"])
                selected_event_id = str(event.get("event_id", ""))
                claimed_at = occurred_at
                released = False
                continue

            if window_ends_at is not None and occurred_at <= window_ends_at:
                candidates.append(event)
                winner = min(
                    candidates,
                    key=lambda candidate: (
                        str(candidate["payload"]["claim_id"]),
                        str(candidate["payload"]["owner"]),
                        str(candidate.get("event_id", "")),
                    ),
                )
                winner_payload: dict[str, Any] = winner["payload"]
                winner_event_id = str(winner.get("event_id", ""))
                if selected_event_id != winner_event_id:
                    owner = str(winner_payload["owner"])
                    claim_id = str(winner_payload["claim_id"])
                    selected_event_id = winner_event_id
                    claimed_at = winner["_occurred_at"]
                    expires_at = parse_timestamp(winner_payload["lease_expires_at"])
                    released = False
            continue

        if not is_active(occurred_at):
            continue
        if payload.get("owner") != owner or payload.get("claim_id") != claim_id:
            continue
        if event_type == "coordination.renew":
            expires_at = parse_timestamp(payload["lease_expires_at"])
        elif event_type == "coordination.release":
            released = True
            expires_at = occurred_at

    if is_active(evaluation_time):
        return LeaseState(
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            expires_at=expires_at,
            active=True,
            event_id=selected_event_id,
            claimed_at=claimed_at,
            contention_window_ends_at=window_ends_at,
        )
    return LeaseState(resource=resource)


def _record_event(
    events_dir: Path,
    *,
    resource: str,
    event_type: str,
    owner: str,
    claim_id: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> str:
    record = create_event(
        issue_id=resource,
        event_type=event_type,
        actor_id=owner,
        payload={"owner": owner, "claim_id": claim_id, **payload},
        occurred_at=format_timestamp(occurred_at),
    )
    try:
        write_events_batch(events_dir, [record])
    except (OSError, RuntimeError) as error:
        raise CoordinationError(str(error)) from error
    return record.event_id


def _merge_coordination_events(
    durable_events: list[dict[str, Any]],
    additional_events: list[dict[str, Any]],
    resource: str,
) -> list[dict[str, Any]]:
    """Merge derived/speculative coordination events with durable history.

    Durable records take precedence when a gossip event carries the same
    event ID. This lets MQTT provide cross-machine visibility without turning
    speculative messages into Git history.
    """
    by_id = {str(event.get("event_id", "")): event for event in durable_events}
    for source in additional_events:
        if (
            not isinstance(source, dict)
            or source.get("issue_id") != resource
            or source.get("event_type")
            not in {
                "coordination.claim",
                "coordination.renew",
                "coordination.release",
            }
            or not isinstance(source.get("payload"), dict)
        ):
            continue
        event_id = str(source.get("event_id", ""))
        if not event_id or event_id in by_id:
            continue
        try:
            event = dict(source)
            event["_occurred_at"] = parse_timestamp(event["occurred_at"])
        except (KeyError, TypeError, ValueError):
            continue
        by_id[event_id] = event
    return sorted(
        by_id.values(),
        key=lambda event: (event["_occurred_at"], str(event.get("event_id", ""))),
    )


def claim(
    events_dir: Path,
    configuration: CoordinationConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    revision: int = 1,
    now: datetime | None = None,
) -> LeaseState:
    """Append a soft claim and return the derived current owner."""
    _validate_identifiers(resource, owner, claim_id)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise CoordinationError("revision must be a positive integer")
    occurred_at = (now or utc_now()).astimezone(UTC)
    ttl_seconds = parse_duration(configuration.default_lease_ttl)
    operation_event_id = _record_event(
        events_dir,
        resource=resource,
        event_type="coordination.claim",
        owner=owner,
        claim_id=claim_id,
        payload={
            "lease_expires_at": format_timestamp(
                occurred_at + timedelta(seconds=ttl_seconds)
            ),
            "contention_window_s": parse_duration(configuration.contention_window),
            "ttl_s": ttl_seconds,
            "revision": revision,
        },
        occurred_at=occurred_at,
    )
    state = inspect_lease(events_dir, resource, now=occurred_at)
    return replace(state, operation_event_id=operation_event_id)


def renew(
    events_dir: Path,
    configuration: CoordinationConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    extend: str | None = None,
    now: datetime | None = None,
) -> LeaseState:
    """Append a renewal for the current winner, extending its expiry."""
    _validate_identifiers(resource, owner, claim_id)
    occurred_at = (now or utc_now()).astimezone(UTC)
    state = inspect_lease(events_dir, resource, now=occurred_at)
    if not state.active or state.owner != owner or state.claim_id != claim_id:
        raise CoordinationError("lease owner mismatch")
    extension_seconds = parse_duration(
        extend if extend is not None else configuration.default_lease_ttl
    )
    assert state.expires_at is not None
    new_expiry = max(state.expires_at, occurred_at) + timedelta(
        seconds=extension_seconds
    )
    operation_event_id = _record_event(
        events_dir,
        resource=resource,
        event_type="coordination.renew",
        owner=owner,
        claim_id=claim_id,
        payload={"lease_expires_at": format_timestamp(new_expiry)},
        occurred_at=occurred_at,
    )
    renewed_state = inspect_lease(events_dir, resource, now=occurred_at)
    return replace(renewed_state, operation_event_id=operation_event_id)


def release(
    events_dir: Path,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    now: datetime | None = None,
) -> str:
    """Append a release for the current winner."""
    _validate_identifiers(resource, owner, claim_id)
    occurred_at = (now or utc_now()).astimezone(UTC)
    state = inspect_lease(events_dir, resource, now=occurred_at)
    if not state.active or state.owner != owner or state.claim_id != claim_id:
        raise CoordinationError("lease owner mismatch")
    return _record_event(
        events_dir,
        resource=resource,
        event_type="coordination.release",
        owner=owner,
        claim_id=claim_id,
        payload={},
        occurred_at=occurred_at,
    )


def _validate_identifiers(resource: str, owner: str, claim_id: str) -> None:
    if not resource.strip():
        raise CoordinationError("resource must not be empty")
    if not owner.strip():
        raise CoordinationError("owner must not be empty")
    if not claim_id.strip():
        raise CoordinationError("claim id must not be empty")
