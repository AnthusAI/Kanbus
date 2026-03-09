from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from kanbus import daemon_server
from kanbus.daemon_protocol import ProtocolError, RequestEnvelope, ResponseEnvelope
from kanbus.index import IssueIndex

from test_helpers import build_issue


def test_daemon_core_warm_start_uses_cache_or_builds_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = daemon_server.DaemonCore(root=tmp_path)
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    cache_path = tmp_path / ".cache" / "index.json"
    monkeypatch.setattr(daemon_server, "load_project_directory", lambda _r: project_dir)
    monkeypatch.setattr(daemon_server, "get_index_cache_path", lambda _r: cache_path)

    built_index = IssueIndex(by_id={"kanbus-1": build_issue("kanbus-1")})
    monkeypatch.setattr(daemon_server, "load_cache_if_valid", lambda *_a: None)
    monkeypatch.setattr(daemon_server, "build_index_from_directory", lambda _d: built_index)
    monkeypatch.setattr(daemon_server, "collect_issue_file_mtimes", lambda _d: {"x": 1.0})
    called: dict[str, bool] = {}
    monkeypatch.setattr(
        daemon_server, "write_cache", lambda *_a: called.setdefault("write_cache", True)
    )
    core.warm_start()
    assert core.state.index is built_index
    assert called.get("write_cache") is True

    cached_index = IssueIndex(by_id={"kanbus-cached": build_issue("kanbus-cached")})
    monkeypatch.setattr(daemon_server, "load_cache_if_valid", lambda *_a: cached_index)
    called.clear()
    core.warm_start()
    assert core.state.index is cached_index
    assert called == {}
    assert issues_dir == project_dir / "issues"


def test_daemon_core_handle_request_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = daemon_server.DaemonCore(root=tmp_path)
    issue = build_issue("kanbus-1")
    monkeypatch.setattr(core, "_load_index", lambda: [issue])

    ping = core.handle_request(
        RequestEnvelope(
            protocol_version="1.0",
            request_id="req-ping",
            action="ping",
            payload={},
        )
    )
    assert ping.status == "ok"
    assert ping.result == {"status": "ok"}

    shutdown = core.handle_request(
        RequestEnvelope(
            protocol_version="1.0",
            request_id="req-stop",
            action="shutdown",
            payload={},
        )
    )
    assert shutdown.status == "ok"
    assert shutdown.result == {"status": "stopping"}

    listing = core.handle_request(
        RequestEnvelope(
            protocol_version="1.0",
            request_id="req-list",
            action="index.list",
            payload={},
        )
    )
    assert listing.status == "ok"
    assert listing.result is not None
    assert listing.result["issues"][0]["id"] == "kanbus-1"

    unknown = core.handle_request(
        RequestEnvelope(
            protocol_version="1.0",
            request_id="req-unknown",
            action="nope",
            payload={},
        )
    )
    assert unknown.status == "error"
    assert unknown.error is not None
    assert unknown.error.code == "unknown_action"

    with pytest.raises(ProtocolError, match="protocol version mismatch"):
        core.handle_request(
            RequestEnvelope(
                protocol_version="2.0",
                request_id="req-bad-version",
                action="ping",
                payload={},
            )
        )


def test_daemon_core_load_index_rebuild_and_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = daemon_server.DaemonCore(root=tmp_path)
    project_dir = tmp_path / "project"
    cache_path = tmp_path / ".cache" / "index.json"
    monkeypatch.setattr(daemon_server, "load_project_directory", lambda _r: project_dir)
    monkeypatch.setattr(daemon_server, "get_index_cache_path", lambda _r: cache_path)

    built = IssueIndex(by_id={"kanbus-1": build_issue("kanbus-1")})
    monkeypatch.setattr(daemon_server, "load_cache_if_valid", lambda *_a: None)
    monkeypatch.setattr(daemon_server, "build_index_from_directory", lambda _d: built)
    monkeypatch.setattr(daemon_server, "collect_issue_file_mtimes", lambda _d: {"k": 1.0})
    monkeypatch.setattr(daemon_server, "write_cache", lambda *_a: None)
    assert [issue.identifier for issue in core._load_index()] == ["kanbus-1"]

    cached = IssueIndex(by_id={"kanbus-cached": build_issue("kanbus-cached")})
    monkeypatch.setattr(daemon_server, "load_cache_if_valid", lambda *_a: cached)
    assert [issue.identifier for issue in core._load_index()] == ["kanbus-cached"]


def test_raw_request_and_response_error_helpers(tmp_path: Path) -> None:
    core = daemon_server.DaemonCore(tmp_path)
    response, action = daemon_server._handle_raw_request(core, b"{not-json")
    assert action is None
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "internal_error"

    unsupported = daemon_server._build_protocol_error_response(
        "req-1", ProtocolError("protocol version unsupported")
    )
    assert unsupported.error is not None
    assert unsupported.error.code == "protocol_version_unsupported"

    mismatch = daemon_server._build_protocol_error_response(
        "req-2", ProtocolError("protocol version mismatch")
    )
    assert mismatch.error is not None
    assert mismatch.error.code == "protocol_version_mismatch"

    internal = daemon_server._build_internal_error_response("req-3", RuntimeError("boom"))
    assert internal.error is not None
    assert internal.error.message == "boom"


def test_handle_request_for_testing_and_raw_payload_for_testing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = RequestEnvelope(
        protocol_version="1.0",
        request_id="req-1",
        action="ping",
        payload={},
    )
    monkeypatch.setattr(
        daemon_server.DaemonCore,
        "handle_request",
        lambda _self, _req: ResponseEnvelope(
            protocol_version="1.0",
            request_id="req-1",
            status="ok",
            result={"status": "ok"},
        ),
    )
    response = daemon_server.handle_request_for_testing(tmp_path, request)
    assert response.status == "ok"

    monkeypatch.setattr(
        daemon_server.DaemonCore,
        "handle_request",
        lambda _self, _req: (_ for _ in ()).throw(ProtocolError("protocol version mismatch")),
    )
    response = daemon_server.handle_request_for_testing(tmp_path, request)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "protocol_version_mismatch"

    monkeypatch.setattr(
        daemon_server.DaemonCore,
        "handle_request",
        lambda _self, _req: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    response = daemon_server.handle_request_for_testing(tmp_path, request)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "internal_error"

    payload = json.dumps(request.model_dump(mode="json")).encode("utf-8")
    monkeypatch.setattr(
        daemon_server.DaemonCore,
        "handle_request",
        lambda _self, _req: ResponseEnvelope(
            protocol_version="1.0",
            request_id="req-1",
            status="ok",
            result={"status": "ok"},
        ),
    )
    raw_response = daemon_server.handle_raw_payload_for_testing(tmp_path, payload)
    assert raw_response.status == "ok"


def test_run_daemon_invokes_server_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeServer:
        def __init__(self, _root: Path) -> None:
            calls.append("init")

        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, *_args):
            calls.append("exit")
            return False

        def warm_start(self) -> None:
            calls.append("warm")

        def serve_forever(self) -> None:
            calls.append("serve")

    monkeypatch.setattr(daemon_server, "DaemonServer", FakeServer)
    daemon_server.run_daemon(tmp_path)
    assert calls == ["init", "enter", "warm", "serve", "exit"]


def test_daemon_server_init_and_proxy_methods(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    socket_path = root / ".cache" / "kanbus.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("old", encoding="utf-8")
    monkeypatch.setattr(daemon_server, "get_daemon_socket_path", lambda _r: socket_path)
    captured: dict[str, object] = {}

    def fake_super_init(self, address, handler_cls):
        captured["address"] = address
        captured["handler"] = handler_cls

    monkeypatch.setattr(
        daemon_server.socketserver.ThreadingUnixStreamServer, "__init__", fake_super_init
    )

    server = daemon_server.DaemonServer(root)
    assert isinstance(server.core, daemon_server.DaemonCore)
    assert captured["address"] == str(socket_path)
    assert captured["handler"] is daemon_server.DaemonRequestHandler
    assert not socket_path.exists()

    calls: dict[str, object] = {}
    monkeypatch.setattr(server.core, "warm_start", lambda: calls.setdefault("warm", True))
    monkeypatch.setattr(
        server.core,
        "handle_request",
        lambda request: calls.setdefault("request", request) or ResponseEnvelope(
            protocol_version="1.0", request_id="req", status="ok", result={}
        ),
    )
    server.warm_start()
    req = RequestEnvelope(
        protocol_version="1.0", request_id="req", action="ping", payload={}
    )
    server.handle_request(req)
    assert calls.get("warm") is True
    assert calls.get("request") is req


def test_daemon_request_handler_handle_writes_response_and_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = object.__new__(daemon_server.DaemonRequestHandler)
    shutdown_called: dict[str, bool] = {}
    handler.server = type(
        "Server",
        (),
        {"core": object(), "shutdown": lambda self: shutdown_called.setdefault("shutdown", True)},
    )()
    handler.rfile = io.BytesIO(b'{"request_id":"r","action":"shutdown","protocol_version":"1.0","payload":{}}\n')
    handler.wfile = io.BytesIO()

    response = ResponseEnvelope(
        protocol_version="1.0",
        request_id="r",
        status="ok",
        result={"status": "stopping"},
    )
    monkeypatch.setattr(
        daemon_server,
        "_handle_raw_request",
        lambda _core, _raw: (response, "shutdown"),
    )

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(daemon_server.threading, "Thread", FakeThread)

    handler.handle()
    payload = handler.wfile.getvalue().decode("utf-8")
    assert '"status": "ok"' in payload
    assert shutdown_called.get("shutdown") is True

    # no-op when empty raw payload
    handler_empty = object.__new__(daemon_server.DaemonRequestHandler)
    handler_empty.server = handler.server
    handler_empty.rfile = io.BytesIO(b"")
    handler_empty.wfile = io.BytesIO()
    handler_empty.handle()
    assert handler_empty.wfile.getvalue() == b""


def test_handle_raw_request_protocol_error_branch() -> None:
    class ProtocolFailCore:
        def handle_request(self, _request):
            raise ProtocolError("protocol version unsupported")

    payload = json.dumps(
        {
            "protocol_version": "1.0",
            "request_id": "req-9",
            "action": "ping",
            "payload": {},
        }
    ).encode("utf-8")
    response, action = daemon_server._handle_raw_request(ProtocolFailCore(), payload)
    assert action == "ping"
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "protocol_version_unsupported"
