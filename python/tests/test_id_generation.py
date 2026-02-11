"""Unit tests for issue ID generation."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from taskulus.ids import (
    IssueIdentifierRequest,
    _hash_identifier_material,
    generate_issue_identifier,
    generate_many_identifiers,
)


def test_generated_ids_follow_prefix_hex_format() -> None:
    """Generated IDs should match prefix-hex format."""
    request = IssueIdentifierRequest(title="Test", prefix="tsk")
    result = generate_issue_identifier(request)
    assert re.match(r"^tsk-[0-9a-f]{6}$", result.identifier)


def test_generated_ids_are_unique() -> None:
    """Generated IDs should be unique across multiple generations."""
    ids = generate_many_identifiers("Test", "tsk", 100)
    assert len(ids) == 100


def test_collision_is_avoided(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collisions should trigger retries and produce a different ID."""
    fixed_time = datetime(2025, 2, 10, tzinfo=timezone.utc)

    def fake_token_bytes(_: int) -> bytes:
        return b"collision"

    monkeypatch.setattr("taskulus.ids.secrets.token_bytes", fake_token_bytes)

    request = IssueIdentifierRequest(
        title="Test",
        prefix="tsk",
        existing_ids={"tsk-aaaaaa"},
        created_at=fixed_time,
    )

    result = generate_issue_identifier(request)
    assert result.identifier != "tsk-aaaaaa"
    assert re.match(r"^tsk-[0-9a-f]{6}$", result.identifier)


def test_generation_fails_after_ten_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_time = datetime(2025, 2, 10, tzinfo=timezone.utc)

    def fake_token_bytes(_: int) -> bytes:
        return b"collision"

    monkeypatch.setattr("taskulus.ids.secrets.token_bytes", fake_token_bytes)

    digest = _hash_identifier_material("Test", fixed_time, b"collision")
    request = IssueIdentifierRequest(
        title="Test",
        prefix="tsk",
        existing_ids={f"tsk-{digest}"},
        created_at=fixed_time,
    )

    with pytest.raises(
        RuntimeError, match="unable to generate unique id after 10 attempts"
    ):
        generate_issue_identifier(request)
