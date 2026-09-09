from __future__ import annotations

from types import SimpleNamespace

from kanbus.comment_summary import (
    get_comment_display_text,
    get_latest_summary_comment,
    get_summary_activity_summary,
    get_summary_rewritten_description,
    get_virtualized_description,
)
from kanbus.models import IssueComment


def _summary_comment(**overrides: object) -> IssueComment:
    payload = {
        "id": "summary-id",
        "author": "system:summary",
        "text": "Activity from text",
        "created_at": "2026-08-27T00:00:00Z",
        "comment_type": "summary",
        "data": {
            "rewritten_description": "Compact description",
            "activity_summary": "Activity from data",
        },
    }
    payload.update(overrides)
    return IssueComment.model_validate(payload)


def test_get_latest_summary_comment_returns_most_recent_summary() -> None:
    issue = SimpleNamespace(
        comments=[
            IssueComment.model_validate(
                {
                    "id": "default-id",
                    "author": "dev",
                    "text": "regular",
                    "created_at": "2026-08-27T00:00:00Z",
                }
            ),
            _summary_comment(id="summary-id"),
        ]
    )
    latest = get_latest_summary_comment(issue)
    assert latest is not None
    assert latest.id == "summary-id"


def test_get_summary_rewritten_description_ignores_empty_values() -> None:
    empty_comment = _summary_comment(data={"rewritten_description": ""})
    assert get_summary_rewritten_description(empty_comment) is None
    valid_comment = _summary_comment(
        data={"rewritten_description": "Compact description"}
    )
    assert get_summary_rewritten_description(valid_comment) == "Compact description"


def test_get_summary_activity_summary_falls_back_to_comment_text() -> None:
    comment = _summary_comment(text="Legacy activity", data={})
    assert get_summary_activity_summary(comment) == "Legacy activity"


def test_get_comment_display_text_uses_summary_activity_for_summary_comments() -> None:
    comment = _summary_comment()
    assert get_comment_display_text(comment) == "Activity from data"


def test_get_virtualized_description_prefers_rewritten_description() -> None:
    issue = SimpleNamespace(
        description="Original description",
        comments=[_summary_comment()],
    )
    assert get_virtualized_description(issue) == "Compact description"
