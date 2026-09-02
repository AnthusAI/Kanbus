"""Helpers for structured summary comment fields and display text."""

from __future__ import annotations

from kanbus.models import IssueComment

SUMMARY_REWRITTEN_DESCRIPTION_KEY = "rewritten_description"
SUMMARY_ACTIVITY_SUMMARY_KEY = "activity_summary"


def get_latest_summary_comment(issue: object) -> IssueComment | None:
    """Return the most recent summary comment on an issue.

    :param issue: Issue data object.
    :type issue: object
    :return: Latest summary comment when present.
    :rtype: IssueComment | None
    """
    comments = getattr(issue, "comments", None) or []
    for comment in reversed(comments):
        if getattr(comment, "comment_type", "default") == "summary":
            return comment
    return None


def get_summary_rewritten_description(comment: IssueComment) -> str | None:
    """Return the rewritten description stored on a summary comment.

    :param comment: Summary comment to inspect.
    :type comment: IssueComment
    :return: Rewritten description text when present.
    :rtype: str | None
    """
    value = comment.data.get(SUMMARY_REWRITTEN_DESCRIPTION_KEY)
    if isinstance(value, str) and value:
        return value
    return None


def get_summary_activity_summary(comment: IssueComment) -> str:
    """Return the activity summary stored on a summary comment.

    :param comment: Summary comment to inspect.
    :type comment: IssueComment
    :return: Activity summary text.
    :rtype: str
    """
    value = comment.data.get(SUMMARY_ACTIVITY_SUMMARY_KEY)
    if isinstance(value, str) and value:
        return value
    return comment.text or ""


def get_comment_display_text(comment: IssueComment) -> str:
    """Return the text to display for a comment.

    :param comment: Comment to render.
    :type comment: IssueComment
    :return: Display text for CLI and UI comment rendering.
    :rtype: str
    """
    if comment.comment_type == "summary":
        return get_summary_activity_summary(comment)
    return comment.text or ""


def get_virtualized_description(issue: object) -> str:
    """Return the effective description for display or LLM context.

    :param issue: Issue data object.
    :type issue: object
    :return: Rewritten description when compacted, otherwise the stored description.
    :rtype: str
    """
    summary_comment = get_latest_summary_comment(issue)
    if summary_comment is not None:
        rewritten_description = get_summary_rewritten_description(summary_comment)
        if rewritten_description is not None:
            return rewritten_description
    return getattr(issue, "description", "")
