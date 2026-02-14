"""Beads to Taskulus migration helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import click

from taskulus.config_loader import load_project_configuration
from taskulus.file_io import ensure_git_repository, initialize_project
from taskulus.hierarchy import InvalidHierarchyError, validate_parent_child_relationship
from taskulus.issue_files import write_issue_to_file
from taskulus.models import (
    DependencyLink,
    IssueComment,
    IssueData,
    ProjectConfiguration,
    PriorityDefinition,
)
from taskulus.project import discover_project_directories, get_configuration_path
from taskulus.workflows import get_workflow_for_issue_type

BEADS_ISSUE_TYPE_MAP = {"feature": "story", "message": "task"}


class MigrationError(RuntimeError):
    """Raised when migration fails."""


@dataclass(frozen=True)
class MigrationResult:
    """Result of a migration run."""

    issue_count: int


def load_beads_issues(root: Path) -> List[IssueData]:
    """Load Beads issues.jsonl into Taskulus issue models without migration.

    :param root: Repository root path.
    :type root: Path
    :return: Loaded Taskulus issue models.
    :rtype: List[IssueData]
    :raises MigrationError: If the Beads data cannot be read.
    """
    beads_dir = root / ".beads"
    if not beads_dir.exists():
        raise MigrationError("no .beads directory")

    issues_path = beads_dir / "issues.jsonl"
    if not issues_path.exists():
        raise MigrationError("no issues.jsonl")

    records = _load_beads_records(issues_path)
    configuration = _load_configuration_for_beads(root, records)
    record_by_id = {record["id"]: record for record in records}
    return [_convert_record(record, record_by_id, configuration) for record in records]


def load_beads_issue(root: Path, identifier: str) -> IssueData:
    """Load a single Beads issue by identifier.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Matching issue data.
    :rtype: IssueData
    :raises MigrationError: If the issue cannot be found.
    """
    issues = load_beads_issues(root)
    for issue in issues:
        if issue.identifier == identifier:
            return issue
    raise MigrationError("not found")


def migrate_from_beads(root: Path) -> MigrationResult:
    """Migrate Beads issues.jsonl into a Taskulus project.

    :param root: Repository root path.
    :type root: Path
    :return: Migration result.
    :rtype: MigrationResult
    :raises MigrationError: If migration fails.
    """
    try:
        ensure_git_repository(root)
    except Exception as error:
        raise MigrationError(str(error)) from error

    beads_dir = root / ".beads"
    if not beads_dir.exists():
        raise MigrationError("no .beads directory")

    issues_path = beads_dir / "issues.jsonl"
    if not issues_path.exists():
        raise MigrationError("no issues.jsonl")

    if discover_project_directories(root):
        raise MigrationError("already initialized")

    initialize_project(root)
    project_dir = root / "project"
    configuration = load_project_configuration(get_configuration_path(root))

    records = _load_beads_records(issues_path)
    record_by_id = {record["id"]: record for record in records}

    for record in records:
        issue = _convert_record(record, record_by_id, configuration)
        issue_path = project_dir / "issues" / f"{issue.identifier}.json"
        write_issue_to_file(issue, issue_path)

    return MigrationResult(issue_count=len(records))


def _load_beads_records(issues_path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in issues_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if "id" not in record:
            raise MigrationError("missing id")
        records.append(record)
    return records


def _load_configuration_for_beads(
    root: Path, records: List[Dict[str, Any]]
) -> ProjectConfiguration:
    """Build configuration derived from Beads records."""
    _ = root
    issue_types = sorted(
        {record.get("issue_type", "") for record in records if record.get("issue_type")}
    )
    hierarchy = ["epic", "task", "sub-task"]
    types = [issue_type for issue_type in issue_types if issue_type not in hierarchy]
    if "feature" in issue_types and "story" not in types:
        types.append("story")

    # Build permissive workflows allowing any status transition.
    statuses = sorted(
        {record.get("status", "") for record in records if record.get("status")}
        | {"open", "in_progress", "blocked", "deferred", "closed"}
    )
    workflow_state = {status: statuses for status in statuses}
    workflows = {
        "default": workflow_state,
        "epic": workflow_state,
        "task": workflow_state,
    }

    priorities: Dict[int, PriorityDefinition] = {}
    for value in sorted(
        {
            record.get("priority")
            for record in records
            if record.get("priority") is not None
        }
        | {0, 1, 2, 3, 4}
    ):
        priorities[int(value)] = PriorityDefinition(name=f"P{int(value)}")

    return ProjectConfiguration(
        project_directory="project",
        external_projects=[],
        project_key="BD",
        hierarchy=hierarchy,
        types=types,
        workflows=workflows,
        initial_status="open",
        priorities=priorities,
        default_priority=2,
        status_colors={},
        type_colors={},
    )


def _convert_record(
    record: Dict[str, Any],
    record_by_id: Dict[str, Dict[str, Any]],
    configuration: ProjectConfiguration,
) -> IssueData:
    identifier = record["id"]
    title = record.get("title", "").strip()
    if not title:
        raise MigrationError("title is required")
    issue_type = record.get("issue_type", "").strip()
    if not issue_type:
        raise MigrationError("issue_type is required")
    canonical_issue_type = BEADS_ISSUE_TYPE_MAP.get(issue_type, issue_type)
    _validate_issue_type(configuration, canonical_issue_type)

    status = record.get("status", "").strip()
    if not status:
        raise MigrationError("status is required")
    _validate_status(configuration, canonical_issue_type, status)

    priority = record.get("priority")
    if priority is None:
        raise MigrationError("priority is required")
    if priority not in configuration.priorities:
        raise MigrationError("invalid priority")

    created_at = _parse_timestamp(record.get("created_at"), "created_at")
    updated_at = _parse_timestamp(record.get("updated_at"), "updated_at")
    closed_at_value = record.get("closed_at")
    closed_at = None
    if closed_at_value:
        closed_at = _parse_timestamp(closed_at_value, "closed_at")

    parent, dependencies = _convert_dependencies(
        record.get("dependencies", []),
        identifier,
        record_by_id,
        configuration,
        canonical_issue_type,
    )

    comment_items = record.get("comments", []) or []
    comments = [_convert_comment(item) for item in comment_items]

    custom: Dict[str, object] = {}
    if record.get("owner"):
        custom["beads_owner"] = record["owner"]
    if record.get("notes"):
        custom["beads_notes"] = record["notes"]
    if record.get("acceptance_criteria"):
        custom["beads_acceptance_criteria"] = record["acceptance_criteria"]
    if record.get("close_reason"):
        custom["beads_close_reason"] = record["close_reason"]
    if canonical_issue_type != issue_type:
        custom["beads_issue_type"] = issue_type

    return IssueData(
        id=identifier,
        title=title,
        description=record.get("description", ""),
        type=canonical_issue_type,
        status=status,
        priority=priority,
        assignee=record.get("assignee"),
        creator=record.get("created_by"),
        parent=parent,
        labels=[],
        dependencies=dependencies,
        comments=comments,
        created_at=created_at,
        updated_at=updated_at,
        closed_at=closed_at,
        custom=custom,
    )


def _convert_dependencies(
    dependencies: Iterable[Dict[str, Any]],
    identifier: str,
    record_by_id: Dict[str, Dict[str, Any]],
    configuration: ProjectConfiguration,
    issue_type: str,
) -> tuple[str | None, List[DependencyLink]]:
    parent = None
    dependency_links: List[DependencyLink] = []
    for dependency in dependencies:
        dependency_type = dependency.get("type")
        depends_on_id = dependency.get("depends_on_id")
        if not dependency_type or not depends_on_id:
            raise MigrationError("invalid dependency")
        if depends_on_id not in record_by_id:
            raise MigrationError("missing dependency")
        if dependency_type == "parent-child":
            if parent is None:
                parent = depends_on_id
            else:
                raise MigrationError("multiple parents")
        else:
            dependency_links.append(
                DependencyLink(target=depends_on_id, type=dependency_type)
            )

    if parent is not None:
        parent_issue_type = record_by_id[parent].get("issue_type", "")
        if not parent_issue_type:
            raise MigrationError("parent issue_type is required")
        canonical_parent_type = BEADS_ISSUE_TYPE_MAP.get(
            parent_issue_type, parent_issue_type
        )
        if not (
            canonical_parent_type == issue_type
            and canonical_parent_type in {"epic", "task"}
        ):
            try:
                validate_parent_child_relationship(
                    configuration, canonical_parent_type, issue_type
                )
            except InvalidHierarchyError as error:
                click.echo(
                    f"Suggestion: {error}. Remove the parent from '{identifier}' or "
                    "update the hierarchy in project/config.yaml to allow this relationship.",
                    err=True,
                )
                parent = None

    return parent, dependency_links


def _convert_comment(comment: Dict[str, Any]) -> IssueComment:
    author = comment.get("author", "").strip()
    text = comment.get("text", "").strip()
    created_at = _parse_timestamp(comment.get("created_at"), "comment.created_at")
    if not author or not text:
        raise MigrationError("invalid comment")
    return IssueComment(author=author, text=text, created_at=created_at)


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not value:
        raise MigrationError(f"{field_name} is required")
    if isinstance(value, str):
        text = value
    else:
        raise MigrationError(f"{field_name} must be a string")
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    text = _normalize_fractional_seconds(text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise MigrationError(f"invalid {field_name}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_fractional_seconds(text: str) -> str:
    """Pad fractional seconds to six digits so datetime can parse Beads timestamps."""

    if "." not in text:
        return text

    dot_index = text.rfind(".")
    prefix = text[: dot_index + 1]
    remainder = text[dot_index + 1 :]

    # Timezone separator is the last "+" or "-" after the fractional part.
    plus_index = remainder.rfind("+")
    minus_index = remainder.rfind("-")
    tz_index = max(plus_index, minus_index)
    if tz_index == -1:
        return text

    fractional = remainder[:tz_index]
    timezone_part = remainder[tz_index:]
    if not fractional.isdigit():
        return text
    if len(fractional) > 6:
        fractional = fractional[:6]
    elif len(fractional) < 6:
        fractional = fractional.ljust(6, "0")

    return f"{prefix}{fractional}{timezone_part}"


def _validate_issue_type(configuration: ProjectConfiguration, issue_type: str) -> None:
    all_types = configuration.hierarchy + configuration.types
    if issue_type not in all_types:
        raise MigrationError("unknown issue type")


def _validate_status(
    configuration: ProjectConfiguration, issue_type: str, status: str
) -> None:
    workflow = get_workflow_for_issue_type(configuration, issue_type)
    statuses = set(workflow.keys())
    for values in workflow.values():
        statuses.update(values)
    if status not in statuses:
        raise MigrationError("invalid status")
