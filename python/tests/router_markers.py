"""Helpers that mark router statuses in plain configuration dictionaries."""

from __future__ import annotations

ROUTER_MARKED_STATUS_CATEGORIES = {
    "open": "todo",
    "in_progress": "in_progress",
    "review": "in_review",
    "blocked": "blocked",
    "closed": "done",
}


def mark_router_statuses(data: dict) -> None:
    """Mark the conventional intake, working, review, blocked and done statuses.

    :param data: Mutable project configuration dictionary with a ``statuses`` list.
    :type data: dict
    """
    for status in data["statuses"]:
        category = ROUTER_MARKED_STATUS_CATEGORIES.get(status["key"])
        if category is not None:
            status["semantic_category"] = category
            status["router"] = True
