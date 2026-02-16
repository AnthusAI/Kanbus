"""Single-line issue formatting for list output."""

from __future__ import annotations

import os
import sys
from typing import Callable, Dict, Iterable, Optional

import click

from kanbus.ids import format_issue_key
from kanbus.models import IssueData, ProjectConfiguration

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


def _resolve_status_color(
    status: str, configuration: ProjectConfiguration | None
) -> str:
    if configuration and status in configuration.status_colors:
        return configuration.status_colors[status]
    return STATUS_COLORS.get(status, "white")


def _resolve_priority_color(
    priority: int, configuration: ProjectConfiguration | None
) -> str:
    if configuration:
        definition = configuration.priorities.get(priority)
        if definition and definition.color:
            return definition.color
    return PRIORITY_COLORS.get(priority, "white")


def _resolve_type_color(
    issue_type: str, configuration: ProjectConfiguration | None
) -> str:
    if configuration and issue_type in configuration.type_colors:
        return configuration.type_colors[issue_type]
    return TYPE_COLORS.get(issue_type, "white")


def _normalize_color(color: str | None) -> str | None:
    return color if color in KNOWN_COLORS else None


def _safe_color(colorizer: Callable[[str, str], str], text: str, fg: str | None) -> str:
    normalized = _normalize_color(fg)
    if normalized is None:
        return text
    return colorizer(text, fg=normalized)


def format_issue_line(
    issue: IssueData,
    *,
    porcelain: bool = False,
    colorizer: Callable[[str, str], str] | None = None,
    widths: Dict[str, int] | None = None,
    project_context: bool = False,
    configuration: ProjectConfiguration | None = None,
    use_color: Optional[bool] = None,
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
    :param project_context: Whether identifiers should omit the project key.
    :type project_context: bool
    :param configuration: Optional project configuration for color overrides.
    :type configuration: ProjectConfiguration | None
    :param use_color: Force color on/off; when None, use NO_COLOR and TTY.
    :type use_color: Optional[bool]
    :return: Formatted line.
    :rtype: str
    """
    if use_color is None:
        use_color = (
            os.getenv("NO_COLOR") is None and sys.stdout.isatty()
        )
    use_color = use_color and not porcelain
    color = colorizer or click.style
    if not use_color:

        def no_color(text: str, **_kwargs: object) -> str:
            return text

        color = no_color
    priority_color = _resolve_priority_color(issue.priority, configuration)
    status_color = _resolve_status_color(issue.status, configuration)

    formatted_identifier = format_issue_key(
        issue.identifier, project_context=project_context
    )

    parent_value = issue.parent or "-"
    parent_display = (
        format_issue_key(parent_value, project_context=project_context)
        if parent_value != "-"
        else parent_value
    )

    type_display = issue.issue_type[:1].upper()

    if porcelain:
        parts = [
            type_display,
            formatted_identifier,
            parent_display,
            issue.status,
            f"P{issue.priority}",
            issue.title,
        ]
        return " | ".join(parts)

    widths = widths or compute_widths([issue], project_context=project_context)

    type_color = _resolve_type_color(issue.issue_type, configuration)
    type_part = _safe_color(color, type_display.ljust(widths["type"]), type_color)

    parent_value = issue.parent or "-"
    parent_display = (
        format_issue_key(parent_value, project_context=project_context)
        if parent_value != "-"
        else parent_value
    )
    status_part = _safe_color(color, issue.status.ljust(widths["status"]), status_color)
    priority_plain = f"P{issue.priority}".ljust(widths["priority"])
    priority_part = _safe_color(color, priority_plain, priority_color)

    identifier_part = formatted_identifier.ljust(widths["identifier"])
    parent_plain = parent_display.ljust(widths["parent"])
    if parent_value == "-" and use_color:
        parent_part = _safe_color(color, parent_plain, "bright_black")
    else:
        parent_part = parent_plain
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


def compute_widths(
    issues: Iterable[IssueData], project_context: bool = False
) -> Dict[str, int]:
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
        formatted_identifier = format_issue_key(
            issue.identifier, project_context=project_context
        )
        identifier_w = max(identifier_w, len(formatted_identifier))
        parent_value = issue.parent or "-"
        parent_display = (
            format_issue_key(parent_value, project_context=project_context)
            if parent_value != "-"
            else parent_value
        )
        parent_w = max(parent_w, len(parent_display))

    return {
        "status": status_w,
        "priority": priority_w,
        "type": type_w,
        "identifier": identifier_w,
        "parent": parent_w,
    }
