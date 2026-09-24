"""Mark the router statuses in a raw configuration mapping used by tests."""

from __future__ import annotations

from typing import Any

ROUTER_STATUS_CATEGORIES = {
    "open": "todo",
    "in_progress": "in_progress",
    "review": "in_review",
    "blocked": "blocked",
    "closed": "done",
}


def mark_router_statuses(configuration_data: dict[str, Any]) -> None:
    """Give each router lifecycle status its semantic category and router marker.

    :param configuration_data: Raw project configuration mapping.
    :type configuration_data: dict[str, Any]
    """
    for status in configuration_data["statuses"]:
        category = ROUTER_STATUS_CATEGORIES.get(status["key"])
        if category is not None:
            status["semantic_category"] = category
            status["router"] = True
