"""Realtime gossip transport and envelope helpers."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import threading
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.models import IssueData, ProjectConfiguration, RealtimeConfig
from kanbus.overlay import OverlayTombstone, write_overlay_issue, write_tombstone
from kanbus.project import (
    ProjectMarkerError,
    get_configuration_path,
    resolve_labeled_projects,
)


class GossipEnvelope(BaseModel):
    """Realtime gossip envelope."""

    id: str = Field(min_length=1)
    ts: str = Field(min_length=1)
    project: str = Field(min_length=1)
    type: str = Field(min_length=1)
    issue_id: Optional[str] = None
    event_id: Optional[str] = None
    producer_id: str = Field(min_length=1)
    origin_cluster_id: Optional[str] = None
    issue: Optional[IssueData] = None


@dataclass(frozen=True)
class BrokerEndpoint:
    """Resolved broker endpoint."""

    scheme: str
    host: str
    port: int
    url: str


@dataclass(frozen=True)
class BrokerStartup:
    """Mosquitto startup result."""

    endpoint: BrokerEndpoint
    process: subprocess.Popen


class GossipError(RuntimeError):
    """Raised when gossip operations fail."""


_PRODUCER_ID: Optional[str] = None


def producer_id() -> str:
    """Return the producer id for this process."""
    global _PRODUCER_ID
    if _PRODUCER_ID is None:
        _PRODUCER_ID = str(uuid4())
    return _PRODUCER_ID


class DedupeSet:
    """In-memory dedupe set with TTL."""

    def __init__(self, ttl_s: int) -> None:
        self.ttl_s = ttl_s
        self._entries: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        now = time.monotonic()
        self._prune(now)
        if key in self._entries:
            return True
        self._entries[key] = now
        return False

    def _prune(self, now: float) -> None:
        ttl = self.ttl_s
        expired = [key for key, ts in self._entries.items() if now - ts > ttl]
        for key in expired:
            self._entries.pop(key, None)


def publish_issue_mutation(
    root: Path,
    project_dir: Path,
    issue: IssueData,
    event_id: Optional[str],
    event_type: str,
) -> None:
    """Publish a gossip envelope for an issue mutation."""
    try:
        configuration = load_project_configuration(get_configuration_path(root))
    except (ProjectMarkerError, ConfigurationError):
        return
    if configuration.realtime.broker == "off":
        return
    project_label = _resolve_project_label(root, project_dir, configuration)
    if project_label is None:
        return
    envelope = GossipEnvelope(
        id=str(uuid4()),
        ts=_now_iso(),
        project=project_label,
        type=event_type,
        issue_id=issue.identifier,
        event_id=event_id,
        producer_id=producer_id(),
        issue=issue,
    )
    topic = configuration.realtime.topics.project_events.format(project=project_label)
    try:
        _publish_envelope(root, configuration, topic, envelope)
    except Exception as error:  # noqa: BLE001
        print(
            f"warning: realtime publish failed for {issue.identifier}: {error}",
            file=sys.stderr,
        )


def publish_issue_deleted(
    root: Path,
    project_dir: Path,
    issue_id: str,
    event_id: Optional[str],
) -> None:
    """Publish a gossip envelope for an issue deletion."""
    try:
        configuration = load_project_configuration(get_configuration_path(root))
    except (ProjectMarkerError, ConfigurationError):
        return
    if configuration.realtime.broker == "off":
        return
    project_label = _resolve_project_label(root, project_dir, configuration)
    if project_label is None:
        return
    envelope = GossipEnvelope(
        id=str(uuid4()),
        ts=_now_iso(),
        project=project_label,
        type="issue.deleted",
        issue_id=issue_id,
        event_id=event_id,
        producer_id=producer_id(),
    )
    topic = configuration.realtime.topics.project_events.format(project=project_label)
    try:
        _publish_envelope(root, configuration, topic, envelope)
    except Exception as error:  # noqa: BLE001
        print(
            f"warning: realtime publish failed for {issue_id}: {error}",
            file=sys.stderr,
        )


def run_gossip_watch(
    root: Path,
    project_filter: Optional[str],
    transport_override: Optional[str],
    broker_override: Optional[str],
    autostart_override: Optional[bool],
    keepalive_override: Optional[bool],
    print_envelopes: bool,
) -> None:
    """Subscribe to gossip notifications and update overlays."""
    _run_gossip_consumer(
        root,
        project_filter,
        transport_override,
        broker_override,
        autostart_override,
        keepalive_override,
        print_envelopes,
        on_envelope=None,
        autostart_local_uds=False,
        broker_off_is_error=True,
    )


def run_gossip_bridge(
    root: Path,
    on_envelope: Callable[[GossipEnvelope], None],
) -> None:
    """Subscribe to gossip notifications for console bridging."""
    _run_gossip_consumer(
        root,
        project_filter=None,
        transport_override=None,
        broker_override=None,
        autostart_override=None,
        keepalive_override=None,
        print_envelopes=False,
        on_envelope=on_envelope,
        autostart_local_uds=True,
        broker_off_is_error=False,
    )


def _run_gossip_consumer(
    root: Path,
    project_filter: Optional[str],
    transport_override: Optional[str],
    broker_override: Optional[str],
    autostart_override: Optional[bool],
    keepalive_override: Optional[bool],
    print_envelopes: bool,
    on_envelope: Optional[Callable[[GossipEnvelope], None]],
    autostart_local_uds: bool,
    broker_off_is_error: bool,
) -> None:
    """Shared consumer loop used by watch mode and console bridge."""
    configuration = load_project_configuration(get_configuration_path(root))
    realtime = configuration.realtime
    transport = transport_override or realtime.transport
    broker = broker_override or realtime.broker
    autostart = autostart_override if autostart_override is not None else realtime.autostart
    keepalive = keepalive_override if keepalive_override is not None else realtime.keepalive

    labeled = resolve_labeled_projects(root)
    if project_filter:
        labeled = [project for project in labeled if project.label == project_filter]
        if not labeled:
            raise GossipError(f"unknown project label: {project_filter}")

    topics = [
        realtime.topics.project_events.format(project=project.label)
        for project in labeled
    ]
    dedupe = DedupeSet(ttl_s=3600)

    def handler(envelope: GossipEnvelope) -> None:
        if dedupe.seen(envelope.id):
            return
        if envelope.producer_id == producer_id():
            return
        target_project = _resolve_project_dir(root, envelope.project)
        if target_project is None:
            return
        if print_envelopes:
            print(json.dumps(envelope.model_dump(mode="json"), sort_keys=False))
        if configuration.overlay.enabled:
            if envelope.type == "issue.mutated" and envelope.issue is not None:
                write_overlay_issue(
                    target_project,
                    envelope.issue,
                    envelope.ts,
                    envelope.event_id,
                )
            elif envelope.type == "issue.deleted" and envelope.issue_id:
                tombstone = OverlayTombstone(
                    op="delete",
                    project=envelope.project,
                    id=envelope.issue_id,
                    event_id=envelope.event_id,
                    ts=envelope.ts,
                    ttl_s=configuration.overlay.ttl_s,
                )
                write_tombstone(target_project, tombstone)
        if on_envelope is not None:
            on_envelope(envelope)

    use_uds = transport == "uds" or (
        transport == "auto" and _uds_socket_path(realtime).exists()
    )
    if autostart_local_uds and not use_uds and transport in {"auto", "uds"}:
        _ensure_local_uds_broker(realtime)
        use_uds = True
    if use_uds:
        run_uds_subscription(realtime, topics, handler)
        return
    if broker == "off":
        if broker_off_is_error:
            raise GossipError("realtime broker is disabled")
        return
    endpoint = resolve_broker_endpoint(broker)
    broker_process = None
    if not broker_is_reachable(endpoint):
        if broker == "auto":
            endpoint = _parse_broker_url("mqtt://127.0.0.1:1883")
        if not autostart:
            raise GossipError("broker not reachable and autostart disabled")
        startup = ensure_mosquitto(endpoint)
        if startup is None:
            _print_mosquitto_missing()
            return
        endpoint = startup.endpoint
        broker_process = startup.process
    run_mqtt_subscription(endpoint, topics, handler)
    if broker_process is not None and not keepalive:
        broker_process.terminate()


def _ensure_local_uds_broker(realtime: RealtimeConfig) -> None:
    socket_path = _uds_socket_path(realtime)
    if socket_path.exists():
        return
    broker_socket = socket_path
    threading.Thread(
        target=run_uds_broker,
        args=(broker_socket,),
        daemon=True,
    ).start()
    for _ in range(20):
        if socket_path.exists():
            return
        time.sleep(0.05)
    raise GossipError(f"failed to start local UDS broker at {socket_path}")


def run_gossip_broker(root: Path, socket_override: Optional[Path]) -> None:
    """Run a UDS gossip broker."""
    socket_path = socket_override
    if socket_path is None:
        try:
            configuration = load_project_configuration(get_configuration_path(root))
            socket_path = _uds_socket_path(configuration.realtime)
        except (ProjectMarkerError, ConfigurationError):
            socket_path = _uds_socket_path()
    run_uds_broker(socket_path)


def run_uds_broker(socket_path: Path) -> None:
    """Run the Unix domain socket gossip broker."""
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(64)
    subscribers: list[tuple[str, socket.socket]] = []
    lock = threading.Lock()
    while True:
        conn, _addr = server.accept()
        conn.settimeout(5.0)
        thread = threading.Thread(
            target=_handle_uds_connection, args=(conn, subscribers, lock), daemon=True
        )
        thread.start()


def _handle_uds_connection(
    conn: socket.socket,
    subscribers: list[tuple[str, socket.socket]],
    lock: threading.Lock,
) -> None:
    buffer = b""
    while True:
        try:
            chunk = conn.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                payload = json.loads(line.decode())
            except json.JSONDecodeError:
                continue
            op = payload.get("op")
            if op == "sub":
                topic = payload.get("topic")
                if isinstance(topic, str):
                    with lock:
                        subscribers.append((topic, conn))
            elif op == "pub":
                _broadcast_payload(payload, subscribers, lock)


def _broadcast_payload(
    payload: dict,
    subscribers: list[tuple[str, socket.socket]],
    lock: threading.Lock,
) -> None:
    topic = payload.get("topic")
    if not isinstance(topic, str):
        return
    message = {"topic": topic, "msg": payload.get("msg")}
    data = (json.dumps(message) + "\n").encode()
    remaining: list[tuple[str, socket.socket]] = []
    with lock:
        current = list(subscribers)
    for sub_topic, sock in current:
        if sub_topic != topic:
            remaining.append((sub_topic, sock))
            continue
        try:
            sock.sendall(data)
            remaining.append((sub_topic, sock))
        except OSError:
            continue
    with lock:
        subscribers[:] = remaining


def run_uds_subscription(
    realtime: RealtimeConfig,
    topics: list[str],
    handler: Callable[[GossipEnvelope], None],
) -> None:
    socket_path = _uds_socket_path(realtime)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))
        for topic in topics:
            payload = json.dumps({"op": "sub", "topic": topic}) + "\n"
            sock.sendall(payload.encode())
        buffer = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line.decode())
                    envelope = GossipEnvelope.model_validate(payload.get("msg", {}))
                except (json.JSONDecodeError, ValidationError):
                    continue
                handler(envelope)


def _publish_envelope(
    root: Path, configuration: ProjectConfiguration, topic: str, envelope: GossipEnvelope
) -> None:
    transport = configuration.realtime.transport
    broker = configuration.realtime.broker
    autostart = configuration.realtime.autostart
    keepalive = configuration.realtime.keepalive
    if transport == "uds" or (
        transport == "auto" and _uds_socket_path(configuration.realtime).exists()
    ):
        try:
            _publish_uds(topic, envelope, configuration.realtime)
        except OSError:
            return
        return
    if broker == "off":
        return
    endpoint = resolve_broker_endpoint(broker)
    broker_process = None
    if not broker_is_reachable(endpoint):
        if broker == "auto":
            endpoint = _parse_broker_url("mqtt://127.0.0.1:1883")
        if not autostart:
            return
        startup = ensure_mosquitto(endpoint)
        if startup is None:
            _print_mosquitto_missing()
            return
        endpoint = startup.endpoint
        broker_process = startup.process
    _publish_mqtt(endpoint, topic, envelope)
    if broker_process is not None and not keepalive:
        broker_process.terminate()


def _publish_uds(topic: str, envelope: GossipEnvelope, realtime: RealtimeConfig) -> None:
    socket_path = _uds_socket_path(realtime)
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
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2.0)
        sock.connect(str(socket_path))
        sock.sendall(payload.encode())


def resolve_broker_endpoint(broker: str) -> BrokerEndpoint:
    if broker == "auto":
        metadata = _load_broker_metadata()
        if metadata:
            return _parse_broker_url(metadata.get("endpoint", "mqtt://127.0.0.1:1883"))
        return _parse_broker_url("mqtt://127.0.0.1:1883")
    return _parse_broker_url(broker)


def broker_is_reachable(endpoint: BrokerEndpoint) -> bool:
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=1.0):
            return True
    except OSError:
        return False


def ensure_mosquitto(endpoint: BrokerEndpoint) -> Optional[BrokerStartup]:
    if endpoint.scheme != "mqtt":
        return None
    if endpoint.host not in ("127.0.0.1", "localhost"):
        return None
    if not _mosquitto_available():
        return None
    run_dir = _broker_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    port = endpoint.port if endpoint.port > 0 else 1883
    port = _find_free_port(port)
    conf_path = run_dir / "mosquitto.conf"
    log_path = run_dir / "mosquitto.log"
    conf_path.write_text(
        "\n".join(
            [
                f"listener {port} 127.0.0.1",
                "allow_anonymous true",
                f"log_dest file {log_path}",
                "persistence false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        ["mosquitto", "-c", str(conf_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    metadata = {
        "kind": "mosquitto",
        "endpoint": f"mqtt://127.0.0.1:{port}",
        "pid": process.pid,
        "started_by": "kanbus",
        "started_at": _now_iso(),
        "log_path": str(log_path),
        "conf_path": str(conf_path),
        "ttl_s": 86400,
    }
    _write_broker_metadata(metadata)
    return BrokerStartup(
        endpoint=_parse_broker_url(metadata["endpoint"]),
        process=process,
    )


def _mosquitto_available() -> bool:
    return bool(shutil.which("mosquitto"))


def _find_free_port(start_port: int) -> int:
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1


def _publish_mqtt(endpoint: BrokerEndpoint, topic: str, envelope: GossipEnvelope) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return
    client = mqtt.Client(client_id=producer_id())
    if endpoint.scheme == "mqtts":
        client.tls_set()
    client.connect(endpoint.host, endpoint.port, 30)
    client.loop_start()
    payload = envelope.model_dump(by_alias=True, mode="json")
    result = client.publish(topic, json.dumps(payload))
    result.wait_for_publish(timeout=2.0)
    client.loop_stop()
    client.disconnect()


def run_mqtt_subscription(
    endpoint: BrokerEndpoint,
    topics: list[str],
    handler: Callable[[GossipEnvelope], None],
) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise GossipError("paho-mqtt is required for MQTT transport") from exc

    client = mqtt.Client(client_id=producer_id())
    if endpoint.scheme == "mqtts":
        client.tls_set()

    def on_message(_client: mqtt.Client, _userdata: object, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode())
            envelope = GossipEnvelope.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return
        handler(envelope)

    client.on_message = on_message
    client.connect(endpoint.host, endpoint.port, 30)
    for topic in topics:
        client.subscribe(topic)
    client.loop_forever()


def _resolve_project_label(
    root: Path, project_dir: Path, configuration: ProjectConfiguration
) -> Optional[str]:
    labeled = resolve_labeled_projects(root)
    for project in labeled:
        if project.project_dir == project_dir:
            return project.label
    return configuration.project_key


def _resolve_project_dir(root: Path, label: str) -> Optional[Path]:
    for project in resolve_labeled_projects(root):
        if project.label == label:
            return project.project_dir
    return None


def _uds_socket_path(realtime: Optional[RealtimeConfig] = None) -> Path:
    if realtime and realtime.uds_socket_path:
        return Path(realtime.uds_socket_path)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "kanbus" / "bus.sock"
    return Path.home() / ".kanbus" / "run" / "bus.sock"


def _parse_broker_url(url: str) -> BrokerEndpoint:
    if "://" not in url:
        raise GossipError(f"invalid broker url: {url}")
    scheme, rest = url.split("://", 1)
    host_port = rest.split("/", 1)[0]
    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 1883
    return BrokerEndpoint(scheme=scheme, host=host, port=port, url=url)


def _broker_run_dir() -> Path:
    return Path.home() / ".kanbus" / "run"


def _load_broker_metadata() -> dict | None:
    metadata_path = _broker_run_dir() / "broker.json"
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_broker_metadata(metadata: dict) -> None:
    run_dir = _broker_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "broker.json"
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _print_mosquitto_missing() -> None:
    print(
        "Mosquitto not found. Install with: brew install mosquitto (macOS) "
        "or apt install mosquitto (Debian/Ubuntu).",
        file=sys.stderr,
    )
