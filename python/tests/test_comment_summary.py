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
    return IssueComment(
        author="agent",
        text="fallback activity",
        created_at=datetime(2026, 3, 6, tzinfo=timezone.utc),
        comment_type="summary",
        data=data,
    )


def test_summary_comment_helpers_cover_empty_and_fallback_paths() -> None:
    empty_rewritten = _summary_comment(rewritten_description="")
    assert get_summary_rewritten_description(empty_rewritten) is None

    activity_fallback = _summary_comment()
    assert get_summary_activity_summary(activity_fallback) == "fallback activity"
    assert get_comment_display_text(activity_fallback) == "fallback activity"

    issue = build_issue("kanbus-1", title="Compacted")
    issue = issue.model_copy(
        update={
            "description": "original",
            "comments": [
                _summary_comment(rewritten_description="rewritten body"),
            ],
        }
    )
    assert get_virtualized_description(issue) == "rewritten body"
