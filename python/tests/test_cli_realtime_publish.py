"""Unit tests for the CLI realtime publish policy and daemon connection limits."""

from __future__ import annotations

import io
import threading
import time
from types import SimpleNamespace

import pytest

from kanbus import daemon_client, daemon_server, gossip
from kanbus.gossip import GossipEnvelope


def _envelope() -> GossipEnvelope:
    return GossipEnvelope(
        id="id-1",
        ts="2026-01-01T00:00:00Z",
        project="alpha",
        type="issue.mutated",
        producer_id="producer-1",
    )


def _configuration(broker: str, transport: str = "mqtt") -> SimpleNamespace:
    return SimpleNamespace(
        realtime=SimpleNamespace(
            transport=transport,
            broker=broker,
            uds_socket_path=None,
        )
    )


@pytest.fixture(autouse=True)
def _no_leftover_publishes():
    gossip.finish_pending_realtime_publishes()
    yield
    gossip.finish_pending_realtime_publishes()


@pytest.mark.parametrize("broker", ["auto", "off"])
def test_broker_auto_and_off_never_publish(monkeypatch, broker: str) -> None:
    published: list[object] = []
    monkeypatch.setattr(
        gossip, "_publish_mqtt", lambda *args, **_kwargs: published.append(args)
    )
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda *_args: pytest.fail("broker discovery must not run"),
    )
    gossip._publish_issue_event(
        _configuration(broker), "topic", _envelope(), "kanbus-1"
    )
    gossip.finish_pending_realtime_publishes()
    assert published == []


def test_explicit_broker_publishes_on_a_daemon_thread(monkeypatch) -> None:
    published_on: list[str] = []
    monkeypatch.setattr(
        gossip,
        "_publish_mqtt",
        lambda *_args, **_kwargs: published_on.append(threading.current_thread().name),
    )
    gossip._publish_issue_event(
        _configuration("mqtt://127.0.0.1:1883"), "topic", _envelope(), "kanbus-1"
    )
    gossip.finish_pending_realtime_publishes()
    assert published_on == ["kanbus-realtime-publish"]


def test_invalid_explicit_broker_warns(monkeypatch, capsys) -> None:
    gossip._publish_issue_event(
        _configuration("not-a-url"), "topic", _envelope(), "kanbus-1"
    )
    assert "warning: realtime publish failed for kanbus-1" in capsys.readouterr().err


def test_publish_failure_is_reported_as_a_warning(monkeypatch, capsys) -> None:
    def refuse(*_args, **_kwargs) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(gossip, "_publish_mqtt", refuse)
    gossip._publish_issue_event(
        _configuration("mqtt://127.0.0.1:1883"), "topic", _envelope(), "kanbus-1"
    )
    gossip.finish_pending_realtime_publishes()
    error = capsys.readouterr().err
    assert "warning: realtime publish failed for kanbus-1: connection refused" in error


def test_wedged_publish_is_abandoned_at_the_cap(monkeypatch, capsys) -> None:
    release = threading.Event()
    monkeypatch.setattr(
        gossip, "_publish_mqtt", lambda *_args, **_kwargs: release.wait(timeout=10)
    )
    monkeypatch.setattr(gossip, "CLI_REALTIME_PUBLISH_CAP_SECONDS", 0.2)
    started = time.monotonic()
    gossip._publish_issue_event(
        _configuration("mqtt://127.0.0.1:1883"), "topic", _envelope(), "kanbus-1"
    )
    gossip.finish_pending_realtime_publishes()
    elapsed = time.monotonic() - started
    release.set()
    assert elapsed < 2.0
    assert "warning: realtime publish abandoned after 0.2s" in capsys.readouterr().err


def test_completed_publishes_are_pruned_from_the_pending_list(monkeypatch) -> None:
    monkeypatch.setattr(gossip, "_publish_mqtt", lambda *_args, **_kwargs: None)
    for _ in range(3):
        gossip._publish_issue_event(
            _configuration("mqtt://127.0.0.1:1883"), "topic", _envelope(), "kanbus-1"
        )
        time.sleep(0.05)
    assert len(gossip._pending_cli_publishes) <= 1


def test_running_console_hub_receives_the_event_inline(monkeypatch, tmp_path) -> None:
    socket_path = tmp_path / "bus.sock"
    socket_path.write_text("")
    published: list[object] = []
    monkeypatch.setattr(
        gossip, "_publish_uds", lambda *args, **_kwargs: published.append(args)
    )
    configuration = _configuration("auto", transport="auto")
    configuration.realtime.uds_socket_path = str(socket_path)
    gossip._publish_issue_event(configuration, "topic", _envelope(), "kanbus-1")
    assert len(published) == 1


def test_stale_hub_socket_falls_through_to_the_explicit_broker(
    monkeypatch, tmp_path
) -> None:
    socket_path = tmp_path / "bus.sock"
    socket_path.write_text("")

    def refuse(*_args, **_kwargs) -> None:
        raise OSError("stale socket")

    published: list[object] = []
    monkeypatch.setattr(gossip, "_publish_uds", refuse)
    monkeypatch.setattr(
        gossip, "_publish_mqtt", lambda *args, **_kwargs: published.append(args)
    )
    configuration = _configuration("mqtt://127.0.0.1:1883", transport="auto")
    configuration.realtime.uds_socket_path = str(socket_path)
    gossip._publish_issue_event(configuration, "topic", _envelope(), "kanbus-1")
    gossip.finish_pending_realtime_publishes()
    assert len(published) == 1


def test_missing_console_hub_socket_is_ignored(monkeypatch, tmp_path) -> None:
    def refuse(*_args, **_kwargs) -> None:
        raise OSError("no hub")

    monkeypatch.setattr(gossip, "_publish_uds", refuse)
    configuration = _configuration("auto", transport="uds")
    configuration.realtime.uds_socket_path = str(tmp_path / "missing.sock")
    gossip._publish_issue_event(configuration, "topic", _envelope(), "kanbus-1")


def test_daemon_handler_survives_a_connection_error() -> None:
    class BrokenConnectionHandler(daemon_server.DaemonRequestHandler):
        def __init__(self) -> None:
            self.rfile = io.BytesIO(b"{}\n")

        def _serve_connection(self) -> None:
            raise BrokenPipeError("client went away")

    BrokenConnectionHandler().handle()


def test_daemon_connection_timeouts_are_bounded() -> None:
    assert daemon_client.DAEMON_CONNECT_TIMEOUT_SECONDS <= 1.0
    assert daemon_client.DAEMON_REQUEST_TIMEOUT_SECONDS <= 30.0
    assert daemon_server.DaemonRequestHandler.timeout == (
        daemon_server.DAEMON_CONNECTION_TIMEOUT_SECONDS
    )
