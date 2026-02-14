"""Behave steps for issue key representation."""

from __future__ import annotations

from behave import given, then, when

from kanbus.ids import format_issue_key


@given('an issue identifier "{identifier}"')
def given_issue_identifier(context: object, identifier: str) -> None:
    context.issue_identifier = identifier


@given('the display context is "{context_value}"')
def given_display_context(context: object, context_value: str) -> None:
    context.project_context = context_value == "project"


@when("I format the issue key")
def when_format_issue_key(context: object) -> None:
    identifier = getattr(context, "issue_identifier", "")
    project_context = getattr(context, "project_context", False)
    context.formatted_issue_key = format_issue_key(
        identifier=identifier,
        project_context=project_context,
    )


@then('the formatted key should be "{expected}"')
def then_formatted_key_should_match(context: object, expected: str) -> None:
    assert getattr(context, "formatted_issue_key", None) == expected
