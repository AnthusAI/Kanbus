"""Issue display formatting helpers."""

from __future__ import annotations

from taskulus.models import IssueData

STATUS_GLYPHS = {
    "open": "◌",
    "in_progress": "◐",
    "blocked": "◑",
    "closed": "●",
    "deferred": "◍",
}

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


def format_issue_for_display(issue: IssueData) -> str:
    """Format an issue for human-readable display.

    :param issue: Issue data to display.
    :type issue: IssueData
    :return: Human-readable issue display.
    :rtype: str
    """
    lines = [
        f"ID: {issue.identifier}",
        f"Title: {issue.title}",
        f"Type: {issue.issue_type}",
        f"Status: {issue.status}",
        f"Priority: {issue.priority}",
        f"Assignee: {issue.assignee or 'None'}",
        f"Parent: {issue.parent or 'None'}",
        f"Labels: {', '.join(issue.labels) if issue.labels else 'None'}",
    ]
    if issue.description:
        lines.append("Description:")
        lines.append(issue.description)
    return "\n".join(lines)
