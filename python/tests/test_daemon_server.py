"""Tests for daemon server request handling."""

from __future__ import annotations

import json
import shutil
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from taskulus.config import write_default_configuration
from taskulus.daemon_protocol import PROTOCOL_VERSION
from taskulus.daemon_server import DaemonServer, run_daemon
from taskulus.issue_files import write_issue_to_file
from taskulus.models import IssueData


def _write_project(root: Path) -> Path:
    marker = root / ".taskulus.yaml"
    marker.write_text("project_dir: project\n", encoding="utf-8")
    project_path = root / "project"
    (project_path / "issues").mkdir(parents=True)
    write_default_configuration(project_path / "config.yaml")
    return project_path


def _make_issue(identifier: str) -> IssueData:
    now = datetime.now(timezone.utc)
    return IssueData(
        id=identifier,
        title="Test",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        description="",
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )


def _send_request(socket_path: Path, payload: dict[str, object]) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))
        sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        response_raw = sock.makefile("rb").readline()
    return json.loads(response_raw.decode("utf-8"))


def _make_short_root() -> Path:
    root = Path("/tmp") / f"taskulus-daemon-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_daemon_server_handles_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_short_root()
    project = _write_project(root)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")

    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda root: root / "taskulus.sock",
    )

    server = DaemonServer(root)
    server.warm_start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    socket_path = root / "taskulus.sock"
    timeout = time.time() + 2
    while not socket_path.exists():
        if time.time() > timeout:
            raise RuntimeError("socket not created")
        time.sleep(0.01)

    response = _send_request(
        socket_path,
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "req-1",
            "action": "ping",
            "payload": {},
        },
    )
    assert response["status"] == "ok"

    response = _send_request(
        socket_path,
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "req-2",
            "action": "index.list",
            "payload": {},
        },
    )
    assert response["status"] == "ok"
    assert response["result"]["issues"][0]["id"] == "tsk-1"

    response = _send_request(
        socket_path,
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "req-3",
            "action": "unknown",
            "payload": {},
        },
    )
    assert response["status"] == "error"
    assert response["error"]["code"] == "unknown_action"

    response = _send_request(
        socket_path,
        {
            "protocol_version": "2.0",
            "request_id": "req-4",
            "action": "ping",
            "payload": {},
        },
    )
    assert response["status"] == "error"
    assert response["error"]["code"] == "protocol_version_mismatch"

    response = _send_request(
        socket_path,
        {
            "protocol_version": "1.1",
            "request_id": "req-5",
            "action": "ping",
            "payload": {},
        },
    )
    assert response["status"] == "error"
    assert response["error"]["code"] == "protocol_version_unsupported"

    response = _send_request(
        socket_path,
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "req-6",
            "action": "shutdown",
            "payload": {},
        },
    )
    assert response["status"] == "ok"

    server.shutdown()
    server.server_close()
    shutil.rmtree(root)


def test_daemon_server_handles_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_short_root()
    _write_project(root)
    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda root: root / "taskulus.sock",
    )
    server = DaemonServer(root)
    server.warm_start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    socket_path = root / "taskulus.sock"
    timeout = time.time() + 2
    while not socket_path.exists():
        if time.time() > timeout:
            raise RuntimeError("socket not created")
        time.sleep(0.01)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))
        sock.sendall(b"{not-json}\n")
        response_raw = sock.makefile("rb").readline()

    response = json.loads(response_raw.decode("utf-8"))
    assert response["status"] == "error"
    assert response["error"]["code"] == "internal_error"

    server.shutdown()
    server.server_close()
    shutil.rmtree(root)


def test_daemon_server_unlinks_existing_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_short_root()
    _write_project(root)
    socket_path = root / "taskulus.sock"
    socket_path.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda value: value / "taskulus.sock",
    )
    server = DaemonServer(root)
    assert socket_path.exists()
    server.server_close()
    shutil.rmtree(root)


def test_daemon_server_warm_start_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_short_root()
    project = _write_project(root)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    cached_index = type("Index", (), {"by_id": {issue.identifier: issue}})()
    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda value: value / "taskulus.sock",
    )
    monkeypatch.setattr(
        "taskulus.daemon_server.load_cache_if_valid",
        lambda cache_path, issues_dir: cached_index,
    )
    server = DaemonServer(root)
    server.warm_start()
    assert server.state.index is not None
    server.server_close()
    shutil.rmtree(root)


def test_daemon_server_load_index_rebuilds(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_short_root()
    project = _write_project(root)
    issue = _make_issue("tsk-1")
    write_issue_to_file(issue, project / "issues" / "tsk-1.json")
    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda value: value / "taskulus.sock",
    )
    server = DaemonServer(root)
    server.warm_start()
    cache_path = project / ".cache" / "index.json"
    if cache_path.exists():
        cache_path.unlink()
    issues = server._load_index()
    assert issues[0].identifier == "tsk-1"
    server.server_close()
    shutil.rmtree(root)


def test_daemon_server_handles_empty_request(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_short_root()
    _write_project(root)
    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda value: value / "taskulus.sock",
    )
    server = DaemonServer(root)
    server.warm_start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    socket_path = root / "taskulus.sock"
    timeout = time.time() + 2
    while not socket_path.exists():
        if time.time() > timeout:
            raise RuntimeError("socket not created")
        time.sleep(0.01)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))
        sock.shutdown(socket.SHUT_WR)
    server.shutdown()
    server.server_close()
    shutil.rmtree(root)


def test_run_daemon_invokes_server(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeServer:
        def __init__(self, root: Path) -> None:
            calls.append(root)

        def __enter__(self) -> "FakeServer":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def warm_start(self) -> None:
            calls.append("warm")

        def serve_forever(self) -> None:
            calls.append("serve")

    monkeypatch.setattr("taskulus.daemon_server.DaemonServer", FakeServer)
    run_daemon(Path("/tmp"))
    assert calls == [Path("/tmp"), "warm", "serve"]
