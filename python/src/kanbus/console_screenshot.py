"""Capture PNG screenshots of the Kanbus console board."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from kanbus.config_loader import load_project_configuration
from kanbus.project import get_configuration_path

DEFAULT_SCREENSHOT_FILENAME = "kanbus-board.png"

_MOCK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class ConsoleScreenshotError(RuntimeError):
    """Raised when board screenshot capture fails."""


def resolve_console_port(root: Path) -> int:
    """
    Resolve the console HTTP port from project configuration.

    :param root: Repository root path.
    :type root: Path
    :return: Console port number.
    :rtype: int
    """
    env_port = os.environ.get("CONSOLE_PORT")
    if env_port:
        try:
            return int(env_port.strip())
        except ValueError:
            pass
    try:
        config_path = get_configuration_path(root)
        config = load_project_configuration(config_path)
        port = getattr(config, "console_port", None)
        if port is not None:
            return int(port)
    except Exception:
        pass
    return 5174


def is_console_server_running(root: Path, port: int | None = None) -> bool:
    """
    Return whether the console server responds on its HTTP port.

    :param root: Repository root path.
    :type root: Path
    :param port: Optional port override.
    :type port: int | None
    :return: True when /api/config responds with HTTP 200.
    :rtype: bool
    """
    resolved_port = port if port is not None else resolve_console_port(root)
    url = f"http://127.0.0.1:{resolved_port}/api/config"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def locate_capture_script(root: Path) -> Path:
    """
    Locate the Node capture script for development and installed layouts.

    :param root: Repository or working root to search from.
    :type root: Path
    :return: Path to capture_console_screenshot.mjs.
    :rtype: Path
    :raises ConsoleScreenshotError: When the script cannot be found.
    """
    script_name = Path("scripts") / "capture_console_screenshot.mjs"
    for directory in [root, *root.parents]:
        candidate = directory / script_name
        if candidate.is_file():
            return candidate
    package_root = Path(__file__).resolve().parents[3]
    candidate = package_root / script_name
    if candidate.is_file():
        return candidate
    raise ConsoleScreenshotError(
        "headless browser capture script not found (scripts/capture_console_screenshot.mjs)."
    )


def _resolve_output_path(root: Path, output: str | None) -> Path:
    if output:
        path = Path(output)
        if not path.is_absolute():
            path = root / path
    else:
        path = root / DEFAULT_SCREENSHOT_FILENAME
    parent = path.parent
    if parent != Path(".") and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    return path


def _mock_mode() -> str | None:
    value = os.environ.get("KANBUS_TEST_SCREENSHOT_MOCK")
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "success", "succeed"}:
        return "success"
    if normalized in {"unavailable", "missing", "fail", "error"}:
        return "unavailable"
    return normalized


def capture_console_screenshot(root: Path, output: str | None = None) -> Path:
    """
    Capture a PNG screenshot of the console board to the requested path.

    :param root: Repository root path.
    :type root: Path
    :param output: Optional output file path relative to root unless absolute.
    :type output: str | None
    :return: Path to the written PNG file.
    :rtype: Path
    :raises ConsoleScreenshotError: When capture fails or prerequisites are missing.
    """
    output_path = _resolve_output_path(root, output)
    if not is_console_server_running(root):
        raise ConsoleScreenshotError("Console server is not running.")

    mock_mode = _mock_mode()
    if mock_mode == "unavailable":
        raise ConsoleScreenshotError(
            "headless browser capture is unavailable. Install Chromium for Playwright "
            "(npx playwright install chromium)."
        )
    if mock_mode == "success":
        output_path.write_bytes(_MOCK_PNG_BYTES)
        return output_path

    port = resolve_console_port(root)
    console_url = f"http://127.0.0.1:{port}/"
    node_executable = shutil.which("node")
    if node_executable is None:
        raise ConsoleScreenshotError(
            "headless browser capture requires Node.js on PATH to run Playwright."
        )

    script_path = locate_capture_script(root)
    result = subprocess.run(
        [node_executable, str(script_path), console_url, str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        if "playwright" in details.lower() or "headless browser" in details.lower():
            raise ConsoleScreenshotError(details)
        raise ConsoleScreenshotError(
            "headless browser capture failed. Install Chromium for Playwright "
            f"(npx playwright install chromium). {details}".strip()
        )
    if not output_path.is_file():
        raise ConsoleScreenshotError("headless browser capture did not produce an output file.")
    return output_path
