"""Issue creation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from pydantic import ValidationError

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.hierarchy import InvalidHierarchyError, validate_parent_child_relationship
from kanbus.ids import IssueIdentifierRequest, generate_issue_identifier
from kanbus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.issue_lookup import IssueLookupError, resolve_issue_identifier
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.event_history import (
    create_event,
    events_dir_for_local,
    events_dir_for_project,
    issue_created_payload,
    now_timestamp,
    write_events_batch,
)
from kanbus.project import (
    ProjectMarkerError,
    ensure_project_local_directory,
    find_project_local_directory,
    get_configuration_path,
    load_project_directory,
)
from kanbus.workflows import InvalidTransitionError, validate_status_value
from kanbus.users import get_current_user


class IssueCreationError(RuntimeError):
    """Raised when issue creation fails."""


@dataclass(frozen=True)
class IssueCreationResult:
    """Result of issue creation."""

    issue: IssueData
    configuration: ProjectConfiguration


def create_issue(
    root: Path,
    title: str,
    issue_type: Optional[str],
    priority: Optional[int],
    assignee: Optional[str],
    parent: Optional[str],
    labels: Iterable[str],
    description: Optional[str],
    local: bool = False,
    validate: bool = True,
) -> IssueCreationResult:
    """Create a new issue and write it to disk.

    :param root: Repository root path.
    :type root: Path
    :param title: Issue title.
    :type title: str
    :param issue_type: Issue type override.
    :type issue_type: Optional[str]
    :param priority: Issue priority override.
    :type priority: Optional[int]
    :param assignee: Assignee identifier.
    :type assignee: Optional[str]
    :param parent: Parent issue identifier.
    :type parent: Optional[str]
    :param labels: Issue labels.
    :type labels: Iterable[str]
    :param description: Issue description.
    :type description: Optional[str]
    :param local: Whether to create the issue in project-local.
    :type local: bool
    :return: Created issue data and configuration.
    :rtype: IssueCreationResult
    :raises IssueCreationError: If validation or file operations fail.
    """
    try:
        project_dir = load_project_directory(root)
    except (ProjectMarkerError, ConfigurationError) as error:
        raise IssueCreationError(str(error)) from error

    issues_dir = project_dir / "issues"
    local_dir = find_project_local_directory(project_dir)
    if local:
        local_dir = ensure_project_local_directory(project_dir)
        issues_dir = local_dir / "issues"
    try:
        configuration = load_project_configuration(get_configuration_path(project_dir))
    except (ProjectMarkerError, ConfigurationError) as error:
        raise IssueCreationError(str(error)) from error

    resolved_type = issue_type or "task"
    resolved_priority = (
        priority if priority is not None else configuration.default_priority
    )
    resolved_parent = parent
    if parent is not None:
        try:
            resolved_parent = resolve_issue_identifier(
                issues_dir, configuration.project_key, parent
            )
        except IssueLookupError as error:
            raise IssueCreationError(str(error)) from error

    if validate:
        valid_types = configuration.hierarchy + configuration.types
        if resolved_type not in valid_types:
            raise IssueCreationError("unknown issue type")

        if resolved_priority not in configuration.priorities:
            raise IssueCreationError("invalid priority")

        if resolved_parent is not None:
            parent_path = issues_dir / f"{resolved_parent}.json"
            if not parent_path.exists():
                raise IssueCreationError("not found")
            parent_issue = read_issue_from_file(parent_path)
            try:
                validate_parent_child_relationship(
                    configuration, parent_issue.issue_type, resolved_type
                )
            except InvalidHierarchyError as error:
                raise IssueCreationError(str(error)) from error

        duplicate_identifier = _find_duplicate_title(issues_dir, title)
        if duplicate_identifier is not None:
            message = (
                f'duplicate title: "{title}" already exists as {duplicate_identifier}'
            )
            raise IssueCreationError(message)

        try:
            validate_status_value(
                configuration, resolved_type, configuration.initial_status
            )
        except InvalidTransitionError as error:
            raise IssueCreationError(str(error)) from error

    existing_ids = list_issue_identifiers(project_dir / "issues")
    if local_dir is not None:
        local_issues_dir = local_dir / "issues"
        if local_issues_dir.exists():
            existing_ids.update(list_issue_identifiers(local_issues_dir))
    created_at = datetime.now(timezone.utc)
    identifier_request = IssueIdentifierRequest(
        title=title,
        existing_ids=existing_ids,
        prefix=configuration.project_key,
    )
    identifier = generate_issue_identifier(identifier_request).identifier
    updated_at = created_at

    resolved_assignee = assignee if assignee is not None else configuration.assignee

    issue = IssueData(
        id=identifier,
        title=title,
        description=description or "",
        type=resolved_type,
        status=configuration.initial_status,
        priority=resolved_priority,
        assignee=resolved_assignee,
        creator=None,
        parent=resolved_parent,
        labels=list(labels),
        dependencies=[],
        comments=[],
        created_at=created_at,
        updated_at=updated_at,
        closed_at=None,
        custom={},
    )

    policies_dir = project_dir / "policies"
    if policies_dir.is_dir():
        from kanbus.policy_loader import load_policies
        from kanbus.policy_evaluator import evaluate_policies
        from kanbus.policy_context import PolicyContext, PolicyOperation
        from kanbus.issue_listing import load_issues_from_directory

        policy_documents = load_policies(policies_dir)
        if policy_documents:
            all_issues = load_issues_from_directory(issues_dir)
            context = PolicyContext(
                current_issue=None,
                proposed_issue=issue,
                transition=None,
                operation=PolicyOperation.CREATE,
                project_configuration=configuration,
                all_issues=all_issues,
            )
            evaluate_policies(context, policy_documents)

    issue_path = issues_dir / f"{identifier}.json"
    write_issue_to_file(issue, issue_path)

    occurred_at = now_timestamp()
    actor_id = get_current_user()
    event = create_event(
        issue_id=issue.identifier,
        event_type="issue_created",
        actor_id=actor_id,
        payload=issue_created_payload(issue),
        occurred_at=occurred_at,
    )
    try:
        events_dir = (
            events_dir_for_local(project_dir)
            if local
            else events_dir_for_project(project_dir)
        )
        write_events_batch(events_dir, [event])
    except Exception as error:  # noqa: BLE001
        issue_path.unlink(missing_ok=True)
        raise IssueCreationError(str(error)) from error
    return IssueCreationResult(issue=issue, configuration=configuration)


def _find_duplicate_title(issues_dir: Path, title: str) -> Optional[str]:
    normalized_title = title.strip().casefold()
    for issue_path in issues_dir.glob("*.json"):
        try:
            issue = read_issue_from_file(issue_path)
        except (ValueError, ValidationError):
            continue
        if issue.title.strip().casefold() == normalized_title:
            return issue.identifier
    return None
