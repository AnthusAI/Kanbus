"""Behave steps for console board screenshot."""

from __future__ import annotations

import json
import os
from pathlib import Path

from behave import given, then

from kanbus.console_screenshot import (
    TEST_CAPTURE_OPTIONS_ENV,
    TEST_LAST_MODE_ENV,
    TEST_PREREQUISITES_VERIFIED_ENV,
)


def _load_capture_options() -> dict:
    raw = os.environ.get(TEST_CAPTURE_OPTIONS_ENV)
    if not raw:
        raise AssertionError("screenshot capture options were not recorded")
    return json.loads(raw)


@given("screenshot capture is mocked to succeed")
def given_screenshot_capture_mocked_success(context: object) -> None:
    os.environ.pop(TEST_LAST_MODE_ENV, None)
    os.environ.pop(TEST_CAPTURE_OPTIONS_ENV, None)
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_TEST_SCREENSHOT_MOCK"] = "success"
    overrides.pop(TEST_LAST_MODE_ENV, None)
    overrides.pop(TEST_CAPTURE_OPTIONS_ENV, None)
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
    os.environ["CONSOLE_PORT"] = str(port)


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
