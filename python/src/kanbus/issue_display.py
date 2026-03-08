"""Issue display formatting helpers."""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

import click

from kanbus.ids import format_issue_key
from kanbus.models import IssueData, ProjectConfiguration

STATUS_GLYPHS = {
    "backlog": "○",
    "open": "◌",
    "in_progress": "◐",
    "blocked": "◑",
    "closed": "●",
    "deferred": "◍",
}

DEFAULT_STATUS_COLORS: Dict[str, str] = {
    "backlog": "grey",
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


def _render_description_and_comments(
    issue: IssueData, all_issues: List[IssueData]
) -> tuple[str, List[str]]:
    """Render description and comment texts through Jinja2 templates.

    :param issue: Issue to render.
    :type issue: IssueData
    :param all_issues: All issues for query/count/issue context.
    :type all_issues: List[IssueData]
    :return: (rendered_description, [rendered_comment_text, ...]).
    :rtype: tuple[str, List[str]]
    """
    from kanbus.wiki import WikiError, render_template_string

    try:
        description = issue.description
        if description:
            description = render_template_string(description, all_issues)
        else:
            description = ""
        comments_text: List[str] = []
        for comment in issue.comments:
            text = render_template_string(comment.text, all_issues)
            comments_text.append(text)
        return description, comments_text
    except WikiError:
        return issue.description or "", [c.text for c in issue.comments]


def format_issue_for_display(
    issue: IssueData,
    configuration: Optional[ProjectConfiguration] = None,
    use_color: Optional[bool] = None,
    project_context: bool = False,
    all_issues: Optional[List[IssueData]] = None,
) -> str:
    """Format an issue for human-readable display.

    :param issue: Issue data to display.
    :type issue: IssueData
    :param configuration: Project configuration for status/priority colors.
    :type configuration: Optional[ProjectConfiguration]
    :param use_color: Whether to apply ANSI colors (defaults to TTY detection).
    :type use_color: Optional[bool]
    :param project_context: Whether the identifier should omit the project key.
    :type project_context: bool
    :param all_issues: All issues for Jinja2 in description/comments.
    :type all_issues: Optional[List[IssueData]]
    :return: Human-readable issue display.
    :rtype: str
    """
    color_output = _should_use_color() if use_color is None else use_color

    # Build status_colors from statuses list
    status_colors = DEFAULT_STATUS_COLORS.copy()
    if configuration:
        category_colors = {
            category.name: category.color for category in configuration.categories
        }
        for status_def in configuration.statuses:
            if status_def.color:
                status_colors[status_def.key] = status_def.color
            elif status_def.category and status_def.category in category_colors:
                color = category_colors[status_def.category]
                if color:
                    status_colors[status_def.key] = color
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

    description = issue.description
    comments_texts: List[str] = []
    if all_issues:
        description, comments_texts = _render_description_and_comments(
            issue, all_issues
        )
    else:
        comments_texts = [c.text for c in issue.comments]

    if description:
        lines.append(f"{_dim('Description:', color_output)}")
        lines.append(_paint(description, None, color_output))

    if issue.dependencies:
        lines.append(f"{_dim('Dependencies:', color_output)}")
        for dependency in issue.dependencies:
            lines.append(f"  {dependency.dependency_type}: {dependency.target}")

    if issue.comments:
        lines.append(f"{_dim('Comments:', color_output)}")
        for idx, comment in enumerate(issue.comments):
            author = comment.author or "unknown"
            prefix = (comment.id or "")[:6]
            text = comments_texts[idx] if idx < len(comments_texts) else comment.text
            if prefix:
                lines.append(f"  [{prefix}] {_dim(f'{author}:', color_output)} {text}")
            else:
                lines.append(f"  {_dim(f'{author}:', color_output)} {text}")

    return "\n".join(lines)
