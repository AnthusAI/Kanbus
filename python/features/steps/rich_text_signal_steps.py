"""Behave steps for rich text quality signal scenarios."""

from __future__ import annotations

import re

from behave import then, when

from features.steps.shared import (
    load_project_directory,
    read_issue_file,
    run_cli,
    run_cli_args,
    capture_issue_identifier,
)


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@when('I create an issue with a literal backslash-n description "{description}"')
def when_create_issue_with_literal_backslash_n_description(
    context: object, description: str
) -> None:
    """Create an issue with a description containing literal \\n sequences.

    :param context: Behave context object.
    :type context: object
    :param description: Description text with literal backslash-n characters.
    :type description: str
    """
    run_cli(context, f"kanbus create Test Issue --description {description!r}")


@when('I create an issue with a plain-text description "{description}"')
def when_create_issue_with_plain_text_description(
    context: object, description: str
) -> None:
    """Create an issue with a plain text description containing no Markdown.

    :param context: Behave context object.
    :type context: object
    :param description: Plain text description.
    :type description: str
    """
    run_cli(context, f"kanbus create Test Issue --description {description!r}")


@when("I create an issue with a clean multi-line description")
def when_create_issue_with_clean_multi_line_description(context: object) -> None:
    """Create an issue with a real multi-line description (no literal \\n sequences).

    Passes the description as a list to avoid shell escaping issues.

    :param context: Behave context object.
    :type context: object
    """
    description = "First line\nSecond line\nThird line"
    run_cli_args(context, ["create", "Test", "Issue", "--description", description])


@when('I comment on "{identifier}" with literal backslash-n text "{text}"')
def when_comment_with_literal_backslash_n_text(
    context: object, identifier: str, text: str
) -> None:
    """Add a comment containing literal backslash-n sequences.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param text: Comment text with literal backslash-n characters.
    :type text: str
    """
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = "dev@example.com"
    context.environment_overrides = overrides
    run_cli(context, f"kanbus comment {identifier} {text!r}")


@when('I comment on "{identifier}" with plain text "{text}"')
def when_comment_with_plain_text(context: object, identifier: str, text: str) -> None:
    """Add a plain text comment (no Markdown formatting).

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param text: Plain comment text.
    :type text: str
    """
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = "dev@example.com"
    context.environment_overrides = overrides
    run_cli(context, f"kanbus comment {identifier} {text!r}")


@when('I update "{identifier}" with plain-text description "{description}"')
def when_update_issue_with_plain_text_description(
    context: object, identifier: str, description: str
) -> None:
    """Update an issue with a plain-text description.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param description: Plain text description.
    :type description: str
    """
    run_cli(context, f"kanbus update {identifier} --description {description!r}")


@then("the stored description contains real newlines")
def then_stored_description_contains_real_newlines(context: object) -> None:
    """Assert the last created issue has real newlines in its description.

    :param context: Behave context object.
    :type context: object
    """
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert (
        "\n" in issue.description
    ), f"Expected real newlines in description, got: {issue.description!r}"
    assert (
        "\\n" not in issue.description
    ), f"Expected no literal backslash-n sequences in description, got: {issue.description!r}"


@then('stderr should not contain "{text}"')
def then_stderr_not_contains_text(context: object, text: str) -> None:
    """Assert that stderr does not contain the given text.

    :param context: Behave context object.
    :type context: object
    :param text: Text that should not appear in stderr.
    :type text: str
    """
    normalized = text.replace('\\"', '"')
    stderr = _strip_ansi(context.result.stderr)
    assert normalized not in stderr, (
        f"Expected stderr NOT to contain '{normalized}', but it did.\n"
        f"STDERR:\n{stderr}"
    )
