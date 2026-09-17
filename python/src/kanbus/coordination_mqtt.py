"""Best-effort MQTT visibility for Git-backed soft coordination leases."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from kanbus import coordination, gossip
from kanbus.gossip import CoordinationGossipEnvelope
from kanbus.models import ProjectConfiguration

DEDUPE_TTL_S = gossip.GOSSIP_DEDUPE_TTL_S


def should_ignore_envelope(
    envelope: CoordinationGossipEnvelope,
    dedupe: gossip.DedupeSet,
    current_producer_id: str,
) -> bool:
    """Apply envelope-ID dedupe and same-process echo suppression."""
    if dedupe.seen(envelope.id):
        return True
    return envelope.producer_id == current_producer_id


def provider_available(root: Path, configuration: ProjectConfiguration) -> bool:
    """Return whether the configured MQTT broker can be used without starting it.

    MQTT is optional for coordination. This check deliberately avoids broker
    autostart so normal Kanbus commands fall back to Git when no shared broker
    is already running.
    """
    realtime = configuration.realtime
    if "mqtt" not in configuration.coordination.providers:
        return False
    if realtime.transport not in {"auto", "mqtt"} or realtime.broker == "off":
        return False
    if realtime.transport == "auto" and gossip._uds_socket_path(realtime).exists():
        return False
    try:
        import paho.mqtt.client  # noqa: F401

        endpoint = gossip.mqtt_endpoint_for_realtime(
            gossip.resolve_broker_endpoint(realtime.broker), realtime
        )
        return gossip.broker_is_reachable(endpoint)
    except (ImportError, OSError, ValueError, gossip.GossipError):
        return False


def topic_for_project(
    root: Path, project_dir: Path, configuration: ProjectConfiguration
) -> str:
    """Resolve the configured project event topic for coordination gossip."""
    project_label = gossip._resolve_project_label(root, project_dir, configuration)
    if project_label is None:
        project_label = configuration.project_key
    return configuration.realtime.topics.project_events.format(project=project_label)


def make_claim_envelope(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    lease_ttl_s: int,
    occurred_at: datetime,
) -> CoordinationGossipEnvelope:
    """Build a CLAIM envelope linked to its durable Git event."""
    return _make_envelope(
        root,
        project_dir,
        configuration,
        event_type="coordination.claim",
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=event_id,
        occurred_at=occurred_at,
        lease_ttl_s=lease_ttl_s,
    )


def make_lease_envelope(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    lease_ttl_s: int,
    expires_at: datetime,
    occurred_at: datetime,
) -> CoordinationGossipEnvelope:
    """Build a LEASE envelope for the selected durable claim event."""
    return _make_envelope(
        root,
        project_dir,
        configuration,
        event_type="coordination.lease",
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=event_id,
        occurred_at=occurred_at,
        lease_ttl_s=lease_ttl_s,
        expires_at=coordination.format_timestamp(expires_at),
    )


def make_release_envelope(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    occurred_at: datetime,
) -> CoordinationGossipEnvelope:
    """Build a RELEASE envelope linked to its durable Git event."""
    return _make_envelope(
        root,
        project_dir,
        configuration,
        event_type="coordination.release",
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=event_id,
        occurred_at=occurred_at,
    )


def _make_envelope(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    event_type: str,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    occurred_at: datetime,
    lease_ttl_s: int | None = None,
    expires_at: str | None = None,
) -> CoordinationGossipEnvelope:
    project_label = gossip._resolve_project_label(root, project_dir, configuration)
    if project_label is None:
        project_label = configuration.project_key
    values: dict[str, Any] = {
        "id": str(uuid4()),
        "ts": coordination.format_timestamp(occurred_at),
        "project": project_label,
        "type": event_type,
        "event_id": event_id,
        "producer_id": gossip.producer_id(),
        "resource": resource,
        "owner": owner,
        "claim_id": claim_id,
    }
    if lease_ttl_s is not None:
        values["lease_ttl_s"] = lease_ttl_s
    if expires_at is not None:
        values["expires_at"] = expires_at
    return CoordinationGossipEnvelope(**values)


def publish_envelope(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    envelope: CoordinationGossipEnvelope,
) -> bool:
    """Publish a coordination envelope to the already-running MQTT broker."""
    if not provider_available(root, configuration):
        return False
    endpoint = gossip.resolve_broker_endpoint(configuration.realtime.broker)
    topic = topic_for_project(root, project_dir, configuration)
    try:
        realtime = configuration.realtime
        if gossip._has_mqtt_custom_authorizer(realtime):
            gossip._publish_mqtt(endpoint, topic, envelope, realtime)
        else:
            gossip._publish_mqtt(endpoint, topic, envelope)
    except Exception:  # noqa: BLE001
        return False
    record_envelope(project_dir, envelope, ttl_s=configuration.overlay.ttl_s)
    return True


def record_envelope(
    project_dir: Path,
    envelope: CoordinationGossipEnvelope,
    *,
    ttl_s: int = 86400,
) -> None:
    """Persist a received MQTT event in the ignored speculative overlay."""
    directory = _resource_overlay_dir(project_dir, envelope.resource or "")
    directory.mkdir(parents=True, exist_ok=True)
    digest = _sha256_hex(envelope.id)
    path = directory / f"{digest}.json"
    if not path.exists():
        payload = envelope.model_dump(by_alias=True, mode="json", exclude_none=True)
        temporary_path = directory / f".{digest}.{uuid4()}.tmp"
        temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary_path.replace(path)
    _prune_overlay(directory, ttl_s)


def overlay_events(
    project_dir: Path,
    resource: str,
    *,
    contention_window_s: int,
    now: datetime | None = None,
    ttl_s: int = 86400,
) -> list[dict[str, Any]]:
    """Convert cached CLAIM/LEASE/RELEASE envelopes to reducer events."""
    overlay_directory = _overlay_dir(project_dir)
    if not overlay_directory.is_dir():
        return []
    evaluation_time = (now or coordination.utc_now()).astimezone(UTC)
    _prune_overlay(overlay_directory, ttl_s, now=evaluation_time)
    directory = _resource_overlay_dir(project_dir, resource)
    if not directory.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            envelope = CoordinationGossipEnvelope.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            occurred_at = coordination.parse_timestamp(envelope.ts)
        except (OSError, ValueError):
            continue
        if envelope.resource != resource or not _is_canonical_overlay_path(
            path, envelope
        ):
            continue
        if occurred_at > evaluation_time:
            continue
        payload: dict[str, Any] = {
            "owner": envelope.owner,
            "claim_id": envelope.claim_id,
        }
        event_id = envelope.event_id or ""
        event_type = envelope.type
        if event_type == "coordination.claim":
            assert envelope.lease_ttl_s is not None
            payload.update(
                {
                    "lease_expires_at": coordination.format_timestamp(
                        occurred_at + timedelta(seconds=envelope.lease_ttl_s)
                    ),
                    "contention_window_s": contention_window_s,
                    "ttl_s": envelope.lease_ttl_s,
                }
            )
        elif event_type == "coordination.lease":
            assert envelope.expires_at is not None
            # LEASE uses the winning CLAIM's event_id by protocol, so use the
            # unique envelope id for the reducer's speculative renewal record.
            event_id = f"mqtt-{envelope.id}"
            event_type = "coordination.renew"
            payload["lease_expires_at"] = envelope.expires_at
        result.append(
            {
                "event_id": event_id,
                "issue_id": resource,
                "event_type": event_type,
                "occurred_at": coordination.format_timestamp(occurred_at),
                "actor_id": envelope.owner,
                "payload": payload,
            }
        )
    return result


def inspect_lease(
    events_dir: Path,
    project_dir: Path,
    resource: str,
    configuration: ProjectConfiguration,
    *,
    now: datetime | None = None,
) -> coordination.LeaseState:
    """Inspect durable Git history merged with speculative MQTT visibility."""
    window_s = coordination.parse_duration(configuration.coordination.contention_window)
    return coordination.inspect_lease(
        events_dir,
        resource,
        now=now,
        additional_events=overlay_events(
            project_dir,
            resource,
            contention_window_s=window_s,
            now=now,
            ttl_s=configuration.overlay.ttl_s,
        ),
    )


def reconcile_lease(
    root: Path,
    project_dir: Path,
    events_dir: Path,
    resource: str,
    configuration: ProjectConfiguration,
    *,
    now: datetime | None = None,
) -> tuple[coordination.LeaseState, bool]:
    """Publish one deterministic LEASE after a contention window closes.

    The return flag indicates whether MQTT remains the selected provider. The
    message can be emitted again by another receiver; all equivalent LEASEs
    identify the same winning durable claim event.
    """
    evaluation_time = (now or coordination.utc_now()).astimezone(UTC)
    state, envelope = select_lease_envelope(
        root,
        project_dir,
        events_dir,
        resource,
        configuration,
        now=evaluation_time,
    )
    if envelope is None:
        return state, True
    return state, publish_envelope(root, project_dir, configuration, envelope)


def select_lease_envelope(
    root: Path,
    project_dir: Path,
    events_dir: Path,
    resource: str,
    configuration: ProjectConfiguration,
    *,
    now: datetime | None = None,
) -> tuple[coordination.LeaseState, CoordinationGossipEnvelope | None]:
    """Select a LEASE message once the resource's contention window is closed."""
    evaluation_time = (now or coordination.utc_now()).astimezone(UTC)
    state = inspect_lease(
        events_dir,
        project_dir,
        resource,
        configuration,
        now=evaluation_time,
    )
    if (
        not state.active
        or state.owner is None
        or state.claim_id is None
        or state.event_id is None
        or state.claimed_at is None
        or state.contention_window_ends_at is None
        or state.expires_at is None
    ):
        return state, None
    if evaluation_time < state.contention_window_ends_at:
        return state, None
    if any(
        envelope.type == "coordination.lease"
        and envelope.resource == resource
        and envelope.event_id == state.event_id
        and envelope.expires_at == coordination.format_timestamp(state.expires_at)
        for envelope in load_envelopes(
            project_dir, ttl_s=configuration.overlay.ttl_s, now=evaluation_time
        )
    ):
        return state, None
    ttl_s = max(1, int((state.expires_at - state.claimed_at).total_seconds()))
    envelope = make_lease_envelope(
        root,
        project_dir,
        configuration,
        resource=resource,
        owner=state.owner,
        claim_id=state.claim_id,
        event_id=state.event_id,
        lease_ttl_s=ttl_s,
        expires_at=state.expires_at,
        occurred_at=evaluation_time,
    )
    return state, envelope


def load_envelopes(
    project_dir: Path,
    *,
    ttl_s: int = 86400,
    now: datetime | None = None,
) -> list[CoordinationGossipEnvelope]:
    """Load valid coordination gossip envelopes from the local overlay."""
    directory = _overlay_dir(project_dir)
    if not directory.is_dir():
        return []
    evaluation_time = (now or coordination.utc_now()).astimezone(UTC)
    _prune_overlay(directory, ttl_s, now=evaluation_time)
    envelopes = []
    seen: set[str] = set()
    for path in sorted(directory.rglob("*.json")):
        try:
            envelope = CoordinationGossipEnvelope.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            coordination.parse_timestamp(envelope.ts)
        except (OSError, ValueError):
            continue
        if not _is_canonical_overlay_path(path, envelope):
            continue
        if envelope.id in seen:
            continue
        seen.add(envelope.id)
        envelopes.append(envelope)
    return envelopes


def _overlay_dir(project_dir: Path) -> Path:
    return project_dir / ".overlay" / "coordination"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resource_overlay_dir(project_dir: Path, resource: str) -> Path:
    return _overlay_dir(project_dir) / _sha256_hex(resource)


def _is_canonical_overlay_path(
    path: Path, envelope: CoordinationGossipEnvelope
) -> bool:
    return (
        path.parent.name == _sha256_hex(envelope.resource or "")
        and path.name == f"{_sha256_hex(envelope.id)}.json"
    )


def _active_lease_expires_at(
    envelope: CoordinationGossipEnvelope,
) -> datetime | None:
    occurred_at = coordination.parse_timestamp(envelope.ts)
    if envelope.type == "coordination.claim":
        assert envelope.lease_ttl_s is not None
        return occurred_at + timedelta(seconds=envelope.lease_ttl_s)
    if envelope.type == "coordination.lease":
        assert envelope.expires_at is not None
        return coordination.parse_timestamp(envelope.expires_at)
    return None


def _prune_overlay(directory: Path, ttl_s: int, *, now: datetime | None = None) -> None:
    evaluation_time = (now or coordination.utc_now()).astimezone(UTC)
    cutoff = evaluation_time - timedelta(seconds=ttl_s)
    for path in directory.rglob("*.json"):
        try:
            envelope = CoordinationGossipEnvelope.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            occurred_at = coordination.parse_timestamp(envelope.ts)
            lease_expires_at = _active_lease_expires_at(envelope)
            if not _is_canonical_overlay_path(path, envelope):
                continue
            if lease_expires_at is not None and lease_expires_at > evaluation_time:
                continue
            if occurred_at < cutoff:
                path.unlink(missing_ok=True)
        except (OSError, ValueError):
            continue
