from __future__ import annotations

from datetime import datetime, timezone

from kanbus.comment_summary import (
    get_comment_display_text,
    get_summary_activity_summary,
    get_summary_rewritten_description,
    get_virtualized_description,
)
from kanbus.models import IssueComment

from test_helpers import build_issue


def _summary_comment(**data: object) -> IssueComment:
    return IssueComment.model_validate(
        {
            "id": "sum1",
            "author": "agent",
            "text": "Fallback activity",
            "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
            "comment_type": "summary",
            "data": data,
        }
    )


def test_summary_rewritten_description_ignores_empty_value() -> None:
    comment = _summary_comment(rewritten_description="")
    assert get_summary_rewritten_description(comment) is None


def test_summary_activity_falls_back_to_comment_text() -> None:
    comment = _summary_comment(activity_summary="")
    assert get_summary_activity_summary(comment) == "Fallback activity"


def test_virtualized_description_uses_rewritten_summary() -> None:
    issue = build_issue("kanbus-summary")
    issue.description = "Original description"
    issue.comments = [_summary_comment(rewritten_description="Compacted description")]
    assert get_virtualized_description(issue) == "Compacted description"
    assert get_comment_display_text(issue.comments[0]) == "Fallback activity"
