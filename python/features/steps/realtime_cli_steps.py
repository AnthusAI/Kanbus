"""Behave steps for the CLI realtime default scenarios."""

from __future__ import annotations

import json
import os
import socket
import stat
import tempfile
import threading
import time
from pathlib import Path

from behave import given, then, when

from features.steps.shared import run_cli


class StubMqttBroker:
    """A minimal MQTT 3.1.1 broker that records published events."""

    def __init__(self, answering: bool) -> None:
        self.answering = answering
        self.connection_count = 0
        self.published: list[dict] = []
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._listener.settimeout(0.05)
        self.port = self._listener.getsockname()[1]
        self._accept_thread = threading.Thread(target=self._accept, daemon=True)
        self._accept_thread.start()

    @property
    def url(self) -> str:
        return f"mqtt://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self._stopping.set()
        self._accept_thread.join(timeout=2.0)
        self._listener.close()

    def _accept(self) -> None:
        while not self._stopping.is_set():
            try:
                connection, _ = self._listener.accept()
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            with self._lock:
                self.connection_count += 1
            threading.Thread(
                target=self._serve, args=(connection,), daemon=True
            ).start()

    def _serve(self, connection: socket.socket) -> None:
        connection.settimeout(0.1)
        with connection:
            if not self.answering:
                self._stopping.wait()
                return
            while not self._stopping.is_set():
                try:
                    header = connection.recv(1)
                except (TimeoutError, socket.timeout):
                    continue
                except OSError:
                    return
                if not header:
                    return
                connection.settimeout(None)
                length = self._read_remaining_length(connection)
                if length is None:
                    return
                body = self._read_exact(connection, length)
                if body is None:
                    return
                connection.settimeout(0.1)
                packet_type = header[0] >> 4
                if packet_type == 1:
                    connection.sendall(bytes([0x20, 0x02, 0x00, 0x00]))
                elif packet_type == 3:
                    topic_length = int.from_bytes(body[:2], "big")
                    payload = body[2 + topic_length :]
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    with self._lock:
                        self.published.append(event)
                elif packet_type == 12:
                    connection.sendall(bytes([0xD0, 0x00]))
                elif packet_type == 14:
                    return

    @staticmethod
    def _read_exact(connection: socket.socket, length: int) -> bytes | None:
        data = b""
        while len(data) < length:
            chunk = connection.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _read_remaining_length(self, connection: socket.socket) -> int | None:
        multiplier = 1
        value = 0
        while True:
            byte = self._read_exact(connection, 1)
            if byte is None:
                return None
            value += (byte[0] & 0x7F) * multiplier
            if not byte[0] & 0x80:
                return value
            multiplier *= 128


def _closed_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _set_scenario_environment(context: object, name: str, value: str | None) -> None:
    original = os.environ.get(name)

    def restore() -> None:
        if original is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original

    context.add_cleanup(restore)
    overrides = getattr(context, "environment_overrides", None)
    if overrides is None:
        overrides = {}
        context.environment_overrides = overrides
    if value is None:
        os.environ.pop(name, None)
        overrides.pop(name, None)
    else:
        os.environ[name] = value
        overrides[name] = value


def _start_stub_broker(context: object, answering: bool) -> None:
    broker = StubMqttBroker(answering)
    context.add_cleanup(broker.stop)
    context.stub_mqtt_broker = broker


def _write_broker_discovery(context: object, endpoint: str) -> None:
    run_directory = Path(os.environ["HOME"]) / ".kanbus" / "run"
    run_directory.mkdir(parents=True, exist_ok=True)
    path = run_directory / "broker.json"
    path.write_text(
        json.dumps(
            {
                "kind": "mosquitto",
                "endpoint": endpoint,
                "pid": 1,
                "started_by": "kbs",
                "started_at": "2026-01-01T00:00:00.000Z",
                "log_path": "/dev/null",
                "conf_path": "/dev/null",
                "ttl_s": 86400,
            }
        ),
        encoding="utf-8",
    )
    context.add_cleanup(lambda: path.unlink(missing_ok=True))


@given("a stub MQTT broker on a free port")
def given_stub_broker(context: object) -> None:
    _start_stub_broker(context, answering=True)


@given("an MQTT broker on a free port that accepts connections and never answers")
def given_silent_broker(context: object) -> None:
    _start_stub_broker(context, answering=False)


@given("broker discovery points at the stub MQTT broker")
def given_discovery_points_at_stub(context: object) -> None:
    _write_broker_discovery(context, context.stub_mqtt_broker.url)


@given("broker discovery points at a closed port")
def given_discovery_points_at_closed_port(context: object) -> None:
    _write_broker_discovery(context, f"mqtt://127.0.0.1:{_closed_local_port()}")


@given("the realtime broker is the stub MQTT broker")
def given_realtime_broker_is_stub(context: object) -> None:
    _set_scenario_environment(
        context, "KANBUS_REALTIME_BROKER", context.stub_mqtt_broker.url
    )


@given("the realtime broker is a closed port")
def given_realtime_broker_is_closed_port(context: object) -> None:
    _set_scenario_environment(
        context, "KANBUS_REALTIME_BROKER", f"mqtt://127.0.0.1:{_closed_local_port()}"
    )


@given("realtime autostart is requested")
def given_autostart_requested(context: object) -> None:
    _set_scenario_environment(context, "KANBUS_REALTIME_AUTOSTART", "true")


@given("a mosquitto executable that records its launches")
def given_launch_recorder(context: object) -> None:
    directory = tempfile.TemporaryDirectory()
    context.add_cleanup(directory.cleanup)
    marker = Path(directory.name) / "launched"
    script = Path(directory.name) / "mosquitto"
    script.write_text(
        f'#!/bin/sh\necho launched >> "{marker}"\nsleep 1\n', encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    _set_scenario_environment(
        context,
        "PATH",
        f"{directory.name}{os.pathsep}{os.environ.get('PATH', '')}",
    )
    _set_scenario_environment(context, "KANBUS_TEST_MOSQUITTO_UNAVAILABLE", None)
    context.mosquitto_launch_marker = marker


@when('I run "{command}" and time it')
def when_run_and_time(context: object, command: str) -> None:
    started = time.monotonic()
    run_cli(context, command)
    context.last_command_elapsed_seconds = time.monotonic() - started


@then("the command should have finished within {seconds:d} seconds")
def then_finished_within(context: object, seconds: int) -> None:
    elapsed = context.last_command_elapsed_seconds
    assert elapsed <= seconds, f"command took {elapsed:.2f}s, limit {seconds}s"


@then("the stub MQTT broker should have received no connections")
def then_stub_no_connections(context: object) -> None:
    time.sleep(0.3)
    count = context.stub_mqtt_broker.connection_count
    assert count == 0, f"stub broker received {count} connections"


@then(
    'the stub MQTT broker should receive an "{event_type}" event for the issue titled "{title}"'
)
def then_stub_received_event(context: object, event_type: str, title: str) -> None:
    broker = context.stub_mqtt_broker
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        for event in list(broker.published):
            issue = event.get("issue") or {}
            if event.get("type") == event_type and issue.get("title") == title:
                return
        time.sleep(0.025)
    raise AssertionError(
        f"stub broker did not receive {event_type} for {title}: {broker.published}"
    )


@then("no mosquitto launch should have been recorded")
def then_no_launch(context: object) -> None:
    time.sleep(0.3)
    assert not context.mosquitto_launch_marker.exists(), "mosquitto was launched"
