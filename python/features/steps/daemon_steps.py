"""Behave steps for daemon scenarios."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    run_cli,
    write_issue_file,
)
from taskulus.cache import collect_issue_file_mtimes, write_cache
from taskulus.daemon_paths import get_daemon_socket_path, get_index_cache_path
from taskulus.daemon_protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    RequestEnvelope,
    ResponseEnvelope,
    parse_version,
    validate_protocol_compatibility,
)
from taskulus.daemon_server import DaemonServer
from taskulus.index import build_index_from_directory


def _start_daemon_server(context: object) -> None:
    project_dir = load_project_directory(context)
    root = project_dir.parent
    server = DaemonServer(root)
    server.warm_start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context.daemon_server = server
    context.daemon_thread = thread


def _patch_daemon_client(context: object) -> None:
    if getattr(context, "daemon_patched", False):
        return
    import taskulus.daemon_client as daemon_client

    context.daemon_original_spawn = daemon_client.spawn_daemon
    context.daemon_original_send = daemon_client.send_request
    context.daemon_spawned = False
    context.daemon_connected = False

    def spawn_daemon(root: Path) -> None:
        context.daemon_spawned = True
        _start_daemon_server(context)

    def wrapped_send(socket_path: Path, request: RequestEnvelope):
        context.daemon_connected = True
        return context.daemon_original_send(socket_path, request)

    daemon_client.spawn_daemon = spawn_daemon
    daemon_client.send_request = wrapped_send
    context.daemon_patched = True


def _send_raw_payload(socket_path: Path, payload: bytes) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))
        sock.sendall(payload)
        response_raw = sock.makefile("rb").readline()
    return json.loads(response_raw.decode("utf-8"))


@given("daemon mode is enabled")
def given_daemon_enabled(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["TASKULUS_NO_DAEMON"] = "0"
    context.environment_overrides = overrides
    _patch_daemon_client(context)


@given("daemon mode is disabled")
def given_daemon_disabled(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["TASKULUS_NO_DAEMON"] = "1"
    context.environment_overrides = overrides


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
    issue = build_issue("tsk-stale", "Title", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    issues_dir = project_dir / "issues"
    cache_path = get_index_cache_path(project_dir.parent)
    index = build_index_from_directory(issues_dir)
    mtimes = collect_issue_file_mtimes(issues_dir)
    write_cache(index, cache_path, mtimes)
    context.cache_mtime = cache_path.stat().st_mtime
    _start_daemon_server(context)
    issue_path = project_dir / "issues" / "tsk-stale.json"
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


@when('I run "tsk list"')
def when_run_list(context: object) -> None:
    run_cli(context, "tsk list")


@when('I run "tsk daemon-status"')
def when_run_daemon_status(context: object) -> None:
    run_cli(context, "tsk daemon-status")


@when('I run "tsk daemon-stop"')
def when_run_daemon_stop(context: object) -> None:
    run_cli(context, "tsk daemon-stop")


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


@when('I send a daemon request with protocol version "{version}"')
def when_send_request_with_protocol(context: object, version: str) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    request = RequestEnvelope(
        protocol_version=version,
        request_id="req-protocol",
        action="ping",
        payload={},
    )
    response = _send_raw_payload(
        socket_path,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    context.daemon_response = response


@when('I send a daemon request with action "{action}"')
def when_send_request_with_action(context: object, action: str) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-action",
        action=action,
        payload={},
    )
    response = _send_raw_payload(
        socket_path,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    context.daemon_response = response


@when("I send an invalid daemon payload")
def when_send_invalid_daemon_payload(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    response = _send_raw_payload(socket_path, b"not-json\n")
    context.daemon_response = response


@when("I open and close a daemon connection without data")
def when_open_close_daemon_connection(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(socket_path))


@then('the daemon response should include error code "{code}"')
def then_daemon_response_error_code(context: object, code: str) -> None:
    response = getattr(context, "daemon_response", {})
    error = response.get("error") or {}
    assert error.get("code") == code


@then("the daemon should still respond to ping")
def then_daemon_responds_to_ping(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-ping",
        action="ping",
        payload={},
    )
    response = _send_raw_payload(
        socket_path,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )
    assert response.get("status") == "ok"


@when("the daemon entry point is started")
def when_daemon_entry_started(context: object) -> None:
    import runpy
    import sys

    project_dir = load_project_directory(context)
    root = project_dir.parent
    socket_path = get_daemon_socket_path(root)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if not socket_path.exists():
        socket_path.write_text("stale", encoding="utf-8")

    def run_entry() -> None:
        original_argv = sys.argv[:]
        sys.argv = ["taskulus.daemon", "--root", str(root)]
        try:
            runpy.run_module("taskulus.daemon", run_name="__main__")
        except SystemExit:
            pass
        finally:
            sys.argv = original_argv

    thread = threading.Thread(target=run_entry, daemon=True)
    thread.start()
    context.daemon_thread = thread
    for _ in range(50):
        try:
            request = RequestEnvelope(
                protocol_version=PROTOCOL_VERSION,
                request_id="req-ready",
                action="ping",
                payload={},
            )
            response = _send_raw_payload(
                socket_path,
                json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
            )
            if response.get("status") == "ok":
                break
        except OSError:
            time.sleep(0.02)
        time.sleep(0.02)


@when("I send a daemon shutdown request")
def when_send_daemon_shutdown(context: object) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-shutdown",
        action="shutdown",
        payload={},
    )
    _ = _send_raw_payload(
        socket_path,
        json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n",
    )


@then("the daemon entry point should stop")
def then_daemon_entry_stopped(context: object) -> None:
    thread = getattr(context, "daemon_thread", None)
    if thread is None:
        raise AssertionError("daemon thread missing")
    thread.join(timeout=1.0)
    assert not thread.is_alive()


@when("I contact a daemon that returns an empty response")
def when_contact_empty_daemon(context: object) -> None:
    import taskulus.daemon_client as daemon_client

    project_dir = load_project_directory(context)
    socket_path = project_dir.parent / ".taskulus-empty.sock"
    if socket_path.exists():
        socket_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)

    def serve_once() -> None:
        conn, _ = server.accept()
        try:
            conn.settimeout(1.0)
            conn.recv(1024)
        except OSError:
            pass
        conn.close()
        server.close()

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    time.sleep(0.01)

    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-empty",
        action="ping",
        payload={},
    )
    try:
        daemon_client.send_request(socket_path, request)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)


@when("the daemon status response is an error")
def when_daemon_status_error(context: object) -> None:
    import taskulus.daemon_client as daemon_client

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
    import taskulus.daemon_client as daemon_client

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
    import taskulus.daemon_client as daemon_client

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
    import taskulus.daemon_client as daemon_client

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
    import taskulus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("TASKULUS_NO_DAEMON")
    if "TASKULUS_NO_DAEMON" in overrides:
        os.environ["TASKULUS_NO_DAEMON"] = overrides["TASKULUS_NO_DAEMON"]
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
            os.environ.pop("TASKULUS_NO_DAEMON", None)
        else:
            os.environ["TASKULUS_NO_DAEMON"] = original


@when("a daemon index list request is handled directly")
def when_handle_daemon_index_list_directly(context: object) -> None:
    from taskulus.daemon_server import handle_request_for_testing

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
    from taskulus.daemon_server import handle_request_for_testing

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
def when_request_daemon_status(context: object) -> None:
    import taskulus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("TASKULUS_NO_DAEMON")
    if "TASKULUS_NO_DAEMON" in overrides:
        os.environ["TASKULUS_NO_DAEMON"] = overrides["TASKULUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_status(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("TASKULUS_NO_DAEMON", None)
        else:
            os.environ["TASKULUS_NO_DAEMON"] = original


@when("I request a daemon shutdown")
def when_request_daemon_shutdown(context: object) -> None:
    import taskulus.daemon_client as daemon_client

    overrides = getattr(context, "environment_overrides", None) or {}
    original = os.environ.get("TASKULUS_NO_DAEMON")
    if "TASKULUS_NO_DAEMON" in overrides:
        os.environ["TASKULUS_NO_DAEMON"] = overrides["TASKULUS_NO_DAEMON"]
    project_dir = load_project_directory(context)
    try:
        daemon_client.request_shutdown(project_dir.parent)
        context.daemon_error = None
    except daemon_client.DaemonClientError as error:
        context.daemon_error = str(error)
    finally:
        if original is None:
            os.environ.pop("TASKULUS_NO_DAEMON", None)
        else:
            os.environ["TASKULUS_NO_DAEMON"] = original


@when('I send a daemon request with action "{action}" to the running daemon')
def when_send_request_with_action_running(context: object, action: str) -> None:
    project_dir = load_project_directory(context)
    socket_path = get_daemon_socket_path(project_dir.parent)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id="req-action",
        action=action,
        payload={},
    )
    response = _send_raw_payload(
        socket_path,
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
    socket_path = project_dir / ".cache" / "taskulus.sock"
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
    import taskulus.daemon_client as daemon_client
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
