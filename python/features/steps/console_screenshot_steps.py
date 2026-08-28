"""Behave steps for console board screenshot."""

from __future__ import annotations

from pathlib import Path

from behave import given, then


@given("screenshot capture is mocked to succeed")
def given_screenshot_capture_mocked_success(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_TEST_SCREENSHOT_MOCK"] = "success"
    context.environment_overrides = overrides


@given("screenshot capture is mocked as unavailable")
def given_screenshot_capture_mocked_unavailable(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_TEST_SCREENSHOT_MOCK"] = "unavailable"
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
