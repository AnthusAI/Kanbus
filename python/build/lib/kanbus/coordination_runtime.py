"""Shared soft-coordination provider selection and MQTT dispatch helpers."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from time import monotonic

from kanbus import coordination_mqtt
from kanbus.coordination import LeaseState
from kanbus.models import ProjectConfiguration


def select_soft_provider(root: Path, configuration: ProjectConfiguration) -> str:
    """Select MQTT when reachable, otherwise use durable Git coordination."""
    return (
        "mqtt"
        if "mqtt" in configuration.coordination.providers
        and coordination_mqtt.provider_available(root, configuration)
        else "git"
    )


def start_soft_listener(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    ready_timeout: float | None = None,
):
    """Start MQTT ingestion so peer leases enter the same local overlay reducer."""
    if select_soft_provider(root, configuration) != "mqtt":
        _emit_mqtt_diagnostics_if_requested()
        return None
    if ready_timeout is None:
        # AWS custom-authorizer TLS handshakes are slower than a local broker,
        # but setup remains bounded and happens before the contention window.
        ready_timeout = (
            5.0
            if coordination_mqtt.gossip._has_mqtt_custom_authorizer(
                configuration.realtime
            )
            else 2.0
        )
    listener = coordination_mqtt.start_listener(root, project_dir, configuration)
    if listener is None:
        _emit_mqtt_diagnostics_if_requested()
        return None
    deadline = monotonic() + ready_timeout
    connected = listener.connected.wait(max(0.0, deadline - monotonic()))
    subscribed = connected and listener.subscribed.wait(
        max(0.0, deadline - monotonic())
    )
    if not connected or not subscribed:
        status = "connect_timeout" if not connected else "suback_timeout"
        coordination_mqtt._update_transport_diagnostics("listener", status=status)
        _emit_mqtt_diagnostics_if_requested()
        listener.stop()
        return None
    return listener


def _emit_mqtt_diagnostics_if_requested() -> None:
    """Print allow-listed transport state only for an explicitly opted-in harness."""
    if os.environ.get("KANBUS_ROUTER_MQTT_DIAGNOSTICS") != "1":
        return
    print(
        "MQTT coordination diagnostics: "
        + json.dumps(
            coordination_mqtt.transport_diagnostics(),
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


def publish_claim_visibility(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    occurred_at: datetime,
    lease_ttl_s: int,
    operation_sequence: int | None = None,
) -> bool:
    """Gossip one already-durable claim; false means continue with Git only."""
    envelope = coordination_mqtt.make_claim_envelope(
        root,
        project_dir,
        configuration,
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=event_id,
        lease_ttl_s=lease_ttl_s,
        occurred_at=occurred_at,
        operation_sequence=operation_sequence,
    )
    return coordination_mqtt.publish_envelope(
        root, project_dir, configuration, envelope
    )


def publish_renewal_visibility(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    state: LeaseState,
    occurred_at: datetime,
) -> bool:
    """Gossip an eligible durable renewal, falling back safely on failure."""
    if not (
        state.active
        and state.event_id
        and state.claimed_at
        and state.expires_at
        and state.contention_window_ends_at
        and occurred_at >= state.contention_window_ends_at
    ):
        return True
    envelope = coordination_mqtt.make_lease_envelope(
        root,
        project_dir,
        configuration,
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=state.event_id,
        lease_ttl_s=max(1, int((state.expires_at - state.claimed_at).total_seconds())),
        expires_at=state.expires_at,
        occurred_at=occurred_at,
        operation_sequence=state.operation_sequence,
    )
    return coordination_mqtt.publish_envelope(
        root, project_dir, configuration, envelope
    )


def publish_release_visibility(
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
) -> bool:
    """Gossip one already-durable release; false leaves Git authoritative."""
    envelope = coordination_mqtt.make_release_envelope(
        root,
        project_dir,
        configuration,
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=event_id,
        occurred_at=occurred_at,
        operation_sequence=operation_sequence,
    )
    return coordination_mqtt.publish_envelope(
        root, project_dir, configuration, envelope
    )
