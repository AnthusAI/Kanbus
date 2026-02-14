"""Behave steps for issue ID generation."""

from __future__ import annotations

import re

from behave import given, then, when

from kanbus.ids import (
    IssueIdentifierRequest,
    generate_issue_identifier,
    generate_many_identifiers,
    set_test_uuid_sequence,
)


@given('a project with project key "{project_key}"')
def given_project_key(context: object, project_key: str) -> None:
    context.id_prefix = project_key
    context.existing_ids = set()


@given('a project with an existing issue "{identifier}"')
def given_project_with_existing_issue(context: object, identifier: str) -> None:
    context.existing_ids = {identifier}
    context.id_prefix = identifier.split("-")[0]


@when("I generate an issue ID")
def when_generate_issue_id(context: object) -> None:
    prefix = getattr(context, "id_prefix", "kanbus")
    existing = getattr(context, "existing_ids", set())
    request = IssueIdentifierRequest(
        title="Test title",
        existing_ids=existing,
        prefix=prefix,
    )
    context.generated_id = generate_issue_identifier(request).identifier


@when("I generate 100 issue IDs")
def when_generate_many_issue_ids(context: object) -> None:
    prefix = getattr(context, "id_prefix", "kanbus")
    context.generated_ids = generate_many_identifiers("Test title", prefix, 100)


@given('the UUID generator always returns "{uuid_text}"')
def given_uuid_generator_returns(context: object, uuid_text: str) -> None:
    set_test_uuid_sequence([uuid_text] * 11)


@when("I attempt to generate an issue ID")
def when_attempt_generate_issue_id(context: object) -> None:
    prefix = getattr(context, "id_prefix", "kanbus")
    existing = getattr(context, "existing_ids", set())
    request = IssueIdentifierRequest(
        title="Test title",
        existing_ids=existing,
        prefix=prefix,
    )
    try:
        context.generated_id = generate_issue_identifier(request).identifier
        context.id_generation_error = None
    except RuntimeError as error:
        context.generated_id = None
        context.id_generation_error = str(error)


@then('the ID should match the pattern "{pattern}"')
def then_id_matches_pattern(context: object, pattern: str) -> None:
    regex = re.compile(f"^{pattern}$")
    assert regex.match(context.generated_id)


@then("all 100 IDs should be unique")
def then_ids_are_unique(context: object) -> None:
    assert len(context.generated_ids) == 100


@then('the ID should not be "{forbidden}"')
def then_id_not_collision(context: object, forbidden: str) -> None:
    assert context.generated_id != forbidden


@then('ID generation should fail with "{message}"')
def then_id_generation_failed(context: object, message: str) -> None:
    assert context.id_generation_error == message
