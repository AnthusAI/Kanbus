"""Daemon client utilities for index access."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from kanbus.daemon_paths import get_daemon_socket_path
from kanbus.daemon_protocol import (
    PROTOCOL_VERSION,
    ErrorEnvelope,
    RequestEnvelope,
    ResponseEnvelope,
)

logger = logging.getLogger(__name__)

DAEMON_SOCKET_WAIT_SECONDS = 0.4
DAEMON_SOCKET_POLL_INTERVAL_SECONDS = 0.025


class DaemonClientError(RuntimeError):
    """Raised when daemon communication fails."""


DAEMON_CONFIG_SCHEMA_ERROR_MESSAGE = "unknown configuration fields"
_daemon_restart_recorded_for_testing = False
_daemon_unavailable_roots: set[str] = set()


def mark_daemon_unavailable(root: Path) -> None:
    """Record that the daemon could not be reached for a project root."""
    _daemon_unavailable_roots.add(str(root))


def is_daemon_unavailable(root: Path) -> bool:
    """Return whether a previous daemon attempt failed for this root."""
    return str(root) in _daemon_unavailable_roots


def reset_daemon_unavailable_roots_for_testing() -> None:
    """Clear the per-root daemon-unavailable marks (test helper)."""
    _daemon_unavailable_roots.clear()


def is_daemon_config_schema_error(message: str) -> bool:
    """Return whether a daemon error indicates stale config schema parsing.

    :param message: Daemon error message text.
    :type message: str
    :return: True when the message is a config schema rejection.
    :rtype: bool
    """
    return message == DAEMON_CONFIG_SCHEMA_ERROR_MESSAGE


def is_daemon_transport_error(message: str) -> bool:
    """Return whether a daemon error means the daemon itself is unreachable.

    :param message: Daemon error message text.
    :type message: str
    :return: True when the daemon is not running, cannot start, or the socket
        is missing, so callers should fall back to direct storage access.
    :rtype: bool
    """
    return (
        message.startswith("daemon connect failed:")
        or message.startswith("daemon connection failed")
        or message.startswith("daemon socket did not become ready")
        or message.startswith("daemon socket unavailable")
        or message.startswith("daemon spawn failed")
        or message == "empty daemon response"
    )


def is_daemon_enabled() -> bool:
    """Return whether daemon mode is enabled.

    :return: True when daemon mode is enabled.
    :rtype: bool
    """
    value = os.getenv("KANBUS_NO_DAEMON", "").lower()
    return value not in {"1", "true", "yes"}


def send_request(socket_path: Path, request: RequestEnvelope) -> ResponseEnvelope:
    """Send a request to the daemon and return the response.

    :param socket_path: Daemon socket path.
    :type socket_path: Path
    :param request: Request envelope.
    :type request: RequestEnvelope
    :return: Response envelope.
    :rtype: ResponseEnvelope
    :raises DaemonClientError: If communication fails.
    """
    payload = json.dumps(request.model_dump(mode="json")).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect(str(socket_path))
            sock.sendall(payload)
            response_raw = sock.makefile("rb").readline()
    except OSError as error:
        raise DaemonClientError(
            f"daemon connect failed: {socket_path}: {error}"
        ) from error

    if not response_raw:
        raise DaemonClientError("empty daemon response")
    response_payload = json.loads(response_raw.decode("utf-8"))
    return ResponseEnvelope.model_validate(response_payload)


def spawn_daemon(root: Path) -> None:
    """Spawn the daemon process.

    :param root: Repository root path.
    :type root: Path
    """
    try:
        subprocess.Popen(
            [sys.executable, "-m", "kanbus.daemon", "--root", str(root)],
            cwd=root,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise DaemonClientError(
            f"daemon spawn failed: {error}. "
            "Set KANBUS_NO_DAEMON=1 to bypass the daemon."
        ) from error


def was_daemon_restarted_for_testing() -> bool:
    """Return whether restart_daemon ran during the current test scenario.

    :return: True when restart_daemon was invoked.
    :rtype: bool
    """
    return _daemon_restart_recorded_for_testing


def reset_daemon_restart_recorded_for_testing() -> None:
    """Clear the restart_daemon test recorder."""
    global _daemon_restart_recorded_for_testing
    _daemon_restart_recorded_for_testing = False


def restart_daemon(root: Path) -> None:
    """Restart the daemon after a stale process rejects the current config schema.

    :param root: Repository root path.
    :type root: Path
    """
    global _daemon_restart_recorded_for_testing
    _daemon_restart_recorded_for_testing = True
    try:
        request_shutdown(root)
    except DaemonClientError:
        pass
    socket_path = get_daemon_socket_path(root)
    if socket_path.exists():
        socket_path.unlink()
    spawn_daemon(root)
    time.sleep(0.05)


def request_index_list(root: Path) -> list[dict[str, Any]]:
    """Request the index list from the daemon, spawning it if needed.

    :param root: Repository root path.
    :type root: Path
    :return: List of issue payloads.
    :rtype: List[Dict[str, Any]]
    :raises DaemonClientError: If the daemon request fails.
    """
    if not is_daemon_enabled():
        raise DaemonClientError("daemon disabled")
    socket_path = get_daemon_socket_path(root)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        action="index.list",
        payload={},
    )
    ensure_daemon_socket_best_effort(root, socket_path)
    response = _request_with_recovery(socket_path, request, root)
    if response.status != "ok":
        error = response.error or ErrorEnvelope(
            code="internal_error", message="daemon error", details={}
        )
        if is_daemon_config_schema_error(error.message):
            restart_daemon(root)
            response = _request_with_recovery(socket_path, request, root)
            if response.status != "ok":
                retry_error = response.error or ErrorEnvelope(
                    code="internal_error", message="daemon error", details={}
                )
                raise DaemonClientError(retry_error.message)
        else:
            raise DaemonClientError(error.message)
    result = response.result or {}
    return list(result.get("issues", []))


def request_status(root: Path) -> dict[str, Any]:
    """Request daemon status.

    :param root: Repository root path.
    :type root: Path
    :return: Status payload.
    :rtype: Dict[str, Any]
    """
    if not is_daemon_enabled():
        raise DaemonClientError("daemon disabled")
    socket_path = get_daemon_socket_path(root)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        action="ping",
        payload={},
    )
    response = _request_with_recovery(socket_path, request, root)
    if response.status != "ok":
        error = response.error or ErrorEnvelope(
            code="internal_error", message="daemon error", details={}
        )
        raise DaemonClientError(error.message)
    return response.result or {}


def request_shutdown(root: Path) -> dict[str, Any]:
    """Request daemon shutdown.

    :param root: Repository root path.
    :type root: Path
    :return: Shutdown response payload.
    :rtype: Dict[str, Any]
    """
    if not is_daemon_enabled():
        raise DaemonClientError("daemon disabled")
    socket_path = get_daemon_socket_path(root)
    request = RequestEnvelope(
        protocol_version=PROTOCOL_VERSION,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        action="shutdown",
        payload={},
    )
    response = _request_with_recovery(socket_path, request, root)
    if response.status != "ok":
        error = response.error or ErrorEnvelope(
            code="internal_error", message="daemon error", details={}
        )
        raise DaemonClientError(error.message)
    return response.result or {}


def _send_virtuus_request(socket_path: Path, request: dict[str, Any]) -> Any:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall(json.dumps(request).encode("utf-8") + b"\n")
        response = b""
        while not response.endswith(b"\n"):
            chunk = connection.recv(65536)
            if not chunk:
                break
            response += chunk
    if not response.strip():
        raise DaemonClientError("empty daemon response")
    decoded = json.loads(response)
    if not decoded.get("ok"):
        raise DaemonClientError(str(decoded.get("error", "daemon error")))
    return decoded.get("result")


def ensure_daemon_socket_best_effort(root: Path, socket_path: Path) -> None:
    """Best-effort just-in-time daemon start.

    The daemon is an accelerator only: spawn once, wait briefly for the
    socket, and mark the root unavailable when the daemon cannot be reached.
    Raises :class:`DaemonClientError` when the socket is not ready so callers
    can fall back to direct storage access.
    """
    if socket_path.exists():
        return
    if _daemon_client_is_patched_for_testing():
        if spawn_daemon is not _original_spawn_daemon:
            spawn_daemon(root)
        return
    if is_daemon_unavailable(root):
        logger.debug(
            "daemon previously unavailable for %s; using direct storage access",
            root,
        )
        raise DaemonClientError(f"daemon socket unavailable: {socket_path}")
    try:
        spawn_daemon(root)
    except DaemonClientError as error:
        mark_daemon_unavailable(root)
        logger.debug(
            "daemon spawn failed for %s (%s); using direct storage access",
            root,
            error,
        )
        raise
    deadline = time.monotonic() + DAEMON_SOCKET_WAIT_SECONDS
    while True:
        if socket_path.exists():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(0.1)
                    probe.connect(str(socket_path))
                return
            except OSError:
                pass
        if time.monotonic() >= deadline:
            mark_daemon_unavailable(root)
            logger.debug(
                "daemon socket did not become ready at %s; using direct storage access",
                socket_path,
            )
            raise DaemonClientError(
                f"daemon socket did not become ready: {socket_path}"
            )
        time.sleep(DAEMON_SOCKET_POLL_INTERVAL_SECONDS)


def request_virtuus(root: Path, request: dict[str, Any]) -> Any:
    """Send a generic Virtuus service request through Kanbus's resident daemon.

    The daemon is a just-in-time accelerator: it is started best-effort and is
    never required for correctness. Callers fall back to direct synchronous
    storage access whenever this raises.
    """
    if not is_daemon_enabled():
        raise DaemonClientError("daemon disabled")
    socket_path = get_daemon_socket_path(root)
    if is_daemon_unavailable(root):
        logger.debug(
            "daemon previously unavailable for %s; using direct storage access", root
        )
        raise DaemonClientError(f"daemon socket unavailable: {socket_path}")
    if not socket_path.exists():
        ensure_daemon_socket_best_effort(root, socket_path)
    try:
        return _send_virtuus_request(socket_path, request)
    except (OSError, json.JSONDecodeError, DaemonClientError) as error:
        logger.debug(
            "Virtuus daemon request failed (%s); falling back to direct storage access",
            error,
        )
        raise DaemonClientError(f"Virtuus daemon request failed: {error}") from error


def _request_with_recovery(
    socket_path: Path, request: RequestEnvelope, root: Path
) -> ResponseEnvelope:
    try:
        return send_request(socket_path, request)
    except DaemonClientError as error:
        if not (
            str(error).startswith("daemon connect failed:")
            or str(error) == "daemon connection failed"
        ):
            raise
        if socket_path.exists():
            socket_path.unlink()
        spawn_daemon(root)
        last_error = error
        for _ in range(10):
            try:
                return send_request(socket_path, request)
            except DaemonClientError as retry_error:
                if not (
                    str(retry_error).startswith("daemon connect failed:")
                    or str(retry_error) == "daemon connection failed"
                ):
                    raise
                last_error = retry_error
                time.sleep(0.05)
        raise DaemonClientError(
            f"daemon connection failed after retries: {socket_path}. "
            "Set KANBUS_NO_DAEMON=1 to bypass the daemon."
        ) from last_error


_original_spawn_daemon = spawn_daemon
_original_send_request = send_request
_original_request_with_recovery = _request_with_recovery


def _daemon_client_is_patched_for_testing() -> bool:
    """Return whether test code has replaced daemon client functions.

    Mocked scenarios must not launch real daemon processes or wait on real
    sockets: :func:`ensure_daemon_socket_best_effort` invokes the patched
    spawn (so scenarios can observe spawn attempts) and skips the rest of
    the just-in-time startup sequence.
    """
    return (
        spawn_daemon is not _original_spawn_daemon
        or send_request is not _original_send_request
        or _request_with_recovery is not _original_request_with_recovery
    )
