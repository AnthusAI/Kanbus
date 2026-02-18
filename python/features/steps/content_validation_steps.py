"""Behave steps for code block content validation."""

from __future__ import annotations

import shlex

from behave import given, when

from features.steps.shared import run_cli


@given('external validator "{tool}" is not available')
def given_external_validator_not_available(context: object, tool: str) -> None:
    """Mark an external validator as not available.

    In test environments, these tools are typically not installed,
    so this step is essentially a no-op. The validation code checks
    for the tool on PATH and skips silently if not found.
    """
    _ = tool


@when("I create an issue with description containing:")
def when_create_with_description(context: object) -> None:
    description = context.text.strip()
    quoted_description = shlex.quote(description)
    run_cli(
        context,
        f"kanbus create Test Issue --description {quoted_description}",
    )


@when("I create an issue with --no-validate and description containing:")
def when_create_no_validate_with_description(context: object) -> None:
    description = context.text.strip()
    quoted_description = shlex.quote(description)
    run_cli(
        context,
        f"kanbus create Test Issue --no-validate --description {quoted_description}",
    )


@when('I comment on "{identifier}" with text containing:')
def when_comment_with_text(context: object, identifier: str) -> None:
    text = context.text.strip()
    quoted_text = shlex.quote(text)
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = "dev@example.com"
    context.environment_overrides = overrides
    run_cli(context, f"kanbus comment {identifier} {quoted_text}")


@when('I comment on "{identifier}" with --no-validate and text containing:')
def when_comment_no_validate_with_text(context: object, identifier: str) -> None:
    text = context.text.strip()
    quoted_text = shlex.quote(text)
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = "dev@example.com"
    context.environment_overrides = overrides
    run_cli(context, f"kanbus comment {identifier} --no-validate {quoted_text}")


@when('I update "{identifier}" with description containing:')
def when_update_with_description(context: object, identifier: str) -> None:
    description = context.text.strip()
    quoted_description = shlex.quote(description)
    run_cli(
        context,
        f"kanbus update {identifier} --description {quoted_description}",
    )
