from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import console_screenshot


def test_locate_capture_script_override_and_hidden_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(console_screenshot.TEST_SCRIPT_SEARCH_ROOT_ENV, str(tmp_path))
    with pytest.raises(console_screenshot.ConsoleScreenshotError, match="not found"):
        monkeypatch.setenv(console_screenshot.TEST_HIDE_PACKAGE_SCRIPT_ENV, "1")
        console_screenshot.locate_capture_script(tmp_path)

    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    script_path = script_dir / "capture_console_screenshot.mjs"
    script_path.write_text("export {}\n", encoding="utf-8")
    monkeypatch.delenv(console_screenshot.TEST_HIDE_PACKAGE_SCRIPT_ENV, raising=False)
    assert console_screenshot.locate_capture_script(tmp_path) == script_path


def test_mock_mode_and_success_requires_node(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("KANBUS_TEST_SCREENSHOT_MOCK", raising=False)
    assert console_screenshot._mock_mode() is None
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_MOCK", "weird")
    assert console_screenshot._mock_mode() == "weird"

    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_MOCK", "success")
    monkeypatch.setenv(console_screenshot.TEST_FORCE_NODE_MISSING_ENV, "1")
    monkeypatch.setattr(
        console_screenshot, "is_console_server_running", lambda _root: True
    )
    monkeypatch.setattr(
        console_screenshot,
        "locate_capture_script",
        lambda _root: tmp_path / "scripts" / "capture_console_screenshot.mjs",
    )
    with pytest.raises(console_screenshot.ConsoleScreenshotError, match="Node.js"):
        console_screenshot.capture_console_screenshot(tmp_path)
