"""Derive a semantic category for a status that does not declare one.

Older project configurations predate ``semantic_category``. Rather than refuse to
load them, infer a category from the status key and name. An explicit value in
the configuration always wins; this only fills the gap.
"""

from __future__ import annotations

import re

CANONICAL_SEMANTIC_CATEGORIES = ("todo", "in_progress", "in_review", "blocked", "done")

_DONE_WORDS = frozenset(
    {
        "closed",
        "done",
        "complete",
        "completed",
        "resolved",
        "published",
        "shipped",
        "released",
        "archived",
        "cancelled",
        "canceled",
        "rejected",
        "accepted",
        "wontfix",
    }
)
_BLOCKED_WORDS = frozenset({"blocked"})
_REVIEW_WORDS = frozenset({"review"})
_TODO_WORDS = frozenset(
    {
        "open",
        "backlog",
        "todo",
        "new",
        "idea",
        "ideas",
        "proposed",
        "planned",
        "inbox",
        "queued",
        "queue",
        "ready",
        "discovery",
        "triage",
    }
)


def derive_semantic_category(key: str, name: str = "") -> str:
    """Infer a canonical semantic category from a status key and name.

    Words of the key and name are checked in a fixed order: a finished word
    gives ``done``, then ``blocked`` gives ``blocked``, then ``review`` gives
    ``in_review``, then a not-started word gives ``todo``. Every other status is
    treated as work in progress.
    """
    words = {word for word in re.split(r"[^a-z0-9]+", f"{key} {name}".lower()) if word}
    if words & _DONE_WORDS:
        return "done"
    if words & _BLOCKED_WORDS:
        return "blocked"
    if words & _REVIEW_WORDS:
        return "in_review"
    if words & _TODO_WORDS:
        return "todo"
    return "in_progress"
