"""Failure and message-boundary tests for optional MQTT coordination."""

from __future__ import annotations

import builtins
import copy
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from kanbus import coordination, coordination_mqtt, gossip
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.gossip import CoordinationGossipEnvelope
from kanbus.models import ProjectConfiguration


@pytest.fixture(autouse=True)
def _isolate_transport_diagnostics():
    diagnostics = coordination_mqtt._TRANSPORT_DIAGNOSTICS
    with coordination_mqtt._TRANSPORT_DIAGNOSTICS_LOCK:
        previous = copy.deepcopy(diagnostics)
        for channel in ("listener", "publisher"):
            diagnostics[channel].clear()
    try:
        yield
    finally:
        with coordination_mqtt._TRANSPORT_DIAGNOSTICS_LOCK:
            for channel in ("listener", "publisher"):
                diagnostics[channel].clear()
                diagnostics[channel].update(previous[channel])


def _configuration(*, providers: list[str] | None = None) -> ProjectConfiguration:
    values = copy.deepcopy(DEFAULT_CONFIGURATION)
    if providers is not None:
        values["coordination"]["providers"] = providers
    values["realtime"].update(
        transport="mqtt",
        broker="mqtt://broker.example:1883",
        autostart=False,
        mqtt_custom_authorizer_name=None,
        mqtt_api_token=None,
    )
    return ProjectConfiguration.model_validate(values)


def _install_fake_paho(monkeypatch, client_class) -> None:
    paho_module = ModuleType("paho")
    mqtt_module = ModuleType("paho.mqtt")
    client_module = ModuleType("paho.mqtt.client")
    client_module.Client = client_class
    client_module.MQTT_ERR_SUCCESS = 0
    paho_module.mqtt = mqtt_module
    mqtt_module.client = client_module
    monkeypatch.setitem(sys.modules, "paho", paho_module)
    monkeypatch.setitem(sys.modules, "paho.mqtt", mqtt_module)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", client_module)


def _envelope(*, project: str = "kanbus", producer_id: str = "peer"):
    return CoordinationGossipEnvelope(
        id=f"envelope-{project}-{producer_id}",
        ts=coordination.format_timestamp(datetime.now(UTC)),
        project=project,
        type="coordination.claim",
        event_id=f"event-{project}-{producer_id}",
        producer_id=producer_id,
        resource="router:issue:kbs-message-boundary",
        owner=producer_id,
        claim_id=f"claim-{producer_id}",
        lease_ttl_s=300,
    )


def test_provider_probe_returns_git_for_disabled_missing_and_unreachable_mqtt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _configuration(providers=["git"])
    assert not coordination_mqtt.provider_available(tmp_path, config)
    assert (
        coordination_mqtt.transport_diagnostics()["listener"]["provider_status"]
        == "not_configured"
    )

    config.coordination.providers = ["mqtt", "git"]
    config.realtime.transport = "websocket"
    assert not coordination_mqtt.provider_available(tmp_path, config)
    assert (
        coordination_mqtt.transport_diagnostics()["listener"]["provider_status"]
        == "disabled"
    )

    config.realtime.transport = "mqtt"
    monkeypatch.setattr(
        gossip,
        "broker_is_reachable",
        lambda _endpoint: (_ for _ in ()).throw(OSError("socket details")),
    )
    assert not coordination_mqtt.provider_available(tmp_path, config)
    diagnostics = coordination_mqtt.transport_diagnostics()["listener"]
    assert diagnostics["provider_status"] == "endpoint_unavailable"
    assert diagnostics["provider_error_type"] == "OSError"
    assert "socket details" not in str(diagnostics)


def test_provider_probe_reports_paho_unavailable_without_importing_other_services(
    monkeypatch,
    tmp_path: Path,
) -> None:
    original_import = builtins.__import__

    def import_without_paho(name, *args, **kwargs):
        if name == "paho.mqtt.client":
            raise ImportError("paho intentionally hidden in this test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_paho)
    config = _configuration(providers=["mqtt", "git"])

    assert not coordination_mqtt.provider_available(tmp_path, config)
    assert (
        coordination_mqtt.transport_diagnostics()["listener"]["provider_status"]
        == "paho_unavailable"
    )


def test_listener_rejects_malformed_and_foreign_messages_and_ignores_echo(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(gossip, "producer_id", lambda: "local-producer")
    monkeypatch.setattr(gossip, "_resolve_project_label", lambda *_args: "kanbus")
    clients = []

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            self.on_connect = None
            self.on_subscribe = None
            self.on_message = None
            clients.append(self)

        def connect(self, *_args):
            return None

        def loop_start(self):
            self.on_connect(self, None, None, 0)
            self.on_subscribe(self, None, 1, [0])

        def subscribe(self, *_args, **_kwargs):
            return 0, 1

        def disconnect(self):
            return None

        def loop_stop(self):
            return None

    _install_fake_paho(monkeypatch, FakeClient)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    listener = coordination_mqtt.start_listener(tmp_path, project_dir, config)
    assert listener is not None and listener.subscribed.is_set()
    client = clients[0]

    client.on_message(client, None, SimpleNamespace(payload=b"not-json"))
    foreign = _envelope(project="another-project")
    client.on_message(
        client,
        None,
        SimpleNamespace(payload=foreign.model_dump_json().encode("utf-8")),
    )
    echo = _envelope(producer_id="local-producer")
    client.on_message(
        client,
        None,
        SimpleNamespace(payload=echo.model_dump_json().encode("utf-8")),
    )
    peer = _envelope()
    client.on_message(
        client,
        None,
        SimpleNamespace(payload=peer.model_dump_json().encode("utf-8")),
    )

    diagnostics = coordination_mqtt.transport_diagnostics()["listener"]
    assert diagnostics["rejected_messages"] == 2
    assert diagnostics["peer_messages"] == 1
    assert listener.received.is_set()
    stored = coordination_mqtt.load_envelopes(project_dir)
    assert [envelope.id for envelope in stored] == [peer.id]
    listener.stop()


def test_failed_publish_records_only_safe_exception_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    envelope = _envelope()
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(gossip, "_resolve_project_label", lambda *_args: "kanbus")
    monkeypatch.setattr(
        gossip,
        "_publish_mqtt",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("secret bearer-value")),
    )

    assert not coordination_mqtt.publish_envelope(
        tmp_path, project_dir, config, envelope
    )
    diagnostics = coordination_mqtt.transport_diagnostics()["publisher"]
    assert diagnostics == {"status": "failed", "error_type": "RuntimeError"}
    assert "bearer-value" not in str(diagnostics)
    assert coordination_mqtt.load_envelopes(project_dir) == []


def test_provider_probe_local_uds_selection_never_attempts_tcp(monkeypatch, tmp_path):
    config = _configuration(providers=["mqtt", "git"])
    config.realtime.transport = "auto"
    monkeypatch.setattr(
        gossip,
        "_uds_socket_path",
        lambda _realtime: SimpleNamespace(exists=lambda: True),
    )
    monkeypatch.setattr(
        gossip,
        "broker_is_reachable",
        lambda *_args: (_ for _ in ()).throw(AssertionError("TCP probe attempted")),
    )

    assert not coordination_mqtt.provider_available(tmp_path, config)
    assert (
        coordination_mqtt.transport_diagnostics()["listener"]["provider_status"]
        == "local_uds_selected"
    )
