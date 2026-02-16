"""Behave steps for CLI output assertions."""

from __future__ import annotations

import re

from behave import then

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@then('stdout should contain "{text}"')
def then_stdout_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    stdout = _strip_ansi(context.result.stdout)
    if normalized not in stdout:
        print(f"Expected '{normalized}' to be in stdout, but it wasn't")
        print(f"ACTUAL STDOUT:\n{stdout}")
        print(f"Exit code: {context.result.exit_code}")
        print(f"STDERR:\n{context.result.stderr}")
    assert normalized in stdout


@then('stdout should not contain "{text}"')
def then_stdout_not_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    stdout = _strip_ansi(context.result.stdout)
    if normalized in stdout:
        print(f"Expected '{normalized}' to NOT be in stdout, but it was")
        print(f"ACTUAL STDOUT:\n{stdout}")
    assert normalized not in stdout


@then('stderr should contain "{text}"')
def then_stderr_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    stderr = _strip_ansi(context.result.stderr)
    assert normalized in stderr


@then('stdout should contain "{text}" once')
def then_stdout_contains_once(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    stdout = _strip_ansi(context.result.stdout)
    assert stdout.count(normalized) == 1


@then('stdout should list "{first}" before "{second}"')
def then_stdout_lists_before(context: object, first: str, second: str) -> None:
    stdout = _strip_ansi(context.result.stdout)
    first_index = stdout.find(first)
    second_index = stdout.find(second)
    assert first_index != -1, f"{first} not found in stdout"
    assert second_index != -1, f"{second} not found in stdout"
    assert first_index < second_index, f"{first} did not appear before {second}"


@then('stdout should contain the external project path for "{identifier}"')
def then_stdout_contains_external_project_path(
    context: object, identifier: str
) -> None:
    project_path = getattr(context, "external_project_path", None)
    assert project_path is not None
    lines = _strip_ansi(context.result.stdout).splitlines()
    matches = [
        line for line in lines if identifier in line and str(project_path) in line
    ]
    assert matches, "no line contains both external project path and identifier"


@then('stdout should list issue "{identifier}"')
def then_stdout_lists_issue(context: object, identifier: str) -> None:
    """Check that an issue ID appears as a field in list output (not just as substring)."""
    stdout = _strip_ansi(context.result.stdout)
    lines = stdout.splitlines()
    # List output format: "T issue-id assignee status priority title"
    # Check if any line has the identifier as the second field
    pattern = re.compile(r"^[A-Z]\s+" + re.escape(identifier) + r"\s+")
    matches = [line for line in lines if pattern.match(line)]
    if not matches:
        print(f"Expected issue '{identifier}' to appear in list output")
        print(f"ACTUAL STDOUT:\n{stdout}")
    assert matches, f"issue {identifier} not found in list output"


@then('stdout should not list issue "{identifier}"')
def then_stdout_not_lists_issue(context: object, identifier: str) -> None:
    """Check that an issue ID does NOT appear as a field in list output."""
    stdout = _strip_ansi(context.result.stdout)
    lines = stdout.splitlines()
    # List output format: "T issue-id assignee status priority title"
    # Check if any line has the identifier as the second field
    pattern = re.compile(r"^[A-Z]\s+" + re.escape(identifier) + r"\s+")
    matches = [line for line in lines if pattern.match(line)]
    if matches:
        print(f"Expected issue '{identifier}' to NOT appear in list output, but it did")
        print(f"ACTUAL STDOUT:\n{stdout}")
    assert (
        not matches
    ), f"issue {identifier} found in list output but should not be there"
