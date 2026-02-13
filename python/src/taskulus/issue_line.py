"""Single-line issue formatting for list output."""

from __future__ import annotations

from typing import Callable, Dict, Iterable

import click

from taskulus.models import IssueData

STATUS_COLORS = {
    "open": "cyan",
    "in_progress": "blue",
    "blocked": "red",
    "closed": "green",
    "deferred": "yellow",
}

PRIORITY_COLORS = {
    0: "red",
    1: "bright_red",
    2: "yellow",
    3: "blue",
    4: "white",
}

# Temporary type color mapping; will be replaced with config-driven values.
TYPE_COLORS = {
    "epic": "magenta",
    "initiative": "bright_magenta",
    "task": "white",
    "sub-task": "white",
    "bug": "red",
    "story": "cyan",
    "chore": "blue",
}


def format_issue_line(
    issue: IssueData,
    *,
    porcelain: bool = False,
    colorizer: Callable[[str, str], str] | None = None,
    widths: Dict[str, int] | None = None,
) -> str:
    """Render a single-line summary similar to Beads.

    :param issue: Issue to format.
    :type issue: IssueData
    :param porcelain: Disable ANSI color when True.
    :type porcelain: bool
    :param colorizer: Optional function to apply color; defaults to click.style.
    :type colorizer: Callable[[str, str], str] | None
    :param widths: Optional column widths for aligned output.
    :type widths: Dict[str, int] | None
    :return: Formatted line.
    :rtype: str
    """
    color = colorizer or click.style
    priority_color = PRIORITY_COLORS.get(issue.priority, "white")
    status_color = STATUS_COLORS.get(issue.status, "white")

    if porcelain:
        parent_value = issue.parent or "-"
        parts = [
            issue.issue_type[:1].upper(),
            issue.identifier,
            parent_value,
            issue.status,
            f"P{issue.priority}",
            issue.title,
        ]
        return " | ".join(parts)

    widths = widths or compute_widths([issue])

    type_initial = issue.issue_type[:1].upper()
    type_color = TYPE_COLORS.get(issue.issue_type, "white")
    type_part = color(type_initial.ljust(widths["type"]), fg=type_color)

    parent_value = issue.parent or "-"
    status_part = color(issue.status.ljust(widths["status"]), fg=status_color)
    priority_plain = f"P{issue.priority}".ljust(widths["priority"])
    priority_part = color(priority_plain, fg=priority_color)

    identifier_part = issue.identifier.ljust(widths["identifier"])
    parent_part = parent_value.ljust(widths["parent"])
    title = issue.title
    prefix = issue.custom.get("project_path")
    prefix_part = f"{prefix} " if prefix else ""

    return (
        f"{prefix_part}"
        f"{type_part} "
        f"{identifier_part} "
        f"{parent_part} "
        f"{status_part} "
        f"{priority_part} "
        f"{title}"
    )


def compute_widths(issues: Iterable[IssueData]) -> Dict[str, int]:
    """Compute printable column widths for aligned normal-mode output."""

    status_w = 1
    priority_w = 0
    type_w = 0
    identifier_w = 0
    parent_w = 0

    for issue in issues:
        status_w = max(status_w, len(issue.status))
        priority_w = max(priority_w, len(f"P{issue.priority}"))
        type_w = max(type_w, len(issue.issue_type[:1].upper()))
        identifier_w = max(identifier_w, len(issue.identifier))
        parent_w = max(parent_w, len(issue.parent or "-"))

    return {
        "status": status_w,
        "priority": priority_w,
        "type": type_w,
        "identifier": identifier_w,
        "parent": parent_w,
    }
