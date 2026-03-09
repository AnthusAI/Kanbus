from __future__ import annotations

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
