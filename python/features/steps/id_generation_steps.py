"""Behave steps for issue ID generation."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from behave import given, then, when

import os

from taskulus.ids import (
    IssueIdentifierRequest,
    generate_issue_identifier,
    generate_many_identifiers,
)
from taskulus import ids as ids_module


@given('a project with prefix "{prefix}"')
def given_project_prefix(context: object, prefix: str) -> None:
    context.id_prefix = prefix
    context.existing_ids = set()


@given('a project with an existing issue "{identifier}"')
def given_project_with_existing_issue(context: object, identifier: str) -> None:
    context.existing_ids = {identifier}
    context.id_prefix = identifier.split("-")[0]


@given('the hash function would produce "{digest}" for the next issue')
def given_hash_override(context: object, digest: str) -> None:
    context.hash_sequence = [digest, "bbbbbb"]


@given('the random bytes are fixed to "{hex_value}"')
def given_random_bytes_fixed(context: object, hex_value: str) -> None:
    context.test_random_bytes_hex = hex_value


@given("the existing issue set includes the generated ID")
def given_existing_set_includes_generated(context: object) -> None:
    prefix = getattr(context, "id_prefix", "tsk")
    test_bytes_hex = getattr(context, "test_random_bytes_hex", "00")
    test_bytes = bytes.fromhex(test_bytes_hex)
    digest = ids_module._hash_identifier_material(
        "Test title",
        datetime(2026, 2, 11, tzinfo=timezone.utc),
        test_bytes,
    )
    context.existing_ids = {f"{prefix}-{digest}"}


@when("I generate an issue ID")
def when_generate_issue_id(context: object) -> None:
    prefix = getattr(context, "id_prefix", "tsk")
    existing = getattr(context, "existing_ids", set())
    original_hash = None
    if getattr(context, "hash_sequence", None):
        sequence = list(context.hash_sequence)
        original_hash = ids_module._hash_identifier_material

        def fake_hash(title: str, created_at: datetime, random_bytes: bytes) -> str:
            if sequence:
                return sequence.pop(0)
            return original_hash(title, created_at, random_bytes)

        ids_module._hash_identifier_material = fake_hash
    try:
        request = IssueIdentifierRequest(
            title="Test title",
            existing_ids=existing,
            prefix=prefix,
            created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        )
        context.generated_id = generate_issue_identifier(request).identifier
    finally:
        if original_hash is not None:
            ids_module._hash_identifier_material = original_hash


@when("I generate an issue ID expecting failure")
def when_generate_issue_id_failure(context: object) -> None:
    prefix = getattr(context, "id_prefix", "tsk")
    existing = getattr(context, "existing_ids", set())
    test_bytes_hex = getattr(context, "test_random_bytes_hex", "")
    if test_bytes_hex:
        os.environ["TASKULUS_TEST_RANDOM_BYTES"] = test_bytes_hex
    try:
        request = IssueIdentifierRequest(
            title="Test title",
            existing_ids=existing,
            prefix=prefix,
            created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        )
        try:
            generate_issue_identifier(request)
            context.id_generation_error = None
        except RuntimeError as error:
            context.id_generation_error = str(error)
    finally:
        if test_bytes_hex:
            os.environ.pop("TASKULUS_TEST_RANDOM_BYTES", None)


@when("I generate 100 issue IDs")
def when_generate_many_issue_ids(context: object) -> None:
    prefix = getattr(context, "id_prefix", "tsk")
    context.generated_ids = generate_many_identifiers("Test title", prefix, 100)


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
