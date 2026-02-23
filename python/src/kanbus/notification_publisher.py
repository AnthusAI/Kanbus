"""Notification publisher: sends real-time events to the console server via Unix socket."""

from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def _get_socket_path(root: Path) -> Path:
    """Return the Unix domain socket path for the given project root.

    Uses the same derivation as the Rust notification_publisher:
    SHA-256 of the canonical path, first 12 hex characters.

    :param root: Repository root path.
    :type root: Path
    :return: Path to the Unix domain socket.
    :rtype: Path
    """
    try:
        canonical = str(root.resolve())
    except OSError:
        canonical = str(root)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    socket_name = f"kanbus-{digest[:12]}.sock"
    return Path(tempfile.gettempdir()) / socket_name


def publish_notification(root: Path, event: dict) -> None:  # type: ignore[type-arg]
    """Send a notification event to the running console server.

    Errors are silenced — notification failure must not block CLI operations.

    :param root: Repository root path.
    :type root: Path
    :param event: Notification event dict (will be JSON-serialised).
    :type event: dict
    """
    socket_path = _get_socket_path(root)
    payload = json.dumps(event) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect(str(socket_path))
            sock.sendall(payload.encode())
            return
    except (OSError, socket.error):
        pass

    port = _get_console_port(root) or 5174
    url = f"http://127.0.0.1:{port}/api/notifications"
    req = urllib.request.Request(
        url,
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            resp.read()
    except (urllib.error.URLError, OSError):
        pass


def _get_console_port(root: Path) -> int | None:
    try:
        from kanbus.project import get_configuration_path
        from kanbus.config_loader import load_project_configuration

        config_path = get_configuration_path(root)
        config = load_project_configuration(config_path)
        return getattr(config, "console_port", None)
    except Exception:
        return None
