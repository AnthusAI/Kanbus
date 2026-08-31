"""Behave steps for console board screenshot."""

from __future__ import annotations

import json
import os
from pathlib import Path

from behave import given, then

from kanbus.console_screenshot import (
    TEST_CAPTURE_OPTIONS_ENV,
    TEST_LAST_MODE_ENV,
    TEST_NODE_EXECUTABLE_ENV,
    TEST_PREREQUISITES_VERIFIED_ENV,
)


def _clear_live_capture_overrides(overrides: dict) -> None:
    overrides.pop("KANBUS_TEST_SCREENSHOT_MOCK", None)
    overrides.pop(TEST_LAST_MODE_ENV, None)
    overrides.pop(TEST_CAPTURE_OPTIONS_ENV, None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT", None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", None)
    overrides.pop(TEST_NODE_EXECUTABLE_ENV, None)


def _write_fake_node_executable(working_directory: Path, script_body: str) -> Path:
    script_path = working_directory / "fake-node-screenshot.sh"
    script_path.write_text(script_body, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def _load_capture_options() -> dict:
    raw = os.environ.get(TEST_CAPTURE_OPTIONS_ENV)
    if not raw:
        raise AssertionError("screenshot capture options were not recorded")
    return json.loads(raw)


@given("screenshot capture is mocked to succeed")
def given_screenshot_capture_mocked_success(context: object) -> None:
    os.environ.pop(TEST_LAST_MODE_ENV, None)
    os.environ.pop(TEST_CAPTURE_OPTIONS_ENV, None)
    os.environ.pop("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", None)
    os.environ.pop("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT", None)
    os.environ.pop("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", None)
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_TEST_SCREENSHOT_MOCK"] = "success"
    overrides.pop(TEST_LAST_MODE_ENV, None)
    overrides.pop(TEST_CAPTURE_OPTIONS_ENV, None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT", None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", None)
    context.environment_overrides = overrides


@given("screenshot capture is mocked as unavailable")
def given_screenshot_capture_mocked_unavailable(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_TEST_SCREENSHOT_MOCK"] = "unavailable"
    context.environment_overrides = overrides


@given("the environment variable CONSOLE_PORT is set to the console server port")
def given_console_port_matches_server(context: object) -> None:
    port = getattr(context, "console_server_port", None)
    assert (
        port is not None
    ), "console server must be running before setting CONSOLE_PORT"
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["CONSOLE_PORT"] = str(port)
    context.environment_overrides = overrides


@given("the capture script cannot be located")
def given_capture_script_cannot_be_located(context: object) -> None:
    working_directory = Path(context.working_directory)
    empty_root = working_directory / "empty-script-root"
    empty_root.mkdir(parents=True, exist_ok=True)
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides.pop("KANBUS_TEST_SCREENSHOT_MOCK", None)
    overrides.pop(TEST_LAST_MODE_ENV, None)
    overrides.pop(TEST_CAPTURE_OPTIONS_ENV, None)
    overrides.pop("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", None)
    overrides["KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT"] = str(empty_root)
    overrides["KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT"] = "1"
    context.environment_overrides = overrides


@given("Node.js is unavailable for screenshot capture")
def given_node_unavailable_for_screenshot(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    _clear_live_capture_overrides(overrides)
    overrides["KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING"] = "1"
    context.environment_overrides = overrides


@given(
    "screenshot capture uses a Node executable that reports Playwright is unavailable"
)
def given_fake_node_reports_playwright_unavailable(context: object) -> None:
    working_directory = Path(context.working_directory)
    script_path = _write_fake_node_executable(
        working_directory,
        "#!/bin/sh\nprintf 'playwright browser missing\\n' >&2\nexit 1\n",
    )
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    _clear_live_capture_overrides(overrides)
    overrides[TEST_NODE_EXECUTABLE_ENV] = str(script_path)
    context.environment_overrides = overrides


@given(
    "screenshot capture uses a Node executable that exits successfully without output"
)
def given_fake_node_exits_without_output(context: object) -> None:
    working_directory = Path(context.working_directory)
    script_path = _write_fake_node_executable(
        working_directory,
        "#!/bin/sh\nexit 0\n",
    )
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    _clear_live_capture_overrides(overrides)
    overrides[TEST_NODE_EXECUTABLE_ENV] = str(script_path)
    context.environment_overrides = overrides


@given("screenshot capture uses a Node executable that fails with a generic error")
def given_fake_node_fails_generically(context: object) -> None:
    working_directory = Path(context.working_directory)
    script_path = _write_fake_node_executable(
        working_directory,
        "#!/bin/sh\nprintf 'capture harness exploded\\n' >&2\nexit 1\n",
    )
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    _clear_live_capture_overrides(overrides)
    overrides[TEST_NODE_EXECUTABLE_ENV] = str(script_path)
    context.environment_overrides = overrides


def _resolve_working_path(context: object, path: str) -> Path:
    working_directory = Path(context.working_directory)
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return working_directory / candidate


@then('a PNG file should exist at "{path}"')
def then_png_file_should_exist(context: object, path: str) -> None:
    file_path = _resolve_working_path(context, path)
    assert file_path.is_file(), f"expected PNG at {file_path}"
    header = file_path.read_bytes()[:8]
    assert header == b"\x89PNG\r\n\x1a\n", f"expected PNG header at {file_path}"


@then('the PNG file at "{path}" should be larger than {size:d} bytes')
def then_png_file_larger_than(context: object, path: str, size: int) -> None:
    file_path = _resolve_working_path(context, path)
    assert file_path.is_file(), f"expected PNG at {file_path}"
    assert file_path.stat().st_size > size


@then('the screenshot appearance mode should be "{mode}"')
def then_screenshot_appearance_mode(context: object, mode: str) -> None:
    recorded = os.environ.get(TEST_LAST_MODE_ENV)
    assert recorded == mode, f"expected appearance mode {mode}, got {recorded}"


@then('the screenshot capture view should be "{view}"')
def then_screenshot_capture_view(context: object, view: str) -> None:
    options = _load_capture_options()
    assert (
        options.get("view") == view
    ), f"expected view {view}, got {options.get('view')}"


@then("screenshot capture expand-all should be enabled")
def then_screenshot_capture_expand_all(context: object) -> None:
    options = _load_capture_options()
    assert options.get("expandAll") is True


@then("screenshot capture prerequisites should be verified")
def then_screenshot_capture_prerequisites_verified(context: object) -> None:
    assert (
        os.environ.get(TEST_PREREQUISITES_VERIFIED_ENV) == "1"
    ), "expected mocked screenshot capture to verify prerequisites"


@then('the screenshot capture expanded columns should include "{column}"')
def then_screenshot_capture_expanded_columns_include(
    context: object, column: str
) -> None:
    options = _load_capture_options()
    expanded = options.get("expand") or []
    assert column in expanded, f"expected expand to include {column}, got {expanded}"


@then('the screenshot capture collapsed columns should include "{column}"')
def then_screenshot_capture_collapsed_columns_include(
    context: object, column: str
) -> None:
    options = _load_capture_options()
    collapsed = options.get("collapse") or []
    assert (
        column in collapsed
    ), f"expected collapse to include {column}, got {collapsed}"
