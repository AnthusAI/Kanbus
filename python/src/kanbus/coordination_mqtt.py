"""Best-effort MQTT visibility for Git-backed soft coordination leases."""

from __future__ import annotations

import hashlib
import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from kanbus import coordination, gossip
from kanbus.gossip import CoordinationGossipEnvelope
from kanbus.models import ProjectConfiguration

DEDUPE_TTL_S = gossip.GOSSIP_DEDUPE_TTL_S
OBSERVATION_TTL_S = 86400
_TRANSPORT_DIAGNOSTICS_LOCK = threading.Lock()
_TRANSPORT_DIAGNOSTICS: dict[str, dict[str, Any]] = {
    "listener": {},
    "publisher": {},
}


def transport_diagnostics() -> dict[str, dict[str, Any]]:
    """Return non-secret diagnostics for the current process's MQTT path."""
    with _TRANSPORT_DIAGNOSTICS_LOCK:
        return json.loads(json.dumps(_TRANSPORT_DIAGNOSTICS))


def _update_transport_diagnostics(channel: str, **values: Any) -> None:
    with _TRANSPORT_DIAGNOSTICS_LOCK:
        _TRANSPORT_DIAGNOSTICS[channel].update(values)


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
        _update_transport_diagnostics("listener", provider_status="not_configured")
        return False
    if realtime.transport not in {"auto", "mqtt"} or realtime.broker == "off":
        _update_transport_diagnostics("listener", provider_status="disabled")
        return False
    if realtime.transport == "auto" and gossip._uds_socket_path(realtime).exists():
        _update_transport_diagnostics("listener", provider_status="local_uds_selected")
        return False
    try:
        import paho.mqtt.client  # noqa: F401

        endpoint = gossip.mqtt_endpoint_for_realtime(
            gossip.resolve_broker_endpoint(realtime.broker), realtime
        )
        reachable = gossip.broker_is_reachable(endpoint)
        _update_transport_diagnostics(
            "listener",
            provider_status="tcp_reachable" if reachable else "tcp_unreachable",
            broker_scheme=endpoint.scheme,
            broker_host=endpoint.host,
            broker_port=endpoint.port,
            custom_authorizer_configured=gossip._has_mqtt_custom_authorizer(realtime),
        )
        return reachable
    except ImportError:
        _update_transport_diagnostics("listener", provider_status="paho_unavailable")
        return False
    except (OSError, ValueError, gossip.GossipError) as error:
        _update_transport_diagnostics(
            "listener",
            provider_status="endpoint_unavailable",
            provider_error_type=type(error).__name__,
        )
        return False


class CoordinationMqttListener:
    """Lifecycle wrapper for a project-scoped coordination MQTT subscription."""

    def __init__(
        self,
        client: Any,
        connected: threading.Event,
        subscribed: threading.Event,
        received: threading.Event,
    ) -> None:
        self._client = client
        self.connected = connected
        self.subscribed = subscribed
        self.received = received

    def stop(self) -> None:
        """Stop the background MQTT network loop and disconnect cleanly."""
        _update_transport_diagnostics("listener", status="stopping")
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()
            _update_transport_diagnostics("listener", status="stopped")


def start_listener(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
) -> CoordinationMqttListener | None:
    """Subscribe to soft-lease envelopes and persist peers in the local overlay."""
    if not provider_available(root, configuration):
        return None
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return None
    realtime = configuration.realtime
    endpoint = gossip.mqtt_endpoint_for_realtime(
        gossip.resolve_broker_endpoint(realtime.broker), realtime
    )
    # Keep the transport identity unique per socket. The stable envelope
    # producer_id is not a broker client ID and must never evict this listener
    # when the same process opens a short-lived publisher connection.
    client_id = str(uuid4())
    client = mqtt.Client(client_id=client_id)
    if endpoint.scheme == "mqtts":
        if gossip._has_mqtt_custom_authorizer(realtime):
            tls_context = ssl.create_default_context()
            tls_context.set_alpn_protocols(["mqtt"])
            client.tls_set_context(tls_context)
        else:
            client.tls_set()
    if gossip._has_mqtt_custom_authorizer(realtime):
        client.username_pw_set(
            f"?x-amz-customauthorizer-name={realtime.mqtt_custom_authorizer_name}",
            realtime.mqtt_api_token,
        )
    connected = threading.Event()
    subscribed = threading.Event()
    received = threading.Event()
    topic = topic_for_project(root, project_dir, configuration)
    _update_transport_diagnostics(
        "listener",
        status="connecting",
        client_id=client_id,
        broker_scheme=endpoint.scheme,
        broker_host=endpoint.host,
        broker_port=endpoint.port,
        topic=topic,
        custom_authorizer_configured=gossip._has_mqtt_custom_authorizer(realtime),
        connect_reason_code=None,
        subscribed=False,
        suback_reason_codes=None,
        peer_messages=0,
        rejected_messages=0,
    )
    project_label = gossip._resolve_project_label(root, project_dir, configuration)
    if project_label is None:
        project_label = configuration.project_key

    def on_connect(connected_client, _userdata, _flags, reason_code, *_extra):
        code = gossip._mqtt_reason_value(reason_code)
        _update_transport_diagnostics(
            "listener",
            connect_reason_code=code,
            connected=code == 0,
            status="connected" if code == 0 else "connect_rejected",
        )
        if code != 0:
            return
        subscribe_result = connected_client.subscribe(topic, qos=0)
        if isinstance(subscribe_result, tuple) and subscribe_result:
            rc = subscribe_result[0]
            _update_transport_diagnostics("listener", subscribe_rc=rc)
            if rc != mqtt.MQTT_ERR_SUCCESS:
                _update_transport_diagnostics(
                    "listener", status="subscribe_request_rejected"
                )
        connected.set()

    def on_subscribe(_client, _userdata, mid, reason_codes, *_extra):
        try:
            codes = list(reason_codes or [])
        except TypeError:
            codes = []
        safe_codes = [gossip._mqtt_reason_value(value) for value in codes]
        accepted = _subscription_succeeded(reason_codes)
        _update_transport_diagnostics(
            "listener",
            suback_mid=mid,
            suback_reason_codes=safe_codes,
            subscribed=accepted,
            status="subscribed" if accepted else "suback_rejected",
        )
        if accepted:
            subscribed.set()

    def on_message(_client, _userdata, message):
        try:
            envelope = CoordinationGossipEnvelope.model_validate_json(message.payload)
        except (TypeError, ValueError):
            state = transport_diagnostics()["listener"]
            _update_transport_diagnostics(
                "listener",
                rejected_messages=int(state.get("rejected_messages", 0)) + 1,
            )
            return
        if envelope.project != project_label:
            state = transport_diagnostics()["listener"]
            _update_transport_diagnostics(
                "listener",
                rejected_messages=int(state.get("rejected_messages", 0)) + 1,
            )
            return
        if envelope.producer_id == gossip.producer_id():
            return
        record_envelope(project_dir, envelope, ttl_s=configuration.overlay.ttl_s)
        state = transport_diagnostics()["listener"]
        _update_transport_diagnostics(
            "listener",
            peer_messages=int(state.get("peer_messages", 0)) + 1,
            last_peer_message_type=envelope.type,
            last_peer_resource=envelope.resource,
        )
        received.set()

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    try:
        client.connect(endpoint.host, endpoint.port, 30)
        client.loop_start()
    except (OSError, ValueError) as error:
        _update_transport_diagnostics(
            "listener", status="connect_failed", error_type=type(error).__name__
        )
        return None
    return CoordinationMqttListener(client, connected, subscribed, received)


def _subscription_succeeded(reason_codes: Any) -> bool:
    """Return whether every requested MQTT subscription was granted.

    :param reason_codes: MQTT 3 granted QoS values or MQTT 5 reason codes.
    :type reason_codes: Any
    :return: Whether at least one subscription was granted without failure.
    :rtype: bool
    """
    if reason_codes is None:
        return False
    try:
        values = list(reason_codes)
    except TypeError:
        return False
    if not values:
        return False
    for reason_code in values:
        is_failure = getattr(reason_code, "is_failure", None)
        if isinstance(is_failure, bool):
            if is_failure:
                return False
            continue
        value = getattr(reason_code, "value", reason_code)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value
            not in {
                0,
                1,
                2,
            }
        ):
            return False
    return True


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
    operation_sequence: int | None = None,
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
        operation_sequence=operation_sequence,
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
    operation_sequence: int | None = None,
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
        operation_sequence=operation_sequence,
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
    operation_sequence: int | None = None,
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
        operation_sequence=operation_sequence,
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
    operation_sequence: int | None = None,
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
    if operation_sequence is not None:
        values["operation_sequence"] = operation_sequence
    return CoordinationGossipEnvelope(**values)


def publish_envelope(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    envelope: CoordinationGossipEnvelope,
) -> bool:
    """Publish a coordination envelope to the already-running MQTT broker."""
    if not provider_available(root, configuration):
        _update_transport_diagnostics("publisher", status="provider_unavailable")
        return False
    endpoint = gossip.mqtt_endpoint_for_realtime(
        gossip.resolve_broker_endpoint(configuration.realtime.broker),
        configuration.realtime,
    )
    topic = topic_for_project(root, project_dir, configuration)
    try:
        realtime = configuration.realtime
        if gossip._has_mqtt_custom_authorizer(realtime):
            publish_result = gossip._publish_mqtt(endpoint, topic, envelope, realtime)
        else:
            publish_result = gossip._publish_mqtt(endpoint, topic, envelope)
    except Exception as error:  # noqa: BLE001
        diagnostics = getattr(error, "diagnostics", None)
        if not isinstance(diagnostics, dict):
            diagnostics = {"status": "failed", "error_type": type(error).__name__}
        _update_transport_diagnostics("publisher", **diagnostics)
        return False
    if isinstance(publish_result, dict):
        _update_transport_diagnostics("publisher", **publish_result)
    else:
        _update_transport_diagnostics(
            "publisher",
            status="published",
            topic=topic,
            broker_scheme=endpoint.scheme,
            broker_host=endpoint.host,
            broker_port=endpoint.port,
            custom_authorizer_configured=gossip._has_mqtt_custom_authorizer(
                configuration.realtime
            ),
            qos=0,
            retain=False,
        )
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
        if envelope.operation_sequence is not None:
            payload["operation_sequence"] = envelope.operation_sequence
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


def record_contention_observation(
    project_dir: Path,
    resource: str,
    claim_id: str,
    *,
    contention_window_s: int,
    ttl_s: int = OBSERVATION_TTL_S,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist the claims visible to this worker at contention close.

    The snapshot is local, ignored router telemetry for integration auditing.
    It lets the live harness distinguish actual arbitration-time observation
    from envelopes that arrived only after the claim decision.

    :param project_dir: Project directory that owns the coordination overlay.
    :type project_dir: Path
    :param resource: Resource whose contention window just closed.
    :type resource: str
    :param claim_id: This worker's attempted claim identifier.
    :type claim_id: str
    :param contention_window_s: Configured contention window in seconds.
    :type contention_window_s: int
    :param now: Optional deterministic observation time.
    :type now: datetime | None
    :return: The persisted observation record.
    :rtype: dict[str, Any]
    """
    observed_at = (now or coordination.utc_now()).astimezone(UTC)
    peer_claim_ids = sorted(
        {
            str(event.get("payload", {}).get("claim_id", ""))
            for event in overlay_events(
                project_dir,
                resource,
                contention_window_s=contention_window_s,
                now=observed_at,
                ttl_s=ttl_s,
            )
            if event.get("event_type") == "coordination.claim"
            and event.get("payload", {}).get("claim_id")
            and event.get("payload", {}).get("claim_id") != claim_id
        }
    )
    record = {
        "schema_version": 1,
        "resource": resource,
        "claim_id": claim_id,
        "local_claim_id": claim_id,
        "observed_claim_ids": sorted({claim_id, *peer_claim_ids}),
        "peer_claim_ids": peer_claim_ids,
        "observed_at": coordination.format_timestamp(observed_at),
        "mqtt_transport": transport_diagnostics(),
    }
    directory = (
        project_dir / ".overlay" / "coordination-observations" / _sha256_hex(resource)
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_sha256_hex(claim_id)}.json"
    temporary_path = directory / f".{path.name}.{uuid4()}.tmp"
    temporary_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temporary_path.replace(path)
    _prune_contention_observations(directory, ttl_s=ttl_s, now=observed_at)
    return record


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
        operation_sequence=state.operation_sequence,
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


def _prune_contention_observations(
    directory: Path, *, ttl_s: int, now: datetime | None = None
) -> None:
    """Remove stale local arbitration snapshots after the overlay TTL."""
    evaluation_time = (now or coordination.utc_now()).astimezone(UTC)
    cutoff = evaluation_time - timedelta(seconds=ttl_s)
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            observed_at = coordination.parse_timestamp(record["observed_at"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if observed_at < cutoff:
            path.unlink(missing_ok=True)
