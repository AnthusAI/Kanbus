"""Regression test for legacy summary comment validation.

Tests that old summary comments with only text (no data.rewritten_description)
can still be loaded. Prevents validation errors that brick the entire board
when one comment is missing the new structured data format.
"""

import pytest
from kanbus.models import IssueComment


def test_summary_comment_with_structured_data():
    """New format: summary with data.rewritten_description and activity_summary."""
    comment = IssueComment(
        id="test-id",
        author="system:summary",
        text="",
        created_at="2026-08-27T00:00:00Z",
        comment_type="summary",
        data={
            "rewritten_description": "Short description",
            "activity_summary": "Activity summary",
        },
    )
    assert comment.comment_type == "summary"


def test_summary_comment_with_legacy_text_only():
    """Legacy format: summary with only text, no structured data."""
    comment = IssueComment(
        id="test-id",
        author="system:summary",
        text="### Issue Metadata\n- **ID**: `test`\n\n### Description\nOld format summary",
        created_at="2026-08-27T00:00:00Z",
        comment_type="summary",
        data={},
    )
    assert comment.comment_type == "summary"


def test_summary_comment_without_text_or_data_fails():
    """Summary comment with neither text nor structured data should fail."""
    with pytest.raises(ValueError, match="summary comment requires either"):
        IssueComment(
            id="test-id",
            author="system:summary",
            text="",
            created_at="2026-08-27T00:00:00Z",
            comment_type="summary",
            data={},
        )


def test_summary_comment_with_incomplete_structured_data_but_text_succeeds():
    """Summary with incomplete data but valid text should still succeed (legacy fallback)."""
    comment = IssueComment(
        id="test-id",
        author="system:summary",
        text="Legacy summary text",
        created_at="2026-08-27T00:00:00Z",
        comment_type="summary",
        data={"rewritten_description": "Only partial data"},
    )
    assert comment.comment_type == "summary"


def test_normal_comment_requires_text():
    """Normal (non-summary) comments still require text."""
    with pytest.raises(ValueError, match="comment text is required"):
        IssueComment(
            id="test-id",
            author="user",
            text="",
            created_at="2026-08-27T00:00:00Z",
            data={},
        )
