from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
import time
from types import SimpleNamespace

from kanbus import gossip
from test_helpers import build_issue


def test_dedupe_set_expires_entries() -> None:
    dedupe = gossip.DedupeSet(ttl_s=1)
    assert dedupe.seen("event-1") is False
    assert dedupe.seen("event-1") is True
    time.sleep(1.05)
    assert dedupe.seen("event-1") is False


def test_parse_broker_url_supports_default_and_explicit_ports() -> None:
    endpoint_default = gossip._parse_broker_url("mqtt://broker.example")
    endpoint_explicit = gossip._parse_broker_url("mqtts://broker.example:8883")
    assert endpoint_default.host == "broker.example"
    assert endpoint_default.port == 1883
    assert endpoint_default.scheme == "mqtt"
    assert endpoint_explicit.host == "broker.example"
    assert endpoint_explicit.port == 8883
    assert endpoint_explicit.scheme == "mqtts"


def test_parse_broker_url_rejects_invalid_values() -> None:
    try:
        gossip._parse_broker_url("not-a-url")
    except gossip.GossipError as error:
        assert "invalid broker url" in str(error)
    else:
        raise AssertionError("expected GossipError")


def test_parse_broker_url_rejects_invalid_port() -> None:
    try:
        gossip._parse_broker_url("mqtt://broker.example:not-a-port")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_uds_socket_path_prefers_xdg_runtime_dir(monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/runtime-test")
    socket_path = gossip._uds_socket_path()
    assert socket_path == Path("/tmp/runtime-test/kanbus/bus.sock")


def test_write_and_load_broker_metadata_round_trip(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "run"
    monkeypatch.setattr(gossip, "_broker_run_dir", lambda: run_dir)
    payload = {"kind": "mosquitto", "endpoint": "mqtt://127.0.0.1:1883"}
    gossip._write_broker_metadata(payload)
    assert gossip._load_broker_metadata() == payload


def test_load_broker_metadata_returns_none_for_invalid_json(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "broker.json").write_text("{invalid-json", encoding="utf-8")
    monkeypatch.setattr(gossip, "_broker_run_dir", lambda: run_dir)
    assert gossip._load_broker_metadata() is None


def test_load_broker_metadata_returns_none_when_file_absent(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gossip, "_broker_run_dir", lambda: run_dir)
    assert gossip._load_broker_metadata() is None


def test_resolve_project_label_falls_back_to_project_key(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    configuration = SimpleNamespace(project_key="kanbus")
    monkeypatch.setattr(gossip, "resolve_labeled_projects", lambda _: [])
    assert gossip._resolve_project_label(root, project_dir, configuration) == "kanbus"


def test_resolve_project_dir_returns_none_for_missing_label(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gossip, "resolve_labeled_projects", lambda _: [])
    assert gossip._resolve_project_dir(tmp_path, "missing") is None


def test_resolve_broker_endpoint_auto_uses_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        gossip,
        "_load_broker_metadata",
        lambda: {"endpoint": "mqtt://127.0.0.1:2883"},
    )
    endpoint = gossip.resolve_broker_endpoint("auto")
    assert endpoint.host == "127.0.0.1"
    assert endpoint.port == 2883


def test_publish_envelope_uses_uds_transport_when_socket_exists(
    monkeypatch, tmp_path: Path
) -> None:
    socket_path = tmp_path / "bus.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: socket_path)

    published: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gossip,
        "_publish_uds",
        lambda topic, envelope, _realtime: published.append((topic, envelope.issue_id or "")),
    )
    monkeypatch.setattr(
        gossip,
        "_publish_mqtt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mqtt path not expected")),
    )

    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="auto", broker="mqtt://127.0.0.1:1883", autostart=True, keepalive=False
        )
    )
    envelope = gossip.GossipEnvelope(
        id="env-1",
        ts="2026-01-01T00:00:00Z",
        project="kanbus",
        type="issue.mutated",
        issue_id="KAN-1",
        producer_id="producer-1",
    )

    gossip._publish_envelope(Path("."), configuration, "topic/one", envelope)
    assert published == [("topic/one", "KAN-1")]


def test_publish_envelope_skips_when_unreachable_and_autostart_disabled(monkeypatch) -> None:
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: Path("/no/such/socket"))
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda _broker: gossip.BrokerEndpoint(
            scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
        ),
    )
    monkeypatch.setattr(gossip, "broker_is_reachable", lambda _endpoint: False)

    called = {"mqtt": False}

    def _publish(*_args, **_kwargs) -> None:
        called["mqtt"] = True

    monkeypatch.setattr(gossip, "_publish_mqtt", _publish)

    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="mqtt://127.0.0.1:1883",
            autostart=False,
            keepalive=False,
        )
    )
    envelope = gossip.GossipEnvelope(
        id="env-2",
        ts="2026-01-01T00:00:00Z",
        project="kanbus",
        type="issue.deleted",
        issue_id="KAN-2",
        producer_id="producer-2",
    )

    gossip._publish_envelope(Path("."), configuration, "topic/two", envelope)
    assert called["mqtt"] is False


@dataclass
class _DummyProcess:
    terminated: bool = False

    def terminate(self) -> None:
        self.terminated = True


def test_publish_envelope_autostarts_and_terminates_when_not_keepalive(monkeypatch) -> None:
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: Path("/no/such/socket"))
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda _broker: gossip.BrokerEndpoint(
            scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
        ),
    )
    monkeypatch.setattr(gossip, "broker_is_reachable", lambda _endpoint: False)

    process = _DummyProcess()
    monkeypatch.setattr(
        gossip,
        "ensure_mosquitto",
        lambda endpoint: gossip.BrokerStartup(endpoint=endpoint, process=process),  # type: ignore[arg-type]
    )

    published: list[str] = []
    monkeypatch.setattr(
        gossip,
        "_publish_mqtt",
        lambda _endpoint, topic, _envelope: published.append(topic),
    )

    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="auto",
            autostart=True,
            keepalive=False,
        )
    )
    envelope = gossip.GossipEnvelope(
        id="env-3",
        ts="2026-01-01T00:00:00Z",
        project="kanbus",
        type="issue.mutated",
        issue_id="KAN-3",
        producer_id="producer-3",
    )

    gossip._publish_envelope(Path("."), configuration, "topic/three", envelope)
    assert published == ["topic/three"]
    assert process.terminated is True


def test_publish_envelope_returns_when_broker_off(monkeypatch) -> None:
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: Path("/no/such/socket"))
    mqtt_called = {"value": False}
    uds_called = {"value": False}
    monkeypatch.setattr(
        gossip,
        "_publish_mqtt",
        lambda *_args, **_kwargs: mqtt_called.__setitem__("value", True),
    )
    monkeypatch.setattr(
        gossip,
        "_publish_uds",
        lambda *_args, **_kwargs: uds_called.__setitem__("value", True),
    )
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="off",
            autostart=True,
            keepalive=False,
        )
    )
    envelope = gossip.GossipEnvelope(
        id="env-off",
        ts="2026-01-01T00:00:00Z",
        project="kanbus",
        type="issue.mutated",
        issue_id="KAN-OFF",
        producer_id="producer-off",
    )
    gossip._publish_envelope(Path("."), configuration, "topic/off", envelope)
    assert mqtt_called["value"] is False
    assert uds_called["value"] is False


def test_publish_envelope_handles_missing_mosquitto(monkeypatch) -> None:
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: Path("/no/such/socket"))
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda _broker: gossip.BrokerEndpoint(
            scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
        ),
    )
    monkeypatch.setattr(gossip, "broker_is_reachable", lambda _endpoint: False)
    monkeypatch.setattr(gossip, "ensure_mosquitto", lambda _endpoint: None)

    printed = {"value": False}
    monkeypatch.setattr(
        gossip,
        "_print_mosquitto_missing",
        lambda: printed.__setitem__("value", True),
    )

    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="auto",
            autostart=True,
            keepalive=False,
        )
    )
    envelope = gossip.GossipEnvelope(
        id="env-missing",
        ts="2026-01-01T00:00:00Z",
        project="kanbus",
        type="issue.mutated",
        issue_id="KAN-MISS",
        producer_id="producer-miss",
    )
    gossip._publish_envelope(Path("."), configuration, "topic/miss", envelope)
    assert printed["value"] is True


def test_publish_issue_mutation_skips_when_config_lookup_fails(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        gossip,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(gossip.ProjectMarkerError("missing")),
    )
    called = {"value": False}
    monkeypatch.setattr(
        gossip, "_publish_envelope", lambda *_args, **_kwargs: called.__setitem__("value", True)
    )
    gossip.publish_issue_mutation(
        root=tmp_path,
        project_dir=tmp_path / "project",
        issue=build_issue("kanbus-1"),
        event_id="evt-1",
        event_type="issue.mutated",
    )
    assert called["value"] is False


def test_publish_issue_mutation_skips_when_broker_off(monkeypatch, tmp_path: Path) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            broker="off",
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        )
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(gossip, "_resolve_project_label", lambda *_args: "kanbus")
    called = {"value": False}
    monkeypatch.setattr(
        gossip, "_publish_envelope", lambda *_args, **_kwargs: called.__setitem__("value", True)
    )
    gossip.publish_issue_mutation(
        root=tmp_path,
        project_dir=tmp_path / "project",
        issue=build_issue("kanbus-2"),
        event_id="evt-2",
        event_type="issue.mutated",
    )
    assert called["value"] is False


def test_publish_issue_deleted_invokes_publish_with_formatted_topic(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            broker="auto",
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        )
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(gossip, "_resolve_project_label", lambda *_args: "alpha")

    captured: dict[str, object] = {}

    def _capture_publish(_root, _config, topic, envelope) -> None:
        captured["topic"] = topic
        captured["envelope"] = envelope

    monkeypatch.setattr(gossip, "_publish_envelope", _capture_publish)
    gossip.publish_issue_deleted(
        root=tmp_path,
        project_dir=tmp_path / "project",
        issue_id="kanbus-3",
        event_id="evt-3",
    )
    assert captured["topic"] == "projects/alpha/events"
    envelope = captured["envelope"]
    assert isinstance(envelope, gossip.GossipEnvelope)
    assert envelope.issue_id == "kanbus-3"
    assert envelope.type == "issue.deleted"


def test_publish_issue_deleted_prints_warning_on_publish_failure(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            broker="auto",
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        )
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(gossip, "_resolve_project_label", lambda *_args: "alpha")
    monkeypatch.setattr(
        gossip,
        "_publish_envelope",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    gossip.publish_issue_deleted(
        root=tmp_path,
        project_dir=tmp_path / "project",
        issue_id="kanbus-4",
        event_id="evt-4",
    )
    captured = capsys.readouterr()
    assert "warning: realtime publish failed for kanbus-4" in captured.err


def test_run_gossip_consumer_raises_for_unknown_project_filter(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="auto",
            autostart=True,
            keepalive=False,
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        ),
        overlay=SimpleNamespace(enabled=False, ttl_s=60),
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(
        gossip,
        "resolve_labeled_projects",
        lambda _root: [SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha")],
    )
    try:
        gossip._run_gossip_consumer(
            root=tmp_path,
            project_filter="missing",
            transport_override=None,
            broker_override=None,
            autostart_override=None,
            keepalive_override=None,
            print_envelopes=False,
            on_envelope=None,
            autostart_local_uds=False,
            broker_off_is_error=True,
        )
    except gossip.GossipError as error:
        assert "unknown project label" in str(error)
    else:
        raise AssertionError("expected GossipError")


def test_run_gossip_consumer_autostarts_local_uds(monkeypatch, tmp_path: Path) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="auto",
            broker="auto",
            autostart=True,
            keepalive=False,
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        ),
        overlay=SimpleNamespace(enabled=False, ttl_s=60),
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(
        gossip,
        "resolve_labeled_projects",
        lambda _root: [SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha")],
    )
    socket_path = tmp_path / "sock" / "bus.sock"
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: socket_path)
    ensured = {"value": False}
    monkeypatch.setattr(
        gossip,
        "_ensure_local_uds_broker",
        lambda _realtime: ensured.__setitem__("value", True),
    )
    captured: dict[str, object] = {}

    def _run_uds(_realtime, topics, _handler) -> None:
        captured["topics"] = topics

    monkeypatch.setattr(gossip, "run_uds_subscription", _run_uds)
    gossip._run_gossip_consumer(
        root=tmp_path,
        project_filter=None,
        transport_override=None,
        broker_override=None,
        autostart_override=None,
        keepalive_override=None,
        print_envelopes=False,
        on_envelope=None,
        autostart_local_uds=True,
        broker_off_is_error=False,
    )
    assert ensured["value"] is True
    assert captured["topics"] == ["projects/alpha/events"]


def test_run_gossip_consumer_broker_off_returns_when_not_error(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="off",
            autostart=True,
            keepalive=False,
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        ),
        overlay=SimpleNamespace(enabled=False, ttl_s=60),
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(
        gossip,
        "resolve_labeled_projects",
        lambda _root: [SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha")],
    )
    called = {"mqtt": False}
    monkeypatch.setattr(
        gossip,
        "run_mqtt_subscription",
        lambda *_args, **_kwargs: called.__setitem__("mqtt", True),
    )
    gossip._run_gossip_consumer(
        root=tmp_path,
        project_filter=None,
        transport_override=None,
        broker_override=None,
        autostart_override=None,
        keepalive_override=None,
        print_envelopes=False,
        on_envelope=None,
        autostart_local_uds=False,
        broker_off_is_error=False,
    )
    assert called["mqtt"] is False


def test_run_gossip_consumer_raises_when_broker_unreachable_and_autostart_disabled(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        realtime=SimpleNamespace(
            transport="mqtt",
            broker="auto",
            autostart=False,
            keepalive=False,
            topics=SimpleNamespace(project_events="projects/{project}/events"),
        ),
        overlay=SimpleNamespace(enabled=False, ttl_s=60),
    )
    monkeypatch.setattr(gossip, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(gossip, "load_project_configuration", lambda _path: configuration)
    monkeypatch.setattr(
        gossip,
        "resolve_labeled_projects",
        lambda _root: [SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha")],
    )
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda _broker: gossip.BrokerEndpoint(
            scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
        ),
    )
    monkeypatch.setattr(gossip, "broker_is_reachable", lambda _endpoint: False)
    try:
        gossip._run_gossip_consumer(
            root=tmp_path,
            project_filter=None,
            transport_override=None,
            broker_override=None,
            autostart_override=None,
            keepalive_override=None,
            print_envelopes=False,
            on_envelope=None,
            autostart_local_uds=False,
            broker_off_is_error=True,
        )
    except gossip.GossipError as error:
        assert "broker not reachable and autostart disabled" in str(error)
    else:
        raise AssertionError("expected GossipError")


def test_ensure_local_uds_broker_starts_thread_and_detects_socket(
    monkeypatch, tmp_path: Path
) -> None:
    class _FakeSocketPath:
        def __init__(self) -> None:
            self.counter = 0

        def exists(self) -> bool:
            self.counter += 1
            return self.counter >= 3

        def __str__(self) -> str:
            return "/tmp/fake.sock"

    fake_path = _FakeSocketPath()
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: fake_path)

    class _FakeThread:
        def __init__(self, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False

        def start(self) -> None:
            self.started = True

    monkeypatch.setattr(gossip.threading, "Thread", _FakeThread)
    monkeypatch.setattr(gossip.time, "sleep", lambda _seconds: None)
    gossip._ensure_local_uds_broker(SimpleNamespace(uds_socket_path=None))


def test_ensure_local_uds_broker_raises_when_socket_never_appears(
    monkeypatch, tmp_path: Path
) -> None:
    class _NeverPath:
        def exists(self) -> bool:
            return False

        def __str__(self) -> str:
            return "/tmp/missing.sock"

    monkeypatch.setattr(gossip, "_uds_socket_path", lambda _realtime: _NeverPath())

    class _FakeThread:
        def __init__(self, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr(gossip.threading, "Thread", _FakeThread)
    monkeypatch.setattr(gossip.time, "sleep", lambda _seconds: None)
    try:
        gossip._ensure_local_uds_broker(SimpleNamespace(uds_socket_path=None))
    except gossip.GossipError as error:
        assert "failed to start local UDS broker" in str(error)
    else:
        raise AssertionError("expected GossipError")


def test_run_gossip_broker_uses_fallback_socket_when_config_missing(
    monkeypatch, tmp_path: Path
) -> None:
    expected_socket = tmp_path / "fallback.sock"
    monkeypatch.setattr(
        gossip,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(gossip.ProjectMarkerError("missing")),
    )
    monkeypatch.setattr(gossip, "_uds_socket_path", lambda *_args, **_kwargs: expected_socket)
    captured: dict[str, Path] = {}
    monkeypatch.setattr(
        gossip,
        "run_uds_broker",
        lambda socket_path: captured.__setitem__("socket", socket_path),
    )
    gossip.run_gossip_broker(tmp_path, socket_override=None)
    assert captured["socket"] == expected_socket


def test_resolve_broker_endpoint_auto_defaults_when_metadata_missing(monkeypatch) -> None:
    monkeypatch.setattr(gossip, "_load_broker_metadata", lambda: None)
    endpoint = gossip.resolve_broker_endpoint("auto")
    assert endpoint.host == "127.0.0.1"
    assert endpoint.port == 1883
    assert endpoint.scheme == "mqtt"


def test_broker_is_reachable_handles_success_and_failure(monkeypatch) -> None:
    endpoint = gossip.BrokerEndpoint(
        scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
    )

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(gossip.socket, "create_connection", lambda *_args, **_kwargs: _Conn())
    assert gossip.broker_is_reachable(endpoint) is True

    def _raise(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(gossip.socket, "create_connection", _raise)
    assert gossip.broker_is_reachable(endpoint) is False


def test_ensure_mosquitto_rejects_non_local_or_non_mqtt(monkeypatch) -> None:
    mqtts = gossip.BrokerEndpoint(
        scheme="mqtts", host="127.0.0.1", port=8883, url="mqtts://127.0.0.1:8883"
    )
    remote = gossip.BrokerEndpoint(
        scheme="mqtt", host="broker.example", port=1883, url="mqtt://broker.example:1883"
    )
    monkeypatch.setattr(gossip, "_mosquitto_available", lambda: True)
    assert gossip.ensure_mosquitto(mqtts) is None
    assert gossip.ensure_mosquitto(remote) is None


def test_ensure_mosquitto_returns_none_when_binary_missing(monkeypatch) -> None:
    endpoint = gossip.BrokerEndpoint(
        scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
    )
    monkeypatch.setattr(gossip, "_mosquitto_available", lambda: False)
    assert gossip.ensure_mosquitto(endpoint) is None


def test_ensure_mosquitto_writes_config_and_metadata(monkeypatch, tmp_path: Path) -> None:
    endpoint = gossip.BrokerEndpoint(
        scheme="mqtt", host="127.0.0.1", port=1883, url="mqtt://127.0.0.1:1883"
    )
    run_dir = tmp_path / "run"
    monkeypatch.setattr(gossip, "_broker_run_dir", lambda: run_dir)
    monkeypatch.setattr(gossip, "_mosquitto_available", lambda: True)
    monkeypatch.setattr(gossip, "_find_free_port", lambda _start: 1999)
    monkeypatch.setattr(gossip, "_now_iso", lambda: "2026-03-09T00:00:00.000Z")

    class _Proc:
        pid = 4321

    monkeypatch.setattr(gossip.subprocess, "Popen", lambda *_args, **_kwargs: _Proc())
    startup = gossip.ensure_mosquitto(endpoint)
    assert startup is not None
    assert startup.endpoint.port == 1999
    conf = (run_dir / "mosquitto.conf").read_text(encoding="utf-8")
    assert "listener 1999 127.0.0.1" in conf
    metadata = gossip._load_broker_metadata()
    assert metadata is not None
    assert metadata["pid"] == 4321
    assert metadata["endpoint"] == "mqtt://127.0.0.1:1999"


def test_find_free_port_skips_in_use_port(monkeypatch) -> None:
    class _Sock:
        calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def bind(self, addr) -> None:
            _Sock.calls += 1
            if _Sock.calls == 1:
                raise OSError("in use")
            return None

    monkeypatch.setattr(gossip.socket, "socket", lambda *_args, **_kwargs: _Sock())
    port = gossip._find_free_port(1883)
    assert port == 1884


def test_broadcast_payload_fans_out_and_prunes_dead_subscribers() -> None:
    class _Sock:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail
            self.messages: list[bytes] = []

        def sendall(self, data: bytes) -> None:
            if self.fail:
                raise OSError("broken pipe")
            self.messages.append(data)

    keep = _Sock()
    drop = _Sock(fail=True)
    other_topic = _Sock()
    subscribers: list[tuple[str, object]] = [
        ("topic/one", keep),
        ("topic/one", drop),
        ("topic/two", other_topic),
    ]
    gossip._broadcast_payload(
        {"topic": "topic/one", "msg": {"id": "env-1"}}, subscribers, gossip.threading.Lock()
    )
    assert len(keep.messages) == 1
    assert b'"topic": "topic/one"' in keep.messages[0]
    assert ("topic/one", drop) not in subscribers
    assert ("topic/two", other_topic) in subscribers


def test_handle_uds_connection_handles_sub_pub_invalid_json_and_timeout(monkeypatch) -> None:
    class _Conn:
        def __init__(self) -> None:
            self._chunks = [
                b'{"op":"sub","topic":"topic/one"}\n',
                b'not-json\n',
                b'{"op":"pub","topic":"topic/one","msg":{"id":"env-1"}}\n',
                socket.timeout(),
                b"",
            ]

        def recv(self, _size: int) -> bytes:
            item = self._chunks.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    conn = _Conn()
    subscribers: list[tuple[str, object]] = []
    seen_payloads: list[dict] = []
    monkeypatch.setattr(
        gossip,
        "_broadcast_payload",
        lambda payload, subs, lock: seen_payloads.append(payload),
    )

    gossip._handle_uds_connection(conn, subscribers, gossip.threading.Lock())
    assert len(subscribers) == 1
    assert subscribers[0][0] == "topic/one"
    assert seen_payloads == [{"op": "pub", "topic": "topic/one", "msg": {"id": "env-1"}}]


def test_run_uds_subscription_subscribes_and_dispatches_valid_envelopes(monkeypatch) -> None:
    class _Sock:
        def __init__(self) -> None:
            self.sent: list[bytes] = []
            self.recv_chunks = [
                b'{"topic":"projects/a/events","msg":{"id":"env-1","ts":"2026-01-01T00:00:00Z","project":"a","type":"issue.deleted","issue_id":"kanbus-1","producer_id":"p1"}}\n',
                b'{"topic":"projects/a/events","msg":{"id":"env-2","bad":true}}\n',
                b"",
            ]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def connect(self, _path: str) -> None:
            return None

        def sendall(self, data: bytes) -> None:
            self.sent.append(data)

        def recv(self, _size: int) -> bytes:
            return self.recv_chunks.pop(0)

    fake_socket = _Sock()
    monkeypatch.setattr(gossip.socket, "socket", lambda *_args, **_kwargs: fake_socket)
    realtime = SimpleNamespace(uds_socket_path="/tmp/kanbus-test.sock")
    seen_ids: list[str] = []

    def _handler(envelope: gossip.GossipEnvelope) -> None:
        seen_ids.append(envelope.id)

    gossip.run_uds_subscription(realtime, ["projects/a/events"], _handler)
    assert any(b'"op": "sub"' in payload for payload in fake_socket.sent)
    assert seen_ids == ["env-1"]
