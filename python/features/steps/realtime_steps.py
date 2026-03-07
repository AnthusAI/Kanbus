"""Behave steps for realtime gossip and overlay."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from behave import given, then, when

from kanbus.gossip import DedupeSet, GossipEnvelope, ensure_mosquitto
from kanbus.models import IssueData, OverlayConfig
from kanbus.overlay import (
    OverlayIssueRecord,
    gc_overlay,
    overlay_issue_path,
    resolve_issue_with_overlay,
    write_overlay_issue,
)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _issue(identifier: str, updated_at: datetime) -> IssueData:
    return IssueData(
        id=identifier,
        title="Realtime test",
        description="",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=updated_at,
        updated_at=updated_at,
        closed_at=None,
        custom={},
    )


@when("I read the realtime documentation")
def when_read_realtime_docs(context: object) -> None:
    root = Path(__file__).resolve().parents[3]
    doc_path = root / "docs" / "REALTIME.md"
    if not doc_path.exists():
        raise AssertionError("docs/REALTIME.md not found")
    context.realtime_doc = doc_path.read_text(encoding="utf-8")


@then("the realtime guide documents transport selection")
def then_doc_transport(context: object) -> None:
    assert "Transport selection" in context.realtime_doc


@then("the realtime guide documents broker discovery")
def then_doc_broker_discovery(context: object) -> None:
    assert "Discovery precedence" in context.realtime_doc


@then("the realtime guide documents autostart behavior")
def then_doc_autostart(context: object) -> None:
    assert "Autostart" in context.realtime_doc


@then("the realtime guide documents envelope schema")
def then_doc_envelope(context: object) -> None:
    assert "Envelope schema" in context.realtime_doc


@then("the realtime guide documents dedupe rules")
def then_doc_dedupe(context: object) -> None:
    assert "Dedupe" in context.realtime_doc


@then("the realtime guide documents overlay merge rules")
def then_doc_overlay_merge(context: object) -> None:
    assert "Overlay merge" in context.realtime_doc


@then("the realtime guide documents overlay GC and hooks")
def then_doc_overlay_gc(context: object) -> None:
    assert "overlay gc" in context.realtime_doc
    assert "install-hooks" in context.realtime_doc


@then("the realtime guide documents CLI commands")
def then_doc_cli(context: object) -> None:
    assert "gossip watch" in context.realtime_doc


@then("the realtime guide documents config blocks")
def then_doc_config(context: object) -> None:
    assert "realtime:" in context.realtime_doc
    assert "overlay:" in context.realtime_doc


@given('a gossip issue "{identifier}" updated at "{timestamp}"')
def given_gossip_issue(context: object, identifier: str, timestamp: str) -> None:
    updated_at = _parse_ts(timestamp)
    context.gossip_issue = _issue(identifier, updated_at)


@when("I build a gossip envelope for the issue")
def when_build_envelope(context: object) -> None:
    issue: IssueData = context.gossip_issue
    context.gossip_envelope = GossipEnvelope(
        id="n1",
        ts=issue.updated_at.isoformat().replace("+00:00", "Z"),
        project="kanbus",
        type="issue.mutated",
        issue_id=issue.identifier,
        event_id="evt-1",
        producer_id="producer-1",
        issue=issue,
    )


@then("the envelope includes the issue snapshot")
def then_envelope_includes_issue(context: object) -> None:
    envelope: GossipEnvelope = context.gossip_envelope
    payload = envelope.model_dump(by_alias=True, mode="json")
    assert payload.get("issue") is not None


@then("the envelope includes standard metadata fields")
def then_envelope_standard_metadata(context: object) -> None:
    envelope: GossipEnvelope = context.gossip_envelope
    payload = envelope.model_dump(by_alias=True, mode="json")
    for key in ("id", "ts", "project", "type", "issue_id", "event_id", "producer_id"):
        assert key in payload


@given('a gossip receiver with producer id "{producer_id}"')
def given_gossip_receiver(context: object, producer_id: str) -> None:
    context.gossip_producer_id = producer_id
    context.gossip_dedupe = DedupeSet(ttl_s=3600)


@given('it has already seen notification id "{notification_id}"')
def given_seen_notification(context: object, notification_id: str) -> None:
    context.gossip_dedupe.seen(notification_id)


@when(
    'it receives notification id "{notification_id}" from producer "{producer_id}"'
)
def when_receive_notification(
    context: object, notification_id: str, producer_id: str
) -> None:
    ignored = False
    if context.gossip_dedupe.seen(notification_id):
        ignored = True
    if producer_id == context.gossip_producer_id:
        ignored = True
    context.last_notification_ignored = ignored


@then("the notification is ignored")
def then_notification_ignored(context: object) -> None:
    assert context.last_notification_ignored is True


@given('a base issue "{identifier}" updated at "{timestamp}"')
def given_base_issue(context: object, identifier: str, timestamp: str) -> None:
    updated_at = _parse_ts(timestamp)
    context.overlay_base_issue = _issue(identifier, updated_at)
    if not getattr(context, "overlay_project_dir", None):
        temp_dir = tempfile.TemporaryDirectory()
        context.overlay_temp_dir = temp_dir
        project_dir = Path(temp_dir.name) / "project"
        (project_dir / "issues").mkdir(parents=True, exist_ok=True)
        context.overlay_project_dir = project_dir
    issue_path = context.overlay_project_dir / "issues" / f"{identifier}.json"
    issue_path.write_text(
        json.dumps(
            context.overlay_base_issue.model_dump(by_alias=True, mode="json"), indent=2
        ),
        encoding="utf-8",
    )


@given('an overlay issue "{identifier}" updated at "{timestamp}"')
def given_overlay_issue(context: object, identifier: str, timestamp: str) -> None:
    updated_at = _parse_ts(timestamp)
    overlay_issue = _issue(identifier, updated_at)
    context.overlay_issue_record = OverlayIssueRecord(
        issue=overlay_issue,
        overlay_ts=updated_at.isoformat().replace("+00:00", "Z"),
        overlay_event_id=None,
    )


@when("I resolve the overlay issue")
def when_resolve_overlay(context: object) -> None:
    project_dir: Path = context.overlay_project_dir
    context.overlay_resolved = resolve_issue_with_overlay(
        project_dir,
        context.overlay_base_issue,
        context.overlay_issue_record,
        None,
        OverlayConfig(enabled=True, ttl_s=86400),
    )


@then("the overlay version is returned")
def then_overlay_version(context: object) -> None:
    resolved = context.overlay_resolved
    assert resolved is not None
    assert resolved.updated_at == context.overlay_issue_record.issue.updated_at


@given('an overlay snapshot "{identifier}" updated at "{timestamp}"')
def given_overlay_snapshot(context: object, identifier: str, timestamp: str) -> None:
    updated_at = _parse_ts(timestamp)
    overlay_issue = _issue(identifier, updated_at)
    write_overlay_issue(
        context.overlay_project_dir,
        overlay_issue,
        updated_at.isoformat().replace("+00:00", "Z"),
        None,
    )


@when("I run overlay GC")
def when_run_overlay_gc(context: object) -> None:
    gc_overlay(context.overlay_project_dir, OverlayConfig(enabled=True, ttl_s=86400))


@then('the overlay snapshot "{identifier}" is removed')
def then_overlay_removed(context: object, identifier: str) -> None:
    assert not overlay_issue_path(context.overlay_project_dir, identifier).exists()


@given("a running UDS gossip broker")
def given_running_uds_broker(context: object) -> None:
    temp_dir = tempfile.TemporaryDirectory()
    context.uds_temp_dir = temp_dir
    socket_path = Path(temp_dir.name) / "bus.sock"
    context.uds_socket_path = socket_path

    def _run() -> None:
        from kanbus.gossip import run_uds_broker

        run_uds_broker(socket_path)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    context.uds_thread = thread
    time.sleep(0.1)


@when('a subscriber listens on "{topic}"')
def when_subscribe_uds(context: object, topic: str) -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(str(context.uds_socket_path))
    payload = json.dumps({"op": "sub", "topic": topic}) + "\n"
    sock.sendall(payload.encode())
    context.uds_subscriber = sock
    context.uds_topic = topic


@when('a publisher sends a gossip envelope on "{topic}"')
def when_publish_uds(context: object, topic: str) -> None:
    issue = _issue("kanbus-uds", datetime.now(timezone.utc))
    envelope = GossipEnvelope(
        id="uds-msg-1",
        ts=issue.updated_at.isoformat().replace("+00:00", "Z"),
        project="kanbus",
        type="issue.mutated",
        issue_id=issue.identifier,
        event_id="evt-uds",
        producer_id="producer-uds",
        issue=issue,
    )
    context.uds_published_id = envelope.id
    payload = json.dumps(
        {"op": "pub", "topic": topic, "msg": envelope.model_dump(by_alias=True, mode="json")}
    ) + "\n"
    pub_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    pub_sock.settimeout(2.0)
    pub_sock.connect(str(context.uds_socket_path))
    pub_sock.sendall(payload.encode())
    pub_sock.close()


@then("the subscriber receives the envelope")
def then_subscriber_receives(context: object) -> None:
    sock: socket.socket = context.uds_subscriber
    buffer = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buffer += chunk
        if b"\n" in buffer:
            line, _rest = buffer.split(b"\n", 1)
            payload = json.loads(line.decode())
            msg = payload.get("msg", {})
            assert msg.get("id") == context.uds_published_id
            return
    raise AssertionError("subscriber did not receive envelope")


@given("mosquitto is available")
def given_mosquitto_available(context: object) -> None:
    if not _mosquitto_on_path():
        context.scenario.skip("mosquitto not installed")


@when("I autostart a mosquitto broker")
def when_autostart_mosquitto(context: object) -> None:
    from kanbus.gossip import _parse_broker_url

    endpoint = _parse_broker_url("mqtt://127.0.0.1:1883")
    startup = ensure_mosquitto(endpoint)
    context.mosquitto_startup = startup
    if startup is not None:
        # allow broker.json to flush
        time.sleep(0.1)


@then("broker metadata is written")
def then_broker_metadata_written(context: object) -> None:
    run_dir = Path.home() / ".kanbus" / "run"
    broker_path = run_dir / "broker.json"
    assert broker_path.exists()
    if context.mosquitto_startup is not None:
        context.mosquitto_startup.process.terminate()


def _mosquitto_on_path() -> bool:
    for entry in os.environ.get("PATH", "").split(":"):
        if not entry:
            continue
        candidate = Path(entry) / "mosquitto"
        if candidate.exists():
            return True
    return False
