"""Daemon client utilities for index access."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from taskulus.daemon_paths import get_daemon_socket_path
from taskulus.daemon_protocol import (
    PROTOCOL_VERSION,
    ErrorEnvelope,
    RequestEnvelope,
    ResponseEnvelope,
)


class DaemonClientError(RuntimeError):
    """Raised when daemon communication fails."""


def is_daemon_enabled() -> bool:
    """Return whether daemon mode is enabled.

    :return: True when daemon mode is enabled.
    :rtype: bool
    """
    value = os.getenv("TASKULUS_NO_DAEMON", "").lower()
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
        raise DaemonClientError("daemon connection failed") from error

    if not response_raw:
        raise DaemonClientError("empty daemon response")
    response_payload = json.loads(response_raw.decode("utf-8"))
    return ResponseEnvelope.model_validate(response_payload)


def spawn_daemon(root: Path) -> None:
    """Spawn the daemon process.

    :param root: Repository root path.
    :type root: Path
    """
    subprocess.Popen(
        [sys.executable, "-m", "taskulus.daemon", "--root", str(root)],
        cwd=root,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def request_index_list(root: Path) -> List[Dict[str, Any]]:
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
    if not socket_path.exists():
        spawn_daemon(root)
    response = _request_with_recovery(socket_path, request, root)
    if response.status != "ok":
        error = response.error or ErrorEnvelope(
            code="internal_error", message="daemon error", details={}
        )
        raise DaemonClientError(error.message)
    result = response.result or {}
    return list(result.get("issues", []))


def request_status(root: Path) -> Dict[str, Any]:
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


def request_shutdown(root: Path) -> Dict[str, Any]:
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


def _request_with_recovery(
    socket_path: Path, request: RequestEnvelope, root: Path
) -> ResponseEnvelope:
    try:
        return send_request(socket_path, request)
    except DaemonClientError:
        if socket_path.exists():
            socket_path.unlink()
        spawn_daemon(root)
        return send_request(socket_path, request)
