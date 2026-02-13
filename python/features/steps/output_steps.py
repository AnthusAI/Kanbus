"""Behave steps for CLI output assertions."""

from __future__ import annotations

from behave import then


@then('stdout should contain "{text}"')
def then_stdout_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    assert normalized in context.result.stdout


@then('stdout should not contain "{text}"')
def then_stdout_not_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    assert normalized not in context.result.stdout


@then('stderr should contain "{text}"')
def then_stderr_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    assert normalized in context.result.stderr


@then('stdout should contain "{text}" once')
def then_stdout_contains_once(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    assert context.result.stdout.count(normalized) == 1


@then('stdout should contain the external project path for "{identifier}"')
def then_stdout_contains_external_project_path(
    context: object, identifier: str
) -> None:
    project_path = getattr(context, "external_project_path", None)
    assert project_path is not None
    lines = context.result.stdout.splitlines()
    matches = [
        line for line in lines if identifier in line and str(project_path) in line
    ]
    assert matches, "no line contains both external project path and identifier"
