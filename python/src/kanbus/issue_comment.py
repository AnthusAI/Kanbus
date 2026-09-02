"""Issue comment management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from kanbus.event_history import (
    comment_payload,
    comment_updated_payload,
    create_event,
    now_timestamp,
)
from kanbus.gossip import publish_issue_mutation
from kanbus.issue_files import write_issue_to_file
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.issue_mutation import PersistIssueMutationRequest, persist_issue_mutation
from kanbus.models import AgentMetadata, IssueComment, IssueData
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
                    comment_type=comment.comment_type,
                    data=comment.data,
                    agent=comment.agent,
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


def _persist_comment_mutation(
    root: Path,
    lookup,
    updated_issue: IssueData,
    before_issue: IssueData,
    event_type: str,
    payload: dict,
) -> IssueData:
    actor_id = get_current_user()
    event = create_event(
        issue_id=updated_issue.identifier,
        event_type=event_type,
        actor_id=actor_id,
        payload=payload,
        occurred_at=now_timestamp(),
    )
    try:
        result = persist_issue_mutation(
            PersistIssueMutationRequest(
                project_dir=lookup.project_dir,
                issue_path=lookup.issue_path,
                issue=updated_issue,
                actor_id=actor_id,
                events=[event],
                before_issue=before_issue,
                root=root,
            )
        )
    except Exception as error:  # noqa: BLE001
        raise IssueCommentError(str(error)) from error
    if lookup.issue_path.parent == lookup.project_dir / "issues":
        publish_issue_mutation(
            root,
            lookup.project_dir,
            result.issue,
            event.event_id,
            "issue.mutated",
        )
    return result.issue


def add_comment(
    root: Path,
    identifier: str,
    author: str,
    text: str,
    agent: Optional[AgentMetadata] = None,
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
    :param agent: Optional agent provenance metadata for this comment.
    :type agent: Optional[AgentMetadata]
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
        agent=agent,
    )
    comments = [*base_issue.comments, comment]
    updated = base_issue.model_copy(update={"comments": comments})
    comment_id = comment.id
    if not comment_id:
        raise IssueCommentError("comment id is required")
    persisted = _persist_comment_mutation(
        root,
        lookup,
        updated,
        lookup.issue,
        "comment_added",
        comment_payload(comment_id, comment.author, comment.agent),
    )
    return IssueCommentResult(issue=persisted, comment=comment)


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
    updated = issue.model_copy(update={"comments": comments})
    if not existing_comment.id:
        raise IssueCommentError("comment id is required")
    return _persist_comment_mutation(
        root,
        lookup,
        updated,
        lookup.issue,
        "comment_updated",
        comment_updated_payload(existing_comment.id, existing_comment.author),
    )


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
    updated = issue.model_copy(update={"comments": comments})
    if not removed_comment.id:
        raise IssueCommentError("comment id is required")
    return _persist_comment_mutation(
        root,
        lookup,
        updated,
        lookup.issue,
        "comment_deleted",
        comment_payload(
            removed_comment.id, removed_comment.author, removed_comment.agent
        ),
    )
