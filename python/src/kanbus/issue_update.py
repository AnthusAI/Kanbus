"""Issue update workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from kanbus.config_loader import load_project_configuration
from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.issue_lookup import (
    IssueLookupError,
    load_issue_from_project,
    resolve_issue_identifier,
)
from kanbus.hierarchy import InvalidHierarchyError, validate_parent_child_relationship
from kanbus.models import IssueData
from kanbus.project import get_configuration_path
from kanbus.workflows import (
    InvalidTransitionError,
    apply_transition_side_effects,
    validate_status_transition,
    validate_status_value,
)
from kanbus.event_history import (
    build_update_events,
    events_dir_for_issue_path,
    now_timestamp,
    write_events_batch,
)
from kanbus.users import get_current_user


class IssueUpdateError(RuntimeError):
    """Raised when issue updates fail."""


def update_issue(
    root: Path,
    identifier: str,
    title: Optional[str],
    description: Optional[str],
    status: Optional[str],
    assignee: Optional[str],
    claim: bool,
    validate: bool = True,
    priority: Optional[int] = None,
    add_labels: Optional[list[str]] = None,
    remove_labels: Optional[list[str]] = None,
    set_labels: Optional[list[str]] = None,
    parent: Optional[str] = None,
) -> IssueData:
    """Update an issue and persist it to disk.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :param title: Updated title if provided.
    :type title: Optional[str]
    :param description: Updated description if provided.
    :type description: Optional[str]
    :param status: Updated status if provided.
    :type status: Optional[str]
    :param assignee: Updated assignee if provided.
    :type assignee: Optional[str]
    :param claim: Whether to claim the issue.
    :type claim: bool
    :param priority: Updated priority if provided.
    :type priority: Optional[int]
    :param add_labels: Labels to add.
    :type add_labels: Optional[list[str]]
    :param remove_labels: Labels to remove.
    :type remove_labels: Optional[list[str]]
    :param set_labels: Labels to set (replacing all existing labels).
    :type set_labels: Optional[list[str]]
    :param parent: Updated parent identifier.
    :type parent: Optional[str]
    :return: Updated issue data.
    :rtype: IssueData
    :raises IssueUpdateError: If the update fails.
    """
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise IssueUpdateError(str(error)) from error

    project_dir = lookup.project_dir
    configuration = load_project_configuration(get_configuration_path(project_dir))
    before_issue = lookup.issue
    updated_issue = lookup.issue
    current_time = datetime.now(timezone.utc)

    resolved_status = status
    if claim:
        resolved_status = "in_progress"

    if title is not None:
        normalized_title = title.strip()
        if normalized_title.casefold() == updated_issue.title.strip().casefold():
            title = None
        else:
            duplicate_identifier = _find_duplicate_title(
                project_dir / "issues",
                normalized_title,
                updated_issue.identifier,
            )
            if duplicate_identifier is not None:
                message = (
                    f'duplicate title: "{normalized_title}" '
                    f"already exists as {duplicate_identifier}"
                )
                raise IssueUpdateError(message)
            title = normalized_title

    if description is not None:
        description = description.strip()
        if description == updated_issue.description:
            description = None

    if assignee is not None and assignee == updated_issue.assignee:
        assignee = None

    if resolved_status is not None and resolved_status == updated_issue.status:
        resolved_status = None

    if priority is not None and priority == updated_issue.priority:
        priority = None

    # Handle label operations
    labels = None
    if set_labels is not None:
        labels = set_labels
    elif add_labels is not None or remove_labels is not None:
        current_labels = set(updated_issue.labels)
        if add_labels:
            current_labels.update(add_labels)
        if remove_labels:
            current_labels.difference_update(remove_labels)
        labels = list(current_labels)

    updated_parent: Optional[str] = None
    if parent is not None:
        issues_dir = project_dir / "issues"
        try:
            resolved_parent = resolve_issue_identifier(
                issues_dir, configuration.project_key, parent
            )
        except IssueLookupError as error:
            raise IssueUpdateError(str(error)) from error
        if updated_issue.parent != resolved_parent:
            if validate:
                parent_issue = read_issue_from_file(
                    issues_dir / f"{resolved_parent}.json"
                )
                try:
                    validate_parent_child_relationship(
                        configuration,
                        parent_issue.issue_type,
                        updated_issue.issue_type,
                    )
                except InvalidHierarchyError as error:
                    raise IssueUpdateError(str(error)) from error
            updated_parent = resolved_parent

    if (
        resolved_status is None
        and title is None
        and description is None
        and assignee is None
        and priority is None
        and labels is None
        and updated_parent is None
    ):
        raise IssueUpdateError("no updates requested")

    if resolved_status is not None:
        if validate:
            try:
                validate_status_value(
                    configuration, updated_issue.issue_type, resolved_status
                )
                validate_status_transition(
                    configuration,
                    updated_issue.issue_type,
                    updated_issue.status,
                    resolved_status,
                )
            except InvalidTransitionError as error:
                raise IssueUpdateError(str(error)) from error
        updated_issue = apply_transition_side_effects(
            updated_issue,
            resolved_status,
            current_time,
        )
        updated_issue = updated_issue.model_copy(update={"status": resolved_status})

    update_fields = {"updated_at": current_time}
    if title is not None:
        update_fields["title"] = title
    if description is not None:
        update_fields["description"] = description
    if assignee is not None:
        update_fields["assignee"] = assignee
    if priority is not None:
        update_fields["priority"] = priority
    if labels is not None:
        update_fields["labels"] = labels
    if updated_parent is not None:
        update_fields["parent"] = updated_parent

    updated_issue = updated_issue.model_copy(update=update_fields)
    
    policies_dir = project_dir / "policies"
    if policies_dir.is_dir():
        from kanbus.policy_loader import load_policies
        from kanbus.policy_evaluator import evaluate_policies
        from kanbus.policy_context import PolicyContext, PolicyOperation, StatusTransition
        from kanbus.issue_listing import load_issues_from_directory
        
        policy_documents = load_policies(policies_dir)
        if policy_documents:
            issues_dir = project_dir / "issues"
            all_issues = load_issues_from_directory(issues_dir)
            context = PolicyContext(
                current_issue=before_issue,
                proposed_issue=updated_issue,
                transition=StatusTransition(
                    from_status=before_issue.status,
                    to_status=resolved_status,
                ) if resolved_status else None,
                operation=PolicyOperation.UPDATE,
                project_configuration=configuration,
                all_issues=all_issues,
            )
            evaluate_policies(context, policy_documents)
    
    write_issue_to_file(updated_issue, lookup.issue_path)
    occurred_at = now_timestamp()
    actor_id = get_current_user()
    events = build_update_events(before_issue, updated_issue, actor_id, occurred_at)
    events_dir = events_dir_for_issue_path(lookup.project_dir, lookup.issue_path)
    try:
        write_events_batch(events_dir, events)
    except Exception as error:  # noqa: BLE001
        write_issue_to_file(before_issue, lookup.issue_path)
        raise IssueUpdateError(str(error)) from error
    return updated_issue


def _find_duplicate_title(
    issues_dir: Path, title: str, current_identifier: str
) -> Optional[str]:
    normalized_title = title.strip().casefold()
    for issue_path in issues_dir.glob("*.json"):
        if issue_path.stem == current_identifier:
            continue
        try:
            issue = read_issue_from_file(issue_path)
        except (ValueError, ValidationError):
            continue
        if issue.title.strip().casefold() == normalized_title:
            return issue.identifier
    return None
