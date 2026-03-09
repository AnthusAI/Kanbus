"""Behave steps for text editor CLI (edit subcommands)."""

from __future__ import annotations

from pathlib import Path

from behave import given, then


@given('a file "{path}" with content "{content}"')
def given_file_with_content_string(context: object, path: str, content: str) -> None:
    """Create a file at the given path with inline string content."""
    working_directory = Path(context.working_directory)
    full_path = working_directory / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.replace("\\n", "\n")
    full_path.write_text(normalized, encoding="utf-8")


@given('a file "{path}" with content')
@given('a file "{path}" with content:')
def given_file_with_content(context: object, path: str) -> None:
    """Create a file at the given path with content from the step docstring."""
    working_directory = Path(context.working_directory)
    full_path = working_directory / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    content = (context.text or "").strip()
    full_path.write_text(content, encoding="utf-8")


@then('"{first}" should appear before "{second}" in the file "{path}"')
def then_first_before_second_in_file(
    context: object, first: str, second: str, path: str
) -> None:
    """Assert that first text appears before second text in the given file."""
    full_path = Path(context.working_directory) / path
    content = full_path.read_text(encoding="utf-8")
    first_index = content.find(first)
    second_index = content.find(second)
    assert first_index != -1, f"{first!r} not found in file"
    assert second_index != -1, f"{second!r} not found in file"
    assert first_index < second_index, f"{first!r} did not appear before {second!r}"


@then('"{first}" should appear after "{second}" in the file "{path}"')
def then_first_after_second_in_file(
    context: object, first: str, second: str, path: str
) -> None:
    """Assert that first text appears after second text in the given file."""
    full_path = Path(context.working_directory) / path
    content = full_path.read_text(encoding="utf-8")
    first_index = content.find(first)
    second_index = content.find(second)
    assert first_index != -1, f"{first!r} not found in file"
    assert second_index != -1, f"{second!r} not found in file"
    assert second_index < first_index, f"{first!r} did not appear after {second!r}"
