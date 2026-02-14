"""Issue comment management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kanbus.issue_files import write_issue_to_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueComment, IssueData


class IssueCommentError(RuntimeError):
    """Raised when issue comment creation fails."""


@dataclass(frozen=True)
class IssueCommentResult:
    """Result of adding a comment to an issue."""

    issue: IssueData
    comment: IssueComment


def add_comment(
    root: Path, identifier: str, author: str, text: str
) -> IssueCommentResult:
    """Add a comment to an issue.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :param author: Comment author.
    :type author: str
    :param text: Comment text.
    :type text: str
    :return: Comment result including the updated issue.
    :rtype: IssueCommentResult
    :raises IssueCommentError: If the issue cannot be found or updated.
    """
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueCommentError(str(error)) from error

    timestamp = datetime.now(timezone.utc)
    comment = IssueComment(author=author, text=text, created_at=timestamp)
    comments = [*lookup.issue.comments, comment]
    updated = lookup.issue.model_copy(
        update={"comments": comments, "updated_at": timestamp}
    )
    write_issue_to_file(updated, lookup.issue_path)
    return IssueCommentResult(issue=updated, comment=comment)
