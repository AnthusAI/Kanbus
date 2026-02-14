"""Issue display formatting helpers."""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional

import click

from kanbus.ids import format_issue_key
from kanbus.models import IssueData, ProjectConfiguration

STATUS_GLYPHS = {
    "open": "◌",
    "in_progress": "◐",
    "blocked": "◑",
    "closed": "●",
    "deferred": "◍",
}

DEFAULT_STATUS_COLORS: Dict[str, str] = {
    "open": "cyan",
    "in_progress": "blue",
    "blocked": "red",
    "closed": "green",
    "deferred": "yellow",
}

DEFAULT_PRIORITY_COLORS: Dict[int, str] = {
    0: "red",
    1: "bright_red",
    2: "yellow",
    3: "blue",
    4: "white",
}

DEFAULT_TYPE_COLORS: Dict[str, str] = {
    "initiative": "bright_blue",
    "epic": "magenta",
    "task": "cyan",
    "sub-task": "bright_cyan",
    "bug": "red",
    "story": "yellow",
    "chore": "green",
    "event": "bright_blue",
}

KNOWN_COLORS = {
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
}


def _should_use_color() -> bool:
    context = click.get_current_context(silent=True)
    if context is not None and context.color is not None:
        return context.color
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _dim(text: str, use_color: bool) -> str:
    if not use_color:
        return text
    return click.style(text, fg="bright_black")


def _normalize_color(color: Optional[str]) -> Optional[str]:
    return color if color in KNOWN_COLORS else None


def _paint(value: str, color: Optional[str], use_color: bool) -> str:
    if not use_color:
        return value
    normalized = _normalize_color(color)
    if normalized is None:
        return value
    return click.style(value, fg=normalized)


def format_issue_for_display(
    issue: IssueData,
    configuration: Optional[ProjectConfiguration] = None,
    use_color: Optional[bool] = None,
    project_context: bool = False,
) -> str:
    """Format an issue for human-readable display.

    :param issue: Issue data to display.
    :type issue: IssueData
    :param use_color: Whether to apply ANSI colors (defaults to TTY detection).
    :type use_color: Optional[bool]
    :param project_context: Whether the identifier should omit the project key.
    :type project_context: bool
    :return: Human-readable issue display.
    :rtype: str
    """
    color_output = _should_use_color() if use_color is None else use_color

    status_colors = (
        {**DEFAULT_STATUS_COLORS, **configuration.status_colors}
        if configuration
        else DEFAULT_STATUS_COLORS
    )
    priority_colors: Dict[int, str] = DEFAULT_PRIORITY_COLORS
    if configuration:
        priority_colors = priority_colors.copy()
        for value, definition in configuration.priorities.items():
            if definition.color:
                priority_colors[value] = definition.color
    type_colors = (
        {**DEFAULT_TYPE_COLORS, **configuration.type_colors}
        if configuration
        else DEFAULT_TYPE_COLORS
    )

    labels_text = ", ".join(issue.labels) if issue.labels else "-"

    formatted_identifier = format_issue_key(issue.identifier, project_context)

    rows = [
        ("ID:", formatted_identifier, None, False),
        ("Title:", issue.title, None, False),
        ("Type:", issue.issue_type, type_colors.get(issue.issue_type), False),
        ("Status:", issue.status, status_colors.get(issue.status), False),
        ("Priority:", str(issue.priority), priority_colors.get(issue.priority), False),
        ("Assignee:", issue.assignee or "-", None, issue.assignee is None),
        ("Parent:", issue.parent or "-", None, issue.parent is None),
        ("Labels:", labels_text, None, not bool(issue.labels)),
    ]

    lines = []
    for label, value, color, muted in rows:
        painted_value = _paint(
            value, color if not muted else "bright_black", color_output
        )
        lines.append(f"{_dim(label, color_output)} {painted_value}")

    if issue.description:
        lines.append(f"{_dim('Description:', color_output)}")
        lines.append(_paint(issue.description, None, color_output))
    return "\n".join(lines)
