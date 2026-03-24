from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import daemon_client
from kanbus.daemon_protocol import ErrorEnvelope, ResponseEnvelope


def ok_response(request_id: str, result: dict | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(
        protocol_version="1.0",
        request_id=request_id,
        status="ok",
        result=result or {},
    )


def error_response(request_id: str, message: str) -> ResponseEnvelope:
    return ResponseEnvelope(
        protocol_version="1.0",
        request_id=request_id,
        status="error",
        error=ErrorEnvelope(code="internal_error", message=message, details={}),
    )


def test_is_daemon_enabled_env_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    assert daemon_client.is_daemon_enabled() is True
    for value in ["1", "true", "yes", "TRUE", "Yes"]:
        monkeypatch.setenv("KANBUS_NO_DAEMON", value)
        assert daemon_client.is_daemon_enabled() is False
    monkeypatch.setenv("KANBUS_NO_DAEMON", "0")
    assert daemon_client.is_daemon_enabled() is True


def test_request_index_list_happy_path_and_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    socket_path = root / "sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(daemon_client, "get_daemon_socket_path", lambda _r: socket_path)
    monkeypatch.setattr(
        daemon_client,
        "spawn_daemon",
        lambda _r: (_ for _ in ()).throw(RuntimeError("should not spawn")),
    )
    monkeypatch.setattr(
        daemon_client,
        "_request_with_recovery",
        lambda _s, request, _r: ok_response(
            request.request_id, {"issues": [{"id": "kanbus-1"}]}
        ),
    )
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)

    issues = daemon_client.request_index_list(root)
    assert issues == [{"id": "kanbus-1"}]

    monkeypatch.setenv("KANBUS_NO_DAEMON", "1")
    with pytest.raises(daemon_client.DaemonClientError, match="daemon disabled"):
        daemon_client.request_index_list(root)


def test_request_index_list_spawns_when_socket_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    socket_path = root / "missing.sock"
    spawned: dict[str, bool] = {}
    monkeypatch.setattr(daemon_client, "get_daemon_socket_path", lambda _r: socket_path)
    monkeypatch.setattr(
        daemon_client,
        "spawn_daemon",
        lambda _r: spawned.setdefault("spawned", True),
    )
    monkeypatch.setattr(
        daemon_client,
        "_request_with_recovery",
        lambda _s, request, _r: ok_response(request.request_id, {"issues": []}),
    )
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    daemon_client.request_index_list(root)
    assert spawned.get("spawned") is True


def test_request_index_list_error_response_uses_envelope_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    socket_path = root / "sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(daemon_client, "get_daemon_socket_path", lambda _r: socket_path)
    monkeypatch.setattr(
        daemon_client,
        "_request_with_recovery",
        lambda _s, request, _r: error_response(request.request_id, "daemon boom"),
    )
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    with pytest.raises(daemon_client.DaemonClientError, match="daemon boom"):
        daemon_client.request_index_list(root)


def test_request_status_and_shutdown_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    socket_path = root / "sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(daemon_client, "get_daemon_socket_path", lambda _r: socket_path)

    def responder(_s: Path, request: object, _r: Path) -> ResponseEnvelope:
        req = request  # type: ignore[assignment]
        if req.action == "ping":
            return ok_response(req.request_id, {"status": "ok"})
        return ok_response(req.request_id, {"stopped": True})

    monkeypatch.setattr(daemon_client, "_request_with_recovery", responder)
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    assert daemon_client.request_status(root) == {"status": "ok"}
    assert daemon_client.request_shutdown(root) == {"stopped": True}

    monkeypatch.setenv("KANBUS_NO_DAEMON", "true")
    with pytest.raises(daemon_client.DaemonClientError, match="daemon disabled"):
        daemon_client.request_status(root)
    with pytest.raises(daemon_client.DaemonClientError, match="daemon disabled"):
        daemon_client.request_shutdown(root)


def test_request_status_and_shutdown_error_fallback_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    socket_path = root / "sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(daemon_client, "get_daemon_socket_path", lambda _r: socket_path)
    monkeypatch.setattr(
        daemon_client,
        "_request_with_recovery",
        lambda _s, request, _r: ResponseEnvelope(
            protocol_version="1.0",
            request_id=request.request_id,
            status="error",
            error=None,
        ),
    )
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    with pytest.raises(daemon_client.DaemonClientError, match="daemon error"):
        daemon_client.request_status(root)
    with pytest.raises(daemon_client.DaemonClientError, match="daemon error"):
        daemon_client.request_shutdown(root)


def test_request_with_recovery_non_connection_error_passthrough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "sock"
    request = SimpleNamespace(request_id="req-1")
    monkeypatch.setattr(
        daemon_client,
        "send_request",
        lambda *_a: (_ for _ in ()).throw(
            daemon_client.DaemonClientError("empty daemon response")
        ),
    )
    with pytest.raises(daemon_client.DaemonClientError, match="empty daemon response"):
        daemon_client._request_with_recovery(socket_path, request, tmp_path)


def test_request_with_recovery_retries_after_connection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "sock"
    socket_path.write_text("", encoding="utf-8")
    request = SimpleNamespace(request_id="req-2")
    attempts = {"count": 0}
    spawned: dict[str, bool] = {}

    def flaky_send(_s: Path, _r: object) -> ResponseEnvelope:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise daemon_client.DaemonClientError("daemon connection failed")
        return ok_response("req-2", {"ok": True})

    monkeypatch.setattr(daemon_client, "send_request", flaky_send)
    monkeypatch.setattr(
        daemon_client,
        "spawn_daemon",
        lambda _r: spawned.setdefault("spawned", True),
    )
    monkeypatch.setattr(daemon_client.time, "sleep", lambda *_a: None)

    response = daemon_client._request_with_recovery(socket_path, request, tmp_path)
    assert response.status == "ok"
    assert spawned.get("spawned") is True
    assert attempts["count"] >= 3
    assert not socket_path.exists()


def test_request_with_recovery_exhausts_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "sock"
    request = SimpleNamespace(request_id="req-3")
    monkeypatch.setattr(
        daemon_client,
        "send_request",
        lambda *_a: (_ for _ in ()).throw(
            daemon_client.DaemonClientError("daemon connection failed")
        ),
    )
    monkeypatch.setattr(daemon_client, "spawn_daemon", lambda _r: None)
    monkeypatch.setattr(daemon_client.time, "sleep", lambda *_a: None)
    with pytest.raises(
        daemon_client.DaemonClientError, match="daemon connection failed"
    ):
        daemon_client._request_with_recovery(socket_path, request, tmp_path)


def test_send_request_success_empty_and_connection_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "sock"
    request = daemon_client.RequestEnvelope(
        protocol_version="1.0",
        request_id="req-1",
        action="ping",
        payload={},
    )

    class FakeFile:
        def __init__(self, data: bytes):
            self._data = data

        def readline(self) -> bytes:
            return self._data

    class FakeSocket:
        def __init__(self, response: bytes):
            self.sent = b""
            self.response = response
            self.connected = None

        def settimeout(self, _timeout: float) -> None:
            pass

        def connect(self, path: str) -> None:
            self.connected = path

        def sendall(self, payload: bytes) -> None:
            self.sent = payload

        def makefile(self, _mode: str):
            return FakeFile(self.response)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    fake = FakeSocket(
        b'{"protocol_version":"1.0","request_id":"req-1","status":"ok","result":{"ok":true}}\n'
    )
    monkeypatch.setattr(daemon_client.socket, "socket", lambda *_a: fake)
    response = daemon_client.send_request(socket_path, request)
    assert response.status == "ok"
    assert response.result == {"ok": True}
    assert fake.connected == str(socket_path)
    assert fake.sent.endswith(b"\n")

    empty = FakeSocket(b"")
    monkeypatch.setattr(daemon_client.socket, "socket", lambda *_a: empty)
    with pytest.raises(daemon_client.DaemonClientError, match="empty daemon response"):
        daemon_client.send_request(socket_path, request)

    def raising_socket(*_a):
        raise OSError("socket down")

    monkeypatch.setattr(daemon_client.socket, "socket", raising_socket)
    with pytest.raises(
        daemon_client.DaemonClientError, match="daemon connection failed"
    ):
        daemon_client.send_request(socket_path, request)


def test_spawn_daemon_invokes_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    captured: dict[str, object] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return None

    monkeypatch.setattr(daemon_client.subprocess, "Popen", fake_popen)
    daemon_client.spawn_daemon(root)
    assert captured["cmd"][0] == daemon_client.sys.executable
    assert captured["cmd"][1:3] == ["-m", "kanbus.daemon"]
    assert captured["kwargs"]["cwd"] == root
    assert captured["kwargs"]["start_new_session"] is True


def test_request_with_recovery_raises_non_connection_error_during_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = tmp_path / "sock"
    request = SimpleNamespace(request_id="req-4")
    state = {"count": 0}

    def flaky_send(_s: Path, _r: object):
        state["count"] += 1
        if state["count"] == 1:
            raise daemon_client.DaemonClientError("daemon connection failed")
        raise daemon_client.DaemonClientError("empty daemon response")

    monkeypatch.setattr(daemon_client, "send_request", flaky_send)
    monkeypatch.setattr(daemon_client, "spawn_daemon", lambda _r: None)
    monkeypatch.setattr(daemon_client.time, "sleep", lambda *_a: None)
    with pytest.raises(daemon_client.DaemonClientError, match="empty daemon response"):
        daemon_client._request_with_recovery(socket_path, request, tmp_path)
