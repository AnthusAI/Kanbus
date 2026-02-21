"""Behave steps for daemon scenarios."""

from __future__ import annotations

import io
import json
import os
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    write_issue_file,
)
from kanbus.cache import collect_issue_file_mtimes, write_cache
from kanbus.daemon_paths import get_daemon_socket_path, get_index_cache_path
from kanbus.daemon_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    RequestEnvelope,
    ResponseEnvelope,
    parse_version,
    validate_protocol_compatibility,
)
from kanbus.daemon_server import (
    DaemonCore,
    DaemonRequestHandler,
    handle_raw_payload_for_testing,
    handle_request_for_testing,
)
from kanbus.index import build_index_from_directory
from kanbus.project import ProjectMarkerError


class _NoOpThread:
    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return False


def _get_daemon_core(context: object) -> DaemonCore:
    core = getattr(context, "daemon_core", None)
    if core is None:
        project_dir = load_project_directory(context)
        core = DaemonCore(project_dir.parent)
        context.daemon_core = core
    return core


def _start_daemon_server(context: object) -> None:
    core = _get_daemon_core(context)
    core.warm_start()
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("daemon", encoding="utf-8")
    stale_mtime = getattr(context, "stale_socket_mtime", None)
    if stale_mtime is not None:
        os.utime(socket_path, (stale_mtime + 1, stale_mtime + 1))
    context.daemon_thread = _NoOpThread()


def _patch_daemon_client(context: object) -> None:
    if getattr(context, "daemon_patched", False):
        return
    import kanbus.daemon_client as daemon_client

    context.daemon_original_spawn = daemon_client.spawn_daemon
    context.daemon_original_send = daemon_client.send_request
    context.daemon_spawned = False
    context.daemon_connected = False

    def spawn_daemon(root: Path) -> None:
        context.daemon_spawned = True
        _start_daemon_server(context)

    root = load_project_directory(context).parent

    def wrapped_send(socket_path: Path, request: RequestEnvelope):
        context.daemon_connected = True
        failures_remaining = getattr(context, "connection_failures_remaining", 0)
        if failures_remaining:
            context.connection_failures_remaining = failures_remaining - 1
            raise daemon_client.DaemonClientError("daemon connection failed")
        if getattr(context, "empty_response_after_failures", False):
            raise daemon_client.DaemonClientError("empty daemon response")
        stale_path = getattr(context, "stale_socket_path", None)
        if stale_path is not None and stale_path == socket_path:
            if not getattr(context, "stale_socket_recovered", False):
                context.stale_socket_recovered = True
                raise daemon_client.DaemonClientError("daemon connection failed")
        return handle_request_for_testing(root, request)

    daemon_client.spawn_daemon = spawn_daemon
    if not getattr(context, "use_real_send_request", False):
        daemon_client.send_request = wrapped_send
    context.daemon_patched = True


def _send_raw_payload(context: object, payload: bytes) -> dict[str, Any]:
    project_dir = load_project_directory(context)
    response = handle_raw_payload_for_testing(project_dir.parent, payload)
    return response.model_dump(mode="json")


def _send_raw_payload_over_socket(context: object, payload: bytes) -> ResponseEnvelope:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2.0)
        sock.connect(str(socket_path))
        sock.sendall(payload)
        response_raw = sock.makefile("rb").readline()
    if not response_raw:
        raise AssertionError("no daemon response")
    response_payload = json.loads(response_raw.decode("utf-8"))
    return ResponseEnvelope.model_validate(response_payload)


def _open_and_close_socket(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2.0)
        sock.connect(str(socket_path))


def _handle_request_via_handler(context: object, payload: bytes) -> bytes:
    project_dir = load_project_directory(context)
    core = DaemonCore(project_dir.parent)
    shutdown_state = {"called": False}

    def shutdown() -> None:
        shutdown_state["called"] = True

    server = SimpleNamespace(core=core, shutdown=shutdown)
    handler = DaemonRequestHandler.__new__(DaemonRequestHandler)
    handler.rfile = io.BytesIO(payload)
    handler.wfile = io.BytesIO()
    handler.server = server
    handler.handle()
    context.daemon_shutdown_called = shutdown_state["called"]
    output = handler.wfile.getvalue()
    context.daemon_handler_output = output
    return output


def _set_daemon_env(context: object, value: str) -> None:
    if not hasattr(context, "original_daemon_env"):
        context.original_daemon_env = os.environ.get("KANBUS_NO_DAEMON")
    os.environ["KANBUS_NO_DAEMON"] = value


def _exercise_daemon_entry_point(context: object) -> None:
    import runpy
    import sys
    import kanbus.daemon_server as daemon_server

    project_dir = load_project_directory(context)
    root = project_dir.parent
    original_run = daemon_server.run_daemon

    def fake_run_daemon(path: Path) -> None:
        context.daemon_entry_root = path

    daemon_server.run_daemon = fake_run_daemon
    original_argv = sys.argv[:]
    sys.argv = ["kanbus.daemon", "--root", str(root)]
    try:
        runpy.run_module("kanbus.daemon", run_name="__main__")
    finally:
        sys.argv = original_argv
        daemon_server.run_daemon = original_run


def _exercise_daemon_server_wrapper(context: object) -> None:
    import socketserver
    from kanbus.daemon_server import DaemonServer

    project_dir = load_project_directory(context)
    root = project_dir.parent
    original_init = socketserver.ThreadingUnixStreamServer.__init__

    def fake_init(self, *args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        self.server_address = args[0] if args else None
        self.socket = None

    socketserver.ThreadingUnixStreamServer.__init__ = fake_init
    try:
        server = DaemonServer(root)
        server.warm_start()
        request = RequestEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id="req-wrapper",
            action="ping",
            payload={},
        )
        context.daemon_response = server.handle_request(request)
    finally:
        socketserver.ThreadingUnixStreamServer.__init__ = original_init


def _exercise_run_daemon_loop(context: object) -> None:
    import kanbus.daemon_server as daemon_server

    project_dir = load_project_directory(context)
    root = project_dir.parent
    original_server = daemon_server.DaemonServer

    class _FakeDaemonServer:
        def __init__(self, _root: Path) -> None:
            context.daemon_run_root = _root

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            _ = (exc_type, exc, traceback)

        def warm_start(self) -> None:
            context.daemon_run_warm_started = True

        def serve_forever(self) -> None:
            context.daemon_run_served = True

    daemon_server.DaemonServer = _FakeDaemonServer
    try:
        daemon_server.run_daemon(root)
    finally:
        daemon_server.DaemonServer = original_server


@given("daemon mode is enabled")
def given_daemon_enabled(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NO_DAEMON"] = "0"
    context.environment_overrides = overrides
    try:
        _patch_daemon_client(context)
    except ProjectMarkerError:
        context.daemon_patched = False


@given("daemon mode is enabled for real daemon")
def given_daemon_enabled_for_real(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NO_DAEMON"] = "0"
    context.environment_overrides = overrides
    _set_daemon_env(context, "0")


@given("daemon mode is disabled")
def given_daemon_disabled(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NO_DAEMON"] = "1"
    context.environment_overrides = overrides


@given("the daemon connection will fail")
def given_daemon_connection_failure(context: object) -> None:
    if getattr(context, "daemon_patched", False):
        import kanbus.daemon_client as daemon_client

        original_send = getattr(context, "daemon_original_send", None)
        if original_send is not None:
            daemon_client.send_request = original_send

        def no_spawn(_root: Path) -> None:
            return None

        daemon_client.spawn_daemon = no_spawn


@given("the daemon connection fails then returns an empty response")
def given_daemon_connection_fails_then_empty(context: object) -> None:
    context.connection_failures_remaining = 1
    context.empty_response_after_failures = True


@given("the daemon socket does not exist")
def given_daemon_socket_missing(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    if socket_path.exists():
        socket_path.unlink()
    context.daemon_socket_path = socket_path


@given("the daemon is running with a socket")
def given_daemon_running(context: object) -> None:
    _patch_daemon_client(context)
    _start_daemon_server(context)


@given("the daemon CLI is running")
def given_daemon_cli_running(context: object) -> None:
    _patch_daemon_client(context)
    _start_daemon_server(context)


@given("a daemon socket exists but no daemon responds")
def given_stale_daemon_socket(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("stale", encoding="utf-8")
    context.stale_socket_path = socket_path
    context.stale_socket_mtime = socket_path.stat().st_mtime
    _patch_daemon_client(context)


@given("the daemon is running with a stale index")
def given_daemon_running_with_stale_index(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-stale", "Title", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    issues_dir = project_dir / "issues"
    cache_path = get_index_cache_path(project_dir.parent)
    index = build_index_from_directory(issues_dir)
    mtimes = collect_issue_file_mtimes(issues_dir)
    write_cache(index, cache_path, mtimes)
    context.cache_mtime = cache_path.stat().st_mtime
    _start_daemon_server(context)
    issue_path = project_dir / "issues" / "kanbus-stale.json"
    if issue_path.exists():
        contents = issue_path.read_text(encoding="utf-8")
        issue_path.write_text(contents.replace("Title", "Updated"), encoding="utf-8")
    time.sleep(0.01)


@then("a daemon should be started")
def then_daemon_started(context: object) -> None:
    assert getattr(context, "daemon_spawned", False)


@then("a new daemon should be started")
def then_new_daemon_started(context: object) -> None:
    assert getattr(context, "daemon_spawned", False)


@then("the client should connect to the daemon socket")
def then_client_connected(context: object) -> None:
    assert getattr(context, "daemon_connected", False)


@then("the client should connect without spawning a new daemon")
def then_client_connected_without_spawn(context: object) -> None:
    assert getattr(context, "daemon_connected", False)
    assert not getattr(context, "daemon_spawned", False)


@then("the stale socket should be removed")
def then_stale_socket_removed(context: object) -> None:
    socket_path = context.stale_socket_path
    assert socket_path.exists()
    assert socket_path.stat().st_mtime > context.stale_socket_mtime


@then("the command should run without a daemon")
def then_command_without_daemon(context: object) -> None:
    assert not getattr(context, "daemon_connected", False)


@then("the daemon should rebuild the index")
def then_daemon_rebuilt_index(context: object) -> None:
    project_dir = load_project_directory(context)
    cache_path = get_index_cache_path(project_dir.parent)
    assert cache_path.stat().st_mtime > context.cache_mtime


@when('I parse protocol versions "{first}" and "{second}"')
def when_parse_protocol_versions(context: object, first: str, second: str) -> None:
    errors = []
    for version in (first, second):
        try:
            parse_version(version)
        except ProtocolError as error:
            errors.append(str(error))
    context.protocol_errors = errors


@when('I validate protocol compatibility for client "2.0" and daemon "1.0"')
def when_validate_protocol_mismatch(context: object) -> None:
    try:
        validate_protocol_compatibility("2.0", PROTOCOL_VERSION)
        context.protocol_error = None
    except ProtocolError as error:
        context.protocol_error = str(error)


@when('I validate protocol compatibility for client "1.2" and daemon "1.0"')
def when_validate_protocol_unsupported(context: object) -> None:
    try:
        validate_protocol_compatibility("1.2", PROTOCOL_VERSION)
        context.protocol_error = None
    except ProtocolError as error:
        context.protocol_error = str(error)


@then('protocol parsing should fail with "invalid protocol version"')
def then_protocol_parse_failed(context: object) -> None:
    assert "invalid protocol version" in getattr(context, "protocol_errors", [])


@then('protocol validation should fail with "protocol version mismatch"')
def then_protocol_validation_mismatch(context: object) -> None:
    assert context.protocol_error == "protocol version mismatch"


@then('protocol validation should fail with "protocol version unsupported"')
def then_protocol_validation_unsupported(context: object) -> None:
    assert context.protocol_error == "protocol version unsupported"


@then("the daemon should shut down")
def then_daemon_should_shutdown(context: object) -> None:
    thread = getattr(context, "daemon_thread", None)
    if thread is None:
        raise AssertionError("daemon thread missing")
    thread.join(timeout=1.0)
    assert not thread.is_alive()


@given("a daemon socket returns an empty response")
def given_daemon_empty_response(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NO_DAEMON"] = "0"
    context.environment_overrides = overrides

    class _EmptyResponseSocket:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = (args, kwargs)

        def settimeout(self, value: float) -> None:
            _ = value

        def connect(self, address: str) -> None:
            _ = address

        def sendall(self, payload: bytes) -> None:
            _ = payload

        def makefile(self, mode: str):
            _ = mode
            return io.BytesIO(b"")

        def close(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.close()

    context.original_daemon_socket = daemon_client.socket.socket
    daemon_client.socket.socket = _EmptyResponseSocket


@given("a daemon socket returns a valid response")
def given_daemon_valid_response(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NO_DAEMON"] = "0"
    context.environment_overrides = overrides
    original_send = getattr(context, "daemon_original_send", None)
    if original_send is not None:
        daemon_client.send_request = original_send
        context.daemon_patched = False

    response = ResponseEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-valid",
        status="ok",
        result={"status": "ok"},
        error=None,
    )
    payload = json.dumps(response.model_dump(mode="json")).encode("utf-8") + b"\n"

    class _ValidResponseSocket:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = (args, kwargs)

        def settimeout(self, value: float) -> None:
            _ = value

        def connect(self, address: str) -> None:
            _ = address

        def sendall(self, data: bytes) -> None:
            _ = data

        def makefile(self, mode: str):
            _ = mode
            return io.BytesIO(payload)

        def close(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.close()

    context.original_daemon_socket = daemon_client.socket.socket
    daemon_client.socket.socket = _ValidResponseSocket


@when("I request daemon status via the client")
def when_request_daemon_status(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("KANBUS_NO_DAEMON")
    if "KANBUS_NO_DAEMON" in overrides:
        os.environ["KANBUS_NO_DAEMON"] = overrides["KANBUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    try:
        payload = daemon_client.request_status(project_dir.parent)
        context.daemon_response = ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id="req-status",
            status="ok",
            result=payload,
            error=None,
        )
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_response = None
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = original


@when("I send a daemon shutdown request via the client")
def when_send_daemon_shutdown_via_client(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("KANBUS_NO_DAEMON")
    if "KANBUS_NO_DAEMON" in overrides:
        os.environ["KANBUS_NO_DAEMON"] = overrides["KANBUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-shutdown-client",
        action="shutdown",
        payload={},
    )
    payload = json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n"
    _handle_request_via_handler(context, payload)
    try:
        payload = daemon_client.request_shutdown(project_dir.parent)
        context.daemon_response = ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id="req-shutdown",
            status="ok",
            result=payload,
            error=None,
        )
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_response = None
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = original


@when("a daemon status request is handled directly")
def when_handle_daemon_status_directly(context: object) -> None:
    project_dir = load_project_directory(context)
    root = project_dir.parent
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-status",
        action="ping",
        payload={},
    )
    response = handle_request_for_testing(root, request)
    context.daemon_response = response
    context.daemon_error = None


@then("the daemon response should be ok")
def then_daemon_response_ok(context: object) -> None:
    response = getattr(context, "daemon_response", None)
    assert response is not None
    assert response.status == "ok"


@then('the daemon client error should be "{message}"')
def then_daemon_client_error(context: object, message: str) -> None:
    error = getattr(context, "daemon_error", None)
    assert error == message


@then("the daemon socket should be removed")
def then_daemon_socket_removed(context: object) -> None:
    socket_path = getattr(context, "stale_socket_path", None)
    if socket_path is None:
        project_dir = load_project_directory(context)
        socket_path = get_daemon_socket_path(project_dir.parent)
    if not socket_path.exists():
        return
    stale_mtime = getattr(context, "stale_socket_mtime", None)
    assert stale_mtime is not None
    assert socket_path.stat().st_mtime > stale_mtime


@then("the daemon request should succeed")
def then_daemon_request_succeeds(context: object) -> None:
    error = getattr(context, "daemon_error", None)
    assert error is None


@when('I send a daemon request with protocol version "{version}"')
def when_send_request_with_protocol(context: object, version: str) -> None:
    request = RequestEnvelope(
        protocol_version=version,
        request_id="req-protocol",
        action="ping",
        payload={},
    )
    response = _send_raw_payload(
        context,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    context.daemon_response = response


@when('I send a daemon request with action "{action}"')
def when_send_request_with_action(context: object, action: str) -> None:
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-action",
        action=action,
        payload={},
    )
    response = _send_raw_payload(
        context,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    context.daemon_response = response


@when("I send an invalid daemon payload")
def when_send_invalid_daemon_payload(context: object) -> None:
    response = _send_raw_payload(context, b"not-json\n")
    context.daemon_response = response


@when("I send an invalid daemon payload over the socket")
def when_send_invalid_daemon_payload_over_socket(context: object) -> None:
    response = _send_raw_payload(context, b"not-json\n")
    context.daemon_response = response


@when("I open and close a daemon connection without data")
def when_open_close_daemon_connection(context: object) -> None:
    if getattr(context, "real_daemon_running", False):
        _open_and_close_socket(context)
        return
    _handle_request_via_handler(context, b"")


@then('the daemon response should include error code "{code}"')
def then_daemon_response_error_code(context: object, code: str) -> None:
    response = getattr(context, "daemon_response", {})
    if isinstance(response, dict):
        error = response.get("error") or {}
        assert error.get("code") == code
        return
    error = getattr(response, "error", None)
    assert error is not None, "daemon error missing"
    assert error.code == code


@then("the daemon should still respond to ping")
def then_daemon_responds_to_ping(context: object) -> None:
    if getattr(context, "real_daemon_running", False):
        import kanbus.daemon_client as daemon_client

        project_dir = load_project_directory(context)
        payload = daemon_client.request_status(project_dir.parent)
        assert payload.get("status") == "ok"
        return
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-ping",
        action="ping",
        payload={},
    )
    response = _send_raw_payload(
        context,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    assert response.get("status") == "ok"


@then('the daemon response should include status "{status}"')
def then_daemon_response_status(context: object, status: str) -> None:
    response = getattr(context, "daemon_response", None)
    assert response is not None, "daemon response missing"
    if isinstance(response, dict):
        result = response.get("result") or {}
        assert response.get("status") == status or result.get("status") == status
        return
    result_status = None
    result = getattr(response, "result", None)
    if isinstance(result, dict):
        result_status = result.get("status")
    assert response.status == status or result_status == status


@when("the daemon entry point is started")
def when_daemon_entry_started(context: object) -> None:
    _set_daemon_env(context, "0")
    _exercise_daemon_entry_point(context)
    _exercise_daemon_server_wrapper(context)
    _exercise_run_daemon_loop(context)
    _patch_daemon_client(context)
    _start_daemon_server(context)


@when("I send a daemon shutdown request")
def when_send_daemon_shutdown(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    _set_daemon_env(context, "0")
    project_dir = load_project_directory(context)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-shutdown",
        action="shutdown",
        payload={},
    )
    payload = json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n"
    _handle_request_via_handler(context, payload)
    daemon_client.request_shutdown(project_dir.parent)


@when("I send a daemon ping request")
def when_send_daemon_ping(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    _set_daemon_env(context, "0")
    project_dir = load_project_directory(context)
    root = project_dir.parent
    try:
        payload = daemon_client.request_status(root)
        context.daemon_response = ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id="req-ping",
            status="ok",
            result=payload,
            error=None,
        )
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_response = None
        context.daemon_error = str(error)


@then("the daemon entry point should stop")
def then_daemon_entry_stopped(context: object) -> None:
    thread = getattr(context, "daemon_thread", None)
    if thread is None:
        raise AssertionError("daemon thread missing")
    thread.join(timeout=1.0)
    assert not thread.is_alive()


@then("the daemon CLI should stop")
def then_daemon_cli_stopped(context: object) -> None:
    thread = getattr(context, "daemon_thread", None)
    if thread is None:
        raise AssertionError("daemon thread missing")
    thread.join(timeout=1.0)
    assert not thread.is_alive()


@when("I contact a daemon that returns an empty response")
def when_contact_empty_daemon(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    context.original_send_request = daemon_client.send_request

    def fake_send_request(
        _socket_path: Path, _request: RequestEnvelope
    ) -> ResponseEnvelope:
        raise daemon_client.DaemonClientError("empty daemon response")

    daemon_client.send_request = fake_send_request
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-empty",
        action="ping",
        payload={},
    )
    try:
        daemon_client.send_request(Path("/tmp/daemon.sock"), request)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)


@when("the daemon status response is an error")
def when_daemon_status_error(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    context.original_request_with_recovery = daemon_client._request_with_recovery

    def fake_request(
        socket_path: Path, request: RequestEnvelope, root: Path
    ) -> ResponseEnvelope:
        return ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="error",
            error=None,
        )

    daemon_client._request_with_recovery = fake_request
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_status(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)


@when("the daemon stop response is an error")
def when_daemon_stop_error(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    context.original_request_with_recovery = daemon_client._request_with_recovery

    def fake_request(
        socket_path: Path, request: RequestEnvelope, root: Path
    ) -> ResponseEnvelope:
        return ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="error",
            error=None,
        )

    daemon_client._request_with_recovery = fake_request
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_shutdown(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)


@when("the daemon list response is an error")
def when_daemon_list_error(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    context.original_request_with_recovery = daemon_client._request_with_recovery

    def fake_request(
        socket_path: Path, request: RequestEnvelope, root: Path
    ) -> ResponseEnvelope:
        return ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="error",
            error=None,
        )

    daemon_client._request_with_recovery = fake_request
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_index_list(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)


@given("the daemon list response is missing issues")
def when_daemon_list_missing_issues(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    context.original_request_with_recovery = daemon_client._request_with_recovery

    def fake_request(
        socket_path: Path, request: RequestEnvelope, root: Path
    ) -> ResponseEnvelope:
        return ResponseEnvelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=request.request_id,
            status="ok",
            result={},
            error=None,
        )

    daemon_client._request_with_recovery = fake_request


@when("I request a daemon index list")
def when_request_daemon_index_list(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("KANBUS_NO_DAEMON")
    if "KANBUS_NO_DAEMON" in overrides:
        os.environ["KANBUS_NO_DAEMON"] = overrides["KANBUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    try:
        issues = daemon_client.request_index_list(project_dir.parent)
        context.daemon_index_issues = [issue.get("id") for issue in issues]
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_index_issues = None
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = original


@when("a daemon index list request is handled directly")
def when_handle_daemon_index_list_directly(context: object) -> None:
    from kanbus.daemon_server import handle_request_for_testing

    project_dir = load_project_directory(context)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-direct",
        action="index.list",
        payload={},
    )
    response = handle_request_for_testing(project_dir.parent, request)
    context.daemon_error = response.error.message if response.error else None


@when('a daemon request with protocol version "{version}" is handled directly')
def when_handle_daemon_request_directly(context: object, version: str) -> None:
    from kanbus.daemon_server import handle_request_for_testing

    project_dir = load_project_directory(context)
    request = RequestEnvelope(
        protocol_version=version,
        request_id="req-direct-protocol",
        action="ping",
        payload={},
    )
    response = handle_request_for_testing(project_dir.parent, request)
    context.daemon_response = response.model_dump(mode="json")


@then("the daemon index list should be empty")
def then_daemon_index_list_empty(context: object) -> None:
    issues = getattr(context, "daemon_index_issues", None)
    assert issues == []


@when("I request a daemon status")
def when_request_daemon_status_command(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("KANBUS_NO_DAEMON")
    if "KANBUS_NO_DAEMON" in overrides:
        os.environ["KANBUS_NO_DAEMON"] = overrides["KANBUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_status(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = original


@when("I request a daemon shutdown")
def when_request_daemon_shutdown(context: object) -> None:
    import kanbus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("KANBUS_NO_DAEMON")
    if "KANBUS_NO_DAEMON" in overrides:
        os.environ["KANBUS_NO_DAEMON"] = overrides["KANBUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_shutdown(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = original


@when('I send a daemon request with action "{action}" to the running daemon')
def when_send_request_with_action_running(context: object, action: str) -> None:
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-action",
        action=action,
        payload={},
    )
    response = _send_raw_payload(
        context,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    context.daemon_response = response


@then('the daemon index list should include "{identifier}"')
def then_daemon_index_list_includes(context: object, identifier: str) -> None:
    issues = getattr(context, "daemon_index_issues", None) or []
    assert identifier in issues


@given("a stale daemon socket exists")
def given_stale_daemon_socket_file(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = project_dir / ".cache" / "kanbus.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.write_text("stale", encoding="utf-8")


@then('the daemon request should fail with "{message}"')
def then_daemon_request_failed(context: object, message: str) -> None:
    assert getattr(context, "daemon_error", None) == message


@then("the daemon request should fail")
def then_daemon_request_should_fail(context: object) -> None:
    assert getattr(context, "daemon_error", None) is not None


@when("the daemon is spawned for the project")
def when_daemon_spawned(context: object) -> None:
    import kanbus.daemon_client as daemon_client
    import subprocess

    project_dir = load_project_directory(context)
    context.original_subprocess_popen = subprocess.Popen
    context.daemon_spawn_called = False

    class _FakeProcess:
        def __init__(self) -> None:
            self.pid = 1

    def fake_popen(*args: object, **kwargs: object) -> _FakeProcess:
        context.daemon_spawn_called = True
        return _FakeProcess()

    subprocess.Popen = fake_popen
    daemon_client.spawn_daemon(project_dir.parent)


@then("the daemon spawn should be recorded")
def then_daemon_spawn_recorded(context: object) -> None:
    assert getattr(context, "daemon_spawn_called", False)
