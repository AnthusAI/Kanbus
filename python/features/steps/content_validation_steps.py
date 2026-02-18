"""Behave steps for code block content validation."""

from __future__ import annotations

import shlex
import shutil
import subprocess

from behave import given, then, when

from features.steps.shared import run_cli
from kanbus.content_validation import ContentValidationError, validate_code_blocks


@given('external validator "{tool}" is not available')
def given_external_validator_not_available(context: object, tool: str) -> None:
    """Mark an external validator as not available.

    In test environments, these tools are typically not installed,
    so this step is essentially a no-op. The validation code checks
    for the tool on PATH and skips silently if not found.
    """
    _ = tool


@given('external validator "{tool}" is available and returns success')
def given_external_validator_available_success(context: object, tool: str) -> None:
    if not hasattr(context, "original_shutil_which"):
        context.original_shutil_which = shutil.which
    if not hasattr(context, "original_subprocess_run"):
        context.original_subprocess_run = subprocess.run

    def fake_which(name: str) -> str | None:
        if name == tool:
            return f"/usr/bin/{tool}"
        return context.original_shutil_which(name)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    shutil.which = fake_which
    subprocess.run = fake_run


@given('external validator "{tool}" is available and returns error "{message}"')
def given_external_validator_available_error(
    context: object, tool: str, message: str
) -> None:
    if not hasattr(context, "original_shutil_which"):
        context.original_shutil_which = shutil.which
    if not hasattr(context, "original_subprocess_run"):
        context.original_subprocess_run = subprocess.run

    def fake_which(name: str) -> str | None:
        if name == tool:
            return f"/usr/bin/{tool}"
        return context.original_shutil_which(name)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr=message)

    shutil.which = fake_which
    subprocess.run = fake_run


@given('external validator "{tool}" times out')
def given_external_validator_timeout(context: object, tool: str) -> None:
    if not hasattr(context, "original_shutil_which"):
        context.original_shutil_which = shutil.which
    if not hasattr(context, "original_subprocess_run"):
        context.original_subprocess_run = subprocess.run

    def fake_which(name: str) -> str | None:
        if name == tool:
            return f"/usr/bin/{tool}"
        return context.original_shutil_which(name)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=args, timeout=30)

    shutil.which = fake_which
    subprocess.run = fake_run


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


@when("I validate code blocks directly:")
def when_validate_code_blocks_directly(context: object) -> None:
    text = context.text.strip()
    try:
        validate_code_blocks(text)
        context.validation_error = None
    except ContentValidationError as error:
        context.validation_error = error


@then("the code block validation should succeed")
def then_code_block_validation_succeeds(context: object) -> None:
    assert getattr(context, "validation_error", None) is None


@then('the code block validation should fail with "{message}"')
def then_code_block_validation_fails(context: object, message: str) -> None:
    error = getattr(context, "validation_error", None)
    assert error is not None
    assert message in str(error)
