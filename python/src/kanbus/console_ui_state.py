"""Console UI state: load and save the cached last-pushed UI route."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from kanbus.project import load_project_directory


def get_console_state_path(root: Path) -> Path:
    """Return the console UI state cache file path.

    :param root: Repository root path.
    :type root: Path
    :return: Path to console_state.json.
    :rtype: Path
    """
    project_dir = load_project_directory(root)
    return project_dir / ".cache" / "console_state.json"


def fetch_console_ui_state(root: Path, port: Optional[int] = None) -> Optional[dict]:  # type: ignore[type-arg]
    """Fetch the current UI state from the running console server.

    Returns ``None`` if the server is not reachable.

    :param root: Repository root path.
    :type root: Path
    :param port: HTTP port override; reads from project config if not given.
    :type port: int, optional
    :return: UI state dict or None.
    :rtype: dict or None
    """
    import urllib.error
    import urllib.request

    if port is None:
        try:
            from kanbus.project import get_configuration_path
            from kanbus.config_loader import load_project_configuration

            config_path = get_configuration_path(root)
            config = load_project_configuration(config_path)
            port = getattr(config, "console_port", None) or 5174
        except Exception:
            port = 5174

    url = f"http://127.0.0.1:{port}/api/ui-state"
    try:
        req = urllib.request.urlopen(url, timeout=3)  # noqa: S310
        return json.loads(req.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
