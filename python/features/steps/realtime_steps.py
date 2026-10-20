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

from kanbus.gossip import (
    DedupeSet,
    GossipEnvelope,
    ensure_mosquitto,
    mosquitto_missing_warning_count,
    reset_mosquitto_missing_warning,
)
from kanbus.models import IssueData, OverlayConfig, ProjectConfiguration, RealtimeConfig
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


@when('it receives notification id "{notification_id}" from producer "{producer_id}"')
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
    project_dir = getattr(context, "overlay_project_dir", None) or (
        context.working_directory / "project"
    )
    write_overlay_issue(
        project_dir,
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
    payload = (
        json.dumps(
            {
                "op": "pub",
                "topic": topic,
                "msg": envelope.model_dump(by_alias=True, mode="json"),
            }
        )
        + "\n"
    )
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


@given("mosquitto is not available")
def given_mosquitto_not_available(context: object) -> None:
    reset_mosquitto_missing_warning()
    context._mosquitto_unavailable_env = os.environ.get(
        "KANBUS_TEST_MOSQUITTO_UNAVAILABLE"
    )
    os.environ["KANBUS_TEST_MOSQUITTO_UNAVAILABLE"] = "1"
    context.mosquitto_unavailable = True


@given("realtime autostart is enabled")
def given_realtime_autostart_enabled(context: object) -> None:
    context.realtime_autostart_enabled = True


@when("I publish gossip envelopes for two issue mutations without a broker")
def when_publish_two_without_broker(context: object) -> None:
    from kanbus.gossip import _publish_envelope, broker_is_reachable

    reset_mosquitto_missing_warning()
    configuration = ProjectConfiguration(
        project_directory="project",
        project_key="kanbus",
        hierarchy=[],
        types=[],
        workflows={},
        initial_status="open",
        priorities={},
        default_priority=2,
        realtime=RealtimeConfig(
            transport="mqtt",
            broker="auto",
            autostart=True,
            keepalive=False,
        ),
    )
    import kanbus.gossip as gossip_module

    original_reachable = broker_is_reachable
    gossip_module.broker_is_reachable = lambda _endpoint: False
    try:
        envelope = GossipEnvelope(
            id="env-1",
            ts="2026-01-01T00:00:00Z",
            project="kanbus",
            type="issue.mutated",
            issue_id="KAN-1",
            producer_id="producer-1",
        )
        root = Path.cwd()
        _publish_envelope(root, configuration, "projects/kanbus/events", envelope)
        envelope.id = "env-2"
        _publish_envelope(root, configuration, "projects/kanbus/events", envelope)
    finally:
        gossip_module.broker_is_reachable = original_reachable
    context.mosquitto_hint_count = mosquitto_missing_warning_count()


@when("I attempt MQTT gossip subscription twice in one session")
def when_attempt_mqtt_subscription_twice(context: object) -> None:
    from kanbus.gossip import attempt_mosquitto_missing_warning

    reset_mosquitto_missing_warning()
    attempt_mosquitto_missing_warning()
    attempt_mosquitto_missing_warning()
    context.mosquitto_hint_count = mosquitto_missing_warning_count()


@then("Mosquitto install hints should not be printed")
def then_mosquitto_hints_not_printed(context: object) -> None:
    assert context.mosquitto_hint_count == 0


@then("Mosquitto install hints should be printed once")
def then_mosquitto_hints_printed_once(context: object) -> None:
    assert context.mosquitto_hint_count == 1


@then("the realtime guide documents optional Mosquitto")
def then_doc_optional_mosquitto(context: object) -> None:
    assert "optional" in context.realtime_doc.lower()
    assert "Mosquitto" in context.realtime_doc


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


@when("a subscriber connects and sends a blank line")
def when_subscriber_sends_blank_line(context: object) -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(str(context.uds_socket_path))
    sock.sendall(b"\n")
    sock.close()


@when("a subscriber connects and sends invalid JSON")
def when_subscriber_sends_invalid_json(context: object) -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(str(context.uds_socket_path))
    sock.sendall(b"{not-json\n")
    sock.close()


@then("the broker should remain running")
def then_broker_remains_running(context: object) -> None:
    # Give the thread a moment to process or crash
    time.sleep(0.1)
    assert context.uds_thread.is_alive()


@given("a configuration with realtime broker disabled")
def given_config_broker_disabled(context: object) -> None:

    root = context.working_directory
    config_path = root / "project" / "config.yaml"
    if not config_path.exists():
        # Re-use common steps if possible, or just generate it.
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("project_key: kanbus\nrealtime:\n  broker: off\n")
    else:
        content = config_path.read_text()
        if "realtime:" not in content:
            content += "\nrealtime:\n  broker: off\n"
        else:
            content = content.replace("broker: auto", "broker: off")
        config_path.write_text(content)


def _scoped_project(context: object, name: str) -> dict:
    return context.scope_projects[name]


def _scoped_topic(context: object, name: str) -> str:
    from kanbus.config_loader import load_project_configuration
    from kanbus.gossip import project_event_topic
    from kanbus.project import get_configuration_path

    project = _scoped_project(context, name)
    configuration = load_project_configuration(
        get_configuration_path(project["repository_root"])
    )
    topic = project_event_topic(configuration)
    assert topic is not None
    return topic


def _write_scoped_project(
    context: object, name: str, project_key: str, project_id: str | None
) -> None:
    if not hasattr(context, "scope_temp_dir"):
        context.scope_temp_dir = tempfile.TemporaryDirectory()
        context.scope_projects = {}
        context.scope_raw_subscribers = {}
        context.scope_consumers = {}
    repository_root = Path(context.scope_temp_dir.name) / name
    project_directory = repository_root / "project"
    (project_directory / "issues").mkdir(parents=True)
    project_id_line = f"project_id: {project_id}\n" if project_id else ""
    (repository_root / ".kanbus.yml").write_text(
        "project_directory: project\n"
        f"project_key: {project_key}\n"
        f"{project_id_line}"
        "realtime:\n"
        "  broker: auto\n"
        "  autostart: false\n"
        "  keepalive: false\n"
        "  topics:\n"
        "    project_events: projects/{project}/events\n"
        "  transport: uds\n"
        f"  uds_socket_path: {context.uds_socket_path}\n",
        encoding="utf-8",
    )
    context.scope_projects[name] = {
        "repository_root": repository_root,
        "project_directory": project_directory,
        "project_key": project_key,
        "project_id": project_id,
    }


@given(
    'two projects "{first}" and "{second}" that share the project key "{project_key}" '
    "and the UDS broker"
)
def given_two_scoped_projects(
    context: object, first: str, second: str, project_key: str
) -> None:
    from uuid import uuid4

    for name in (first, second):
        _write_scoped_project(context, name, project_key, str(uuid4()))


@given('a clone "{clone}" of project "{original}" in another directory')
def given_clone_of_project(context: object, clone: str, original: str) -> None:
    source = _scoped_project(context, original)
    _write_scoped_project(context, clone, source["project_key"], source["project_id"])


@given(
    'a project "{name}" with the project key "{project_key}" and no project id '
    "on the UDS broker"
)
def given_project_without_project_id(
    context: object, name: str, project_key: str
) -> None:
    _write_scoped_project(context, name, project_key, None)


@then('the realtime watch of project "{name}" fails with "{message}"')
def then_watch_fails_with_message(context: object, name: str, message: str) -> None:
    from kanbus.gossip import GossipError, run_gossip_watch

    root = _scoped_project(context, name)["repository_root"]
    try:
        run_gossip_watch(root, None, None, None, None, None, False)
    except GossipError as error:
        assert message in str(error)
        return
    raise AssertionError("watch should fail without a project id")


@given('a raw subscriber on the realtime topic of project "{name}"')
def given_raw_subscriber(context: object, name: str) -> None:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(context.uds_socket_path))
    payload = json.dumps({"op": "sub", "topic": _scoped_topic(context, name)}) + "\n"
    sock.sendall(payload.encode())
    context.scope_raw_subscribers[name] = sock
    time.sleep(0.1)


@given('a console realtime consumer for project "{name}"')
def given_console_consumer(context: object, name: str) -> None:
    from kanbus.gossip import run_gossip_bridge

    root = _scoped_project(context, name)["repository_root"]
    applied: list[str] = []

    def _on_envelope(envelope: GossipEnvelope) -> None:
        if envelope.issue_id:
            applied.append(envelope.issue_id)

    thread = threading.Thread(
        target=run_gossip_bridge, args=(root, _on_envelope), daemon=True
    )
    thread.start()
    context.scope_consumers.setdefault(name, []).append(applied)
    time.sleep(0.4)


@when('project "{name}" publishes an issue mutation for "{issue_id}"')
def when_project_publishes_mutation(context: object, name: str, issue_id: str) -> None:
    from kanbus.gossip import publish_issue_mutation

    project = _scoped_project(context, name)
    publish_issue_mutation(
        project["repository_root"],
        project["repository_root"] / "project",
        _issue(issue_id, datetime.now(timezone.utc)),
        None,
        "issue.mutated",
    )


def _publish_remote_mutation(
    context: object, issue_id: str, topic_project: str, identity_project: str
) -> None:
    identity_source = _scoped_project(context, identity_project)
    identity = identity_source["project_id"]
    issue = _issue(issue_id, datetime.now(timezone.utc))
    envelope = GossipEnvelope(
        id=f"remote-{issue_id}",
        ts=issue.updated_at.isoformat().replace("+00:00", "Z"),
        project=identity_source["project_key"],
        project_identity=identity,
        type="issue.mutated",
        issue_id=issue.identifier,
        event_id=f"evt-{issue_id}",
        producer_id="remote-producer",
        issue=issue,
    )
    payload = json.dumps(
        {
            "op": "pub",
            "topic": _scoped_topic(context, topic_project),
            "msg": envelope.model_dump(by_alias=True, mode="json"),
        }
    )
    pub_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    pub_sock.connect(str(context.uds_socket_path))
    pub_sock.sendall((payload + "\n").encode())
    pub_sock.close()


@when(
    'a remote producer publishes an issue mutation for "{issue_id}" in project "{name}"'
)
def when_remote_publishes_in_project(context: object, issue_id: str, name: str) -> None:
    _publish_remote_mutation(context, issue_id, name, name)


@when(
    'a remote producer publishes an issue mutation for "{issue_id}" on the topic of '
    'project "{topic_project}" claiming the identity of project "{identity_project}"'
)
def when_remote_publishes_claiming_identity(
    context: object, issue_id: str, topic_project: str, identity_project: str
) -> None:
    from kanbus.gossip import foreign_project_drop_count

    context.scope_drop_count_before = foreign_project_drop_count()
    _publish_remote_mutation(context, issue_id, topic_project, identity_project)


@then('the raw subscriber of project "{name}" receives an envelope for "{issue_id}"')
def then_raw_subscriber_receives(context: object, name: str, issue_id: str) -> None:
    sock = context.scope_raw_subscribers[name]
    sock.settimeout(3.0)
    line = sock.makefile("rb").readline()
    assert json.loads(line.decode())["msg"]["issue_id"] == issue_id


@then('the raw subscriber of project "{name}" receives no envelope')
def then_raw_subscriber_receives_nothing(context: object, name: str) -> None:
    sock = context.scope_raw_subscribers[name]
    sock.settimeout(0.5)
    try:
        received = sock.recv(4096)
    except socket.timeout:
        return
    raise AssertionError(f"unexpected envelope: {received!r}")


@then(
    'every console realtime consumer of project "{name}" applies the issue "{issue_id}"'
)
def then_consumers_apply_issue(context: object, name: str, issue_id: str) -> None:
    deadline = time.monotonic() + 5.0
    overlay_path = overlay_issue_path(
        _scoped_project(context, name)["project_directory"], issue_id
    )
    for applied in context.scope_consumers[name]:
        while issue_id not in applied:
            assert time.monotonic() < deadline, f"consumer never applied {issue_id}"
            time.sleep(0.05)
    while not overlay_path.exists():
        assert time.monotonic() < deadline, f"overlay never cached {issue_id}"
        time.sleep(0.05)


@then('no console realtime consumer of project "{name}" applies the issue "{issue_id}"')
def then_consumers_do_not_apply_issue(
    context: object, name: str, issue_id: str
) -> None:
    time.sleep(0.5)
    for applied in context.scope_consumers[name]:
        assert issue_id not in applied
    assert not overlay_issue_path(
        _scoped_project(context, name)["project_directory"], issue_id
    ).exists()


@then("the count of dropped events for other projects has increased")
def then_foreign_drop_count_increased(context: object) -> None:
    from kanbus.gossip import foreign_project_drop_count

    assert foreign_project_drop_count() > context.scope_drop_count_before
