"""Tests for daemon client helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid

import pytest

from taskulus.daemon_client import (
    DaemonClientError,
    _request_with_recovery,
    is_daemon_enabled,
    request_index_list,
    request_shutdown,
    request_status,
    send_request,
)
from taskulus.daemon_protocol import RequestEnvelope, ResponseEnvelope
from taskulus.daemon_server import DaemonServer
from taskulus.config import write_default_configuration
from taskulus.issue_files import write_issue_to_file
from taskulus.models import IssueData


def test_is_daemon_enabled_default() -> None:
    assert is_daemon_enabled()


def test_is_daemon_enabled_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASKULUS_NO_DAEMON", "1")
    assert not is_daemon_enabled()


def test_request_status_rejects_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TASKULUS_NO_DAEMON", "true")
    with pytest.raises(DaemonClientError, match="daemon disabled"):
        request_status(tmp_path)


def test_request_shutdown_rejects_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TASKULUS_NO_DAEMON", "yes")
    with pytest.raises(DaemonClientError, match="daemon disabled"):
        request_shutdown(tmp_path)


def test_request_with_recovery_spawns_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, int] = {"send": 0, "spawn": 0}

    def fake_send_request(
        socket_path: Path, request: RequestEnvelope
    ) -> ResponseEnvelope:
        calls["send"] += 1
        if calls["send"] == 1:
            raise DaemonClientError("boom")
        return ResponseEnvelope(
            protocol_version="1.0",
            request_id=request.request_id,
            status="ok",
            result={},
            error=None,
        )

    def fake_spawn_daemon(root: Path) -> None:
        calls["spawn"] += 1

    socket_path = tmp_path / "taskulus.sock"
    socket_path.write_text("stale", encoding="utf-8")
    request = RequestEnvelope(
        protocol_version="1.0",
        request_id="req-1234",
        action="ping",
        payload={},
    )

    monkeypatch.setattr("taskulus.daemon_client.send_request", fake_send_request)
    monkeypatch.setattr("taskulus.daemon_client.spawn_daemon", fake_spawn_daemon)

    response = _request_with_recovery(socket_path, request, tmp_path)

    assert response.status == "ok"
    assert calls["send"] == 2
    assert calls["spawn"] == 1
    assert not socket_path.exists()


def _make_short_root() -> Path:
    root = Path("/tmp") / f"taskulus-daemon-client-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    marker = root / ".taskulus.yaml"
    marker.write_text("project_dir: project\n", encoding="utf-8")
    project_path = root / "project"
    (project_path / "issues").mkdir(parents=True)
    write_default_configuration(project_path / "config.yaml")
    return root


def _write_issue(root: Path, identifier: str) -> None:
    now = datetime.now(timezone.utc)
    issue = IssueData(
        id=identifier,
        title="Title",
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
    issue_path = root / "project" / "issues" / f"{identifier}.json"
    write_issue_to_file(issue, issue_path)


def _start_server(root: Path, monkeypatch: pytest.MonkeyPatch) -> DaemonServer:
    monkeypatch.setattr(
        "taskulus.daemon_server.get_daemon_socket_path",
        lambda value: value / "taskulus.sock",
    )
    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path",
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
    return server


def test_send_request_success(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_short_root()
    _write_issue(root, "tsk-1")
    server = _start_server(root, monkeypatch)
    request = RequestEnvelope(
        protocol_version="1.0",
        request_id="req-1",
        action="ping",
        payload={},
    )
    response = send_request(root / "taskulus.sock", request)
    assert response.status == "ok"
    server.shutdown()
    server.server_close()
    shutil.rmtree(root)


def test_send_request_raises_on_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_socket(*_args: object, **_kwargs: object) -> object:
        raise OSError("boom")

    monkeypatch.setattr("taskulus.daemon_client.socket.socket", fake_socket)

    request = RequestEnvelope(
        protocol_version="1.0",
        request_id="req-2",
        action="ping",
        payload={},
    )

    with pytest.raises(DaemonClientError, match="daemon connection failed"):
        send_request(tmp_path / "taskulus.sock", request)


def test_send_request_raises_on_empty_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FakeFile:
        def readline(self) -> bytes:
            return b""

    class _FakeSocket:
        def __enter__(self) -> "_FakeSocket":
            return self

        def __exit__(self, _exc_type: object, _exc: object, _exc_tb: object) -> None:
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def connect(self, _path: str) -> None:
            return None

        def sendall(self, _payload: bytes) -> None:
            return None

        def makefile(self, _mode: str) -> _FakeFile:
            return _FakeFile()

    monkeypatch.setattr(
        "taskulus.daemon_client.socket.socket", lambda *_a, **_k: _FakeSocket()
    )

    request = RequestEnvelope(
        protocol_version="1.0",
        request_id="req-3",
        action="ping",
        payload={},
    )

    with pytest.raises(DaemonClientError, match="empty daemon response"):
        send_request(tmp_path / "taskulus.sock", request)


def test_request_index_list_success(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_short_root()
    _write_issue(root, "tsk-1")
    server = _start_server(root, monkeypatch)
    issues = request_index_list(root)
    assert issues[0]["id"] == "tsk-1"
    server.shutdown()
    server.server_close()
    shutil.rmtree(root)


def test_spawn_daemon_invokes_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, list[object]] = {"args": []}

    def fake_popen(args: list[str], **_kwargs: object) -> None:
        calls["args"].append(args)
        return None

    monkeypatch.setattr("taskulus.daemon_client.subprocess.Popen", fake_popen)

    from taskulus.daemon_client import spawn_daemon

    spawn_daemon(tmp_path)

    assert calls["args"]
    assert calls["args"][0][0] == sys.executable


def test_request_index_list_spawns_when_socket_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    socket_path = tmp_path / "taskulus.sock"
    calls: dict[str, int] = {"spawn": 0}

    def fake_spawn(root: Path) -> None:
        calls["spawn"] += 1

    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-4",
        status="ok",
        result={"issues": []},
        error=None,
    )

    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path", lambda _root: socket_path
    )
    monkeypatch.setattr("taskulus.daemon_client.spawn_daemon", fake_spawn)
    monkeypatch.setattr(
        "taskulus.daemon_client._request_with_recovery", lambda *_a: response
    )

    issues = request_index_list(tmp_path)

    assert issues == []
    assert calls["spawn"] == 1


def test_request_index_list_raises_on_error_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    socket_path = tmp_path / "taskulus.sock"
    socket_path.write_text("socket", encoding="utf-8")
    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-5",
        status="error",
        result=None,
        error=None,
    )
    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path", lambda _root: socket_path
    )
    monkeypatch.setattr(
        "taskulus.daemon_client._request_with_recovery", lambda *_a: response
    )

    with pytest.raises(DaemonClientError, match="daemon error"):
        request_index_list(tmp_path)


def test_request_status_raises_on_error_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-6",
        status="error",
        result=None,
        error=None,
    )
    monkeypatch.delenv("TASKULUS_NO_DAEMON", raising=False)
    monkeypatch.setattr(
        "taskulus.daemon_client._request_with_recovery", lambda *_a: response
    )
    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path", lambda _root: tmp_path / "sock"
    )

    with pytest.raises(DaemonClientError, match="daemon error"):
        request_status(tmp_path)


def test_request_status_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-8",
        status="ok",
        result={"status": "ok"},
        error=None,
    )
    monkeypatch.delenv("TASKULUS_NO_DAEMON", raising=False)
    monkeypatch.setattr(
        "taskulus.daemon_client._request_with_recovery", lambda *_a: response
    )
    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path", lambda _root: tmp_path / "sock"
    )

    result = request_status(tmp_path)
    assert result["status"] == "ok"


def test_request_shutdown_raises_on_error_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-7",
        status="error",
        result=None,
        error=None,
    )
    monkeypatch.delenv("TASKULUS_NO_DAEMON", raising=False)
    monkeypatch.setattr(
        "taskulus.daemon_client._request_with_recovery", lambda *_a: response
    )
    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path", lambda _root: tmp_path / "sock"
    )

    with pytest.raises(DaemonClientError, match="daemon error"):
        request_shutdown(tmp_path)


def test_request_shutdown_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-9",
        status="ok",
        result={"status": "stopped"},
        error=None,
    )
    monkeypatch.delenv("TASKULUS_NO_DAEMON", raising=False)
    monkeypatch.setattr(
        "taskulus.daemon_client._request_with_recovery", lambda *_a: response
    )
    monkeypatch.setattr(
        "taskulus.daemon_client.get_daemon_socket_path", lambda _root: tmp_path / "sock"
    )

    result = request_shutdown(tmp_path)
    assert result["status"] == "stopped"
