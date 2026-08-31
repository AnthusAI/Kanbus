"""Capture PNG screenshots of the Kanbus console board."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kanbus.config_loader import load_project_configuration
from kanbus.project import get_configuration_path

DEFAULT_SCREENSHOT_FILENAME = "kanbus-board.png"
DEFAULT_APPEARANCE_MODE = "light"
TEST_LAST_MODE_ENV = "KANBUS_TEST_SCREENSHOT_LAST_MODE"
TEST_CAPTURE_OPTIONS_ENV = "KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS"
TEST_PREREQUISITES_VERIFIED_ENV = "KANBUS_TEST_SCREENSHOT_PREREQUISITES_VERIFIED"
TEST_SCRIPT_SEARCH_ROOT_ENV = "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT"
TEST_HIDE_PACKAGE_SCRIPT_ENV = "KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT"
TEST_FORCE_NODE_MISSING_ENV = "KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING"
VALID_VIEWS = frozenset({"initiatives", "epics", "issues", "all"})

_MOCK_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class ConsoleScreenshotError(RuntimeError):
    """Raised when board screenshot capture fails."""


@dataclass
class ScreenshotCaptureOptions:
    """Layout and appearance options for a single board screenshot."""

    appearance_mode: str = DEFAULT_APPEARANCE_MODE
    view: str | None = None
    expand_all: bool = False
    expand_columns: list[str] = field(default_factory=list)
    collapse_columns: list[str] = field(default_factory=list)

    def to_capture_json(self) -> str:
        """
        Serialize options for the Playwright capture script.

        :return: JSON string for capture_console_screenshot.mjs.
        :rtype: str
        """
        payload: dict[str, Any] = {
            "appearanceMode": self.appearance_mode,
            "view": self.view,
            "expandAll": self.expand_all,
            "expand": list(self.expand_columns),
            "collapse": list(self.collapse_columns),
        }
        return json.dumps(payload)

    def record_for_tests(self) -> None:
        """Record capture options for behavior-spec assertions."""
        os.environ[TEST_LAST_MODE_ENV] = self.appearance_mode
        os.environ[TEST_CAPTURE_OPTIONS_ENV] = self.to_capture_json()


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
    search_roots: list[Path]
    override = os.environ.get(TEST_SCRIPT_SEARCH_ROOT_ENV)
    if override:
        search_roots = [Path(override)]
    else:
        search_roots = [root, *root.parents]
    for directory in search_roots:
        candidate = directory / script_name
        if candidate.is_file():
            return candidate
    if os.environ.get(TEST_HIDE_PACKAGE_SCRIPT_ENV) == "1":
        raise ConsoleScreenshotError(
            "headless browser capture script not found (scripts/capture_console_screenshot.mjs)."
        )
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


def _normalize_appearance_mode(mode: str | None) -> str:
    """
    Normalize and validate screenshot appearance mode.

    :param mode: Requested mode or None for the default.
    :type mode: str | None
    :return: ``light`` or ``dark``.
    :rtype: str
    :raises ConsoleScreenshotError: When the mode is not light or dark.
    """
    resolved = (mode or DEFAULT_APPEARANCE_MODE).strip().lower()
    if resolved in {"light", "dark"}:
        return resolved
    raise ConsoleScreenshotError("appearance mode must be light or dark")


def _normalize_view(view: str | None) -> str | None:
    if view is None:
        return None
    resolved = view.strip().lower()
    if resolved in VALID_VIEWS:
        return resolved
    raise ConsoleScreenshotError("view must be one of: initiatives, epics, issues, all")


def build_capture_options(
    appearance_mode: str | None = None,
    view: str | None = None,
    expand_all: bool = False,
    expand_columns: list[str] | None = None,
    collapse_columns: list[str] | None = None,
) -> ScreenshotCaptureOptions:
    """
    Build validated screenshot capture options.

    :param appearance_mode: Console light/dark mode.
    :type appearance_mode: str | None
    :param view: Board type filter view.
    :type view: str | None
    :param expand_all: Expand every collapsed column before capture.
    :type expand_all: bool
    :param expand_columns: Status column keys to expand.
    :type expand_columns: list[str] | None
    :param collapse_columns: Status column keys to collapse.
    :type collapse_columns: list[str] | None
    :return: Validated capture options.
    :rtype: ScreenshotCaptureOptions
    """
    return ScreenshotCaptureOptions(
        appearance_mode=_normalize_appearance_mode(appearance_mode),
        view=_normalize_view(view),
        expand_all=expand_all,
        expand_columns=list(expand_columns or []),
        collapse_columns=list(collapse_columns or []),
    )


def capture_console_screenshot(
    root: Path,
    output: str | None = None,
    appearance_mode: str | None = None,
    view: str | None = None,
    expand_all: bool = False,
    expand_columns: list[str] | None = None,
    collapse_columns: list[str] | None = None,
) -> Path:
    """
    Capture a PNG screenshot of the console board to the requested path.

    :param root: Repository root path.
    :type root: Path
    :param output: Optional output file path relative to root unless absolute.
    :type output: str | None
    :param appearance_mode: Console appearance mode (``light`` or ``dark``).
    :type appearance_mode: str | None
    :param view: Board view filter (``initiatives``, ``epics``, ``issues``, or ``all``).
    :type view: str | None
    :param expand_all: Expand every collapsed status column before capture.
    :type expand_all: bool
    :param expand_columns: Status column keys to expand before capture.
    :type expand_columns: list[str] | None
    :param collapse_columns: Status column keys to collapse before capture.
    :type collapse_columns: list[str] | None
    :return: Path to the written PNG file.
    :rtype: Path
    :raises ConsoleScreenshotError: When capture fails or prerequisites are missing.
    """
    options = build_capture_options(
        appearance_mode=appearance_mode,
        view=view,
        expand_all=expand_all,
        expand_columns=expand_columns,
        collapse_columns=collapse_columns,
    )
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
        locate_capture_script(root)
        node_executable = shutil.which("node")
        if node_executable is None:
            raise ConsoleScreenshotError(
                "headless browser capture requires Node.js on PATH to run Playwright."
            )
        options.record_for_tests()
        os.environ[TEST_PREREQUISITES_VERIFIED_ENV] = "1"
        output_path.write_bytes(_MOCK_PNG_BYTES)
        return output_path

    port = resolve_console_port(root)
    console_url = f"http://127.0.0.1:{port}/"
    if os.environ.get(TEST_FORCE_NODE_MISSING_ENV) == "1":
        node_executable = None
    else:
        node_executable = shutil.which("node")
    if node_executable is None:
        raise ConsoleScreenshotError(
            "headless browser capture requires Node.js on PATH to run Playwright."
        )

    script_path = locate_capture_script(root)
    result = subprocess.run(
        [
            node_executable,
            str(script_path),
            console_url,
            str(output_path),
            options.to_capture_json(),
        ],
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
        raise ConsoleScreenshotError(
            "headless browser capture did not produce an output file."
        )
    return output_path
