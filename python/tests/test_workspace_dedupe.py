from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kanbus.issue_listing import _deduplicate_issues_by_identity
from test_helpers import build_issue

LATER = datetime(2026, 3, 7, tzinfo=timezone.utc)
EARLIER = datetime(2026, 3, 6, tzinfo=timezone.utc)


def test_deduplicate_keeps_most_recent_copy() -> None:
    stale = build_issue("kanbus-dup", title="Stale copy")
    fresh = build_issue("kanbus-dup", title="Fresh copy")
    fresh = fresh.model_copy(update={"updated_at": LATER})
    distinct = build_issue("kanbus-other", title="Other issue")

    deduplicated = _deduplicate_issues_by_identity(
        [
            (stale, Path("repo/project")),
            (fresh, Path("repo-wt/project")),
            (distinct, Path("other/project")),
        ]
    )

    assert [issue.identifier for issue, _ in deduplicated] == [
        "kanbus-dup",
        "kanbus-other",
    ]
    assert deduplicated[0][0].title == "Fresh copy"
    assert deduplicated[0][1] == Path("repo-wt/project")
    assert deduplicated[0][0].updated_at == LATER


def test_deduplicate_winner_keeps_first_occurrence_position() -> None:
    first = build_issue("kanbus-dup", title="First")
    second = build_issue("kanbus-dup", title="Second")
    second = second.model_copy(update={"updated_at": LATER})
    tail = build_issue("kanbus-tail", title="Tail")

    deduplicated = _deduplicate_issues_by_identity(
        [(first, Path("a")), (second, Path("b")), (tail, Path("c"))]
    )

    assert [issue.title for issue, _ in deduplicated] == ["Second", "Tail"]
    assert deduplicated[0][1] == Path("b")


def test_deduplicate_tie_breaks_on_canonical_record() -> None:
    alpha = build_issue("kanbus-tie", title="Tie copy alpha")
    zeta = build_issue("kanbus-tie", title="Tie copy zeta")

    deduplicated = _deduplicate_issues_by_identity(
        [(alpha, Path("a")), (zeta, Path("b"))]
    )
    assert deduplicated[0][0].title == "Tie copy zeta"

    reversed_deduplicated = _deduplicate_issues_by_identity(
        [(zeta, Path("b")), (alpha, Path("a"))]
    )
    assert reversed_deduplicated[0][0].title == "Tie copy zeta"


def test_deduplicate_byte_identical_copies_collapse() -> None:
    copy_one = build_issue("kanbus-same", title="Same")
    copy_two = build_issue("kanbus-same", title="Same")

    deduplicated = _deduplicate_issues_by_identity(
        [(copy_one, Path("a")), (copy_two, Path("b"))]
    )

    assert len(deduplicated) == 1
    assert deduplicated[0][1] == Path("a")


def test_deduplicate_keeps_distinct_issues() -> None:
    one = build_issue("kanbus-one", title="One")
    two = build_issue("kanbus-two", title="Two")
    two = two.model_copy(update={"updated_at": LATER})

    deduplicated = _deduplicate_issues_by_identity([(one, Path("a")), (two, Path("b"))])

    assert [issue.identifier for issue, _ in deduplicated] == [
        "kanbus-one",
        "kanbus-two",
    ]
