"""A status without a semantic category gets a sensible one instead of failing."""

from __future__ import annotations

import pytest

from kanbus.models import StatusDefinition
from kanbus.status_semantic_defaults import derive_semantic_category


@pytest.mark.parametrize(
    ("key", "name", "expected"),
    [
        ("open", "Discovery", "todo"),
        ("backlog", "Backlog", "todo"),
        ("idea", "Idea", "todo"),
        ("Discovery", "Discovery", "todo"),
        ("proposed", "Proposed", "todo"),
        ("closed", "Done", "done"),
        ("done", "Done", "done"),
        ("published", "Published", "done"),
        ("accepted", "Accepted", "done"),
        ("rejected", "Rejected", "done"),
        ("in_progress", "In Progress", "in_progress"),
        ("blocked", "Blocked", "in_progress"),
        ("assignment", "Assignment", "in_progress"),
        ("editor_select", "Editor select", "in_progress"),
        ("awaiting-review", "Awaiting review", "in_progress"),
        ("gold-authored", "Gold authored", "in_progress"),
    ],
)
def test_category_is_derived_from_key_and_name(key, name, expected):
    assert derive_semantic_category(key, name) == expected


def test_done_wins_over_todo_when_both_read_true():
    assert derive_semantic_category("ready_and_shipped") == "done"


def test_missing_semantic_category_is_filled_in_on_load():
    status = StatusDefinition(key="published", name="Published", category="Publishing")
    assert status.semantic_category == "done"


def test_blank_semantic_category_is_treated_as_missing():
    status = StatusDefinition(
        key="idea", name="Idea", category="Editorial", semantic_category="  "
    )
    assert status.semantic_category == "todo"


def test_an_explicit_semantic_category_is_never_overridden():
    status = StatusDefinition(
        key="published",
        name="Published",
        category="Publishing",
        semantic_category="todo",
    )
    assert status.semantic_category == "todo"
