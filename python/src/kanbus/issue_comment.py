"""Issue comment management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from kanbus.issue_files import write_issue_to_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueComment, IssueData
from kanbus.event_history import (
    comment_payload,
    comment_updated_payload,
    create_event,
    events_dir_for_issue_path,
    now_timestamp,
    write_events_batch,
)
from kanbus.users import get_current_user


class IssueCommentError(RuntimeError):
    """Raised when issue comment creation fails."""


@dataclass(frozen=True)
class IssueCommentResult:
    """Result of adding a comment to an issue."""

    issue: IssueData
    comment: IssueComment


def _generate_comment_id() -> str:
    return str(uuid4())


def _ensure_comment_ids(issue: IssueData) -> tuple[IssueData, bool]:
    changed = False
    comments = []
    for comment in issue.comments:
        if not comment.id:
            changed = True
            comments.append(
                IssueComment(
                    id=_generate_comment_id(),
                    author=comment.author,
                    text=comment.text,
                    created_at=comment.created_at,
                )
            )
        else:
            comments.append(comment)
    if not changed:
        return issue, False
    updated = issue.model_copy(update={"comments": comments})
    return updated, True


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip().lower()
    if not normalized:
        raise IssueCommentError("comment id is required")
    return normalized


def _find_comment_index(issue: IssueData, prefix: str) -> int:
    normalized = _normalize_prefix(prefix)
    matches: list[int] = []
    for index, comment in enumerate(issue.comments):
        if comment.id and comment.id.lower().startswith(normalized):
            matches.append(index)
    if not matches:
        raise IssueCommentError("comment not found")
    if len(matches) > 1:
        ids = ", ".join(
            (issue.comments[index].id or "")[:6]
            for index in matches
            if issue.comments[index].id
        )
        raise IssueCommentError(f"comment id prefix is ambiguous; matches: {ids}")
    return matches[0]


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
    base_issue, _ = _ensure_comment_ids(lookup.issue)
    comment = IssueComment(
        id=_generate_comment_id(),
        author=author,
        text=text,
        created_at=timestamp,
    )
    comments = [*base_issue.comments, comment]
    updated = lookup.issue.model_copy(
        update={"comments": comments, "updated_at": timestamp}
    )
    write_issue_to_file(updated, lookup.issue_path)
    comment_id = comment.id
    if not comment_id:
        raise IssueCommentError("comment id is required")
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=updated.identifier,
        event_type="comment_added",
        actor_id=actor_id,
        payload=comment_payload(comment_id, comment.author),
        occurred_at=occurred_at,
    )
    events_dir = events_dir_for_issue_path(lookup.project_dir, lookup.issue_path)
    try:
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(lookup.issue, lookup.issue_path)
        raise IssueCommentError(str(error)) from error
    return IssueCommentResult(issue=updated, comment=comment)


def ensure_issue_comment_ids(root: Path, identifier: str) -> IssueData:
    """Ensure comment ids are set for an issue and persist any changes."""
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueCommentError(str(error)) from error
    updated, changed = _ensure_comment_ids(lookup.issue)
    if changed:
        write_issue_to_file(updated, lookup.issue_path)
    return updated


def update_comment(
    root: Path, identifier: str, comment_id: str, text: str
) -> IssueData:
    """Update a comment by id prefix."""
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueCommentError(str(error)) from error
    issue, _ = _ensure_comment_ids(lookup.issue)
    index = _find_comment_index(issue, comment_id)
    comments = list(issue.comments)
    existing_comment = comments[index]
    updated_comment = comments[index].model_copy(update={"text": text})
    comments[index] = updated_comment
    updated = issue.model_copy(
        update={"comments": comments, "updated_at": datetime.now(timezone.utc)}
    )
    write_issue_to_file(updated, lookup.issue_path)
    if not existing_comment.id:
        raise IssueCommentError("comment id is required")
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=updated.identifier,
        event_type="comment_updated",
        actor_id=actor_id,
        payload=comment_updated_payload(existing_comment.id, existing_comment.author),
        occurred_at=occurred_at,
    )
    events_dir = events_dir_for_issue_path(lookup.project_dir, lookup.issue_path)
    try:
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(lookup.issue, lookup.issue_path)
        raise IssueCommentError(str(error)) from error
    return updated


def delete_comment(root: Path, identifier: str, comment_id: str) -> IssueData:
    """Delete a comment by id prefix."""
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueCommentError(str(error)) from error
    issue, _ = _ensure_comment_ids(lookup.issue)
    index = _find_comment_index(issue, comment_id)
    comments = list(issue.comments)
    removed_comment = comments.pop(index)
    updated = issue.model_copy(
        update={"comments": comments, "updated_at": datetime.now(timezone.utc)}
    )
    write_issue_to_file(updated, lookup.issue_path)
    if not removed_comment.id:
        raise IssueCommentError("comment id is required")
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=updated.identifier,
        event_type="comment_deleted",
        actor_id=actor_id,
        payload=comment_payload(removed_comment.id, removed_comment.author),
        occurred_at=occurred_at,
    )
    events_dir = events_dir_for_issue_path(lookup.project_dir, lookup.issue_path)
    try:
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(lookup.issue, lookup.issue_path)
        raise IssueCommentError(str(error)) from error
    return updated
