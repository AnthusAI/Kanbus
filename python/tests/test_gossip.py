from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from types import SimpleNamespace

from kanbus import gossip


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
