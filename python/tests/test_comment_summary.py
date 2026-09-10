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


def _summary(**data: object) -> IssueComment:
    payload = {
        "id": "s1",
        "author": "system:summary",
        "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
        "comment_type": "summary",
        "data": data,
        "text": "legacy activity",
    }
    return IssueComment.model_validate(payload)


def test_summary_field_helpers_cover_empty_and_virtualized_paths() -> None:
    empty_rewritten = _summary(rewritten_description="", activity_summary="activity")
    assert get_summary_rewritten_description(empty_rewritten) is None

    missing_activity = _summary(rewritten_description="goal")
    missing_activity.data["activity_summary"] = None
    assert get_summary_activity_summary(missing_activity) == "legacy activity"
    assert get_comment_display_text(missing_activity) == "legacy activity"

    issue = build_issue("kanbus-1")
    issue.description = "original"
    issue.comments = [
        _summary(rewritten_description="compacted goal", activity_summary="activity")
    ]
    assert get_virtualized_description(issue) == "compacted goal"
    issue.comments = []
    issue.description = ""
    assert get_virtualized_description(issue) == ""
