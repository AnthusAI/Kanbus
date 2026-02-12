"""Maintenance command implementations."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from pydantic import ValidationError as PydanticValidationError

from taskulus.config_loader import ConfigurationError, load_project_configuration
from taskulus.dependencies import ALLOWED_DEPENDENCY_TYPES
from taskulus.hierarchy import InvalidHierarchyError, validate_parent_child_relationship
from taskulus.models import IssueData, ProjectConfiguration
from taskulus.project import ProjectMarkerError, load_project_directory
from taskulus.workflows import get_workflow_for_issue_type


class ProjectValidationError(RuntimeError):
    """Raised when project validation fails."""


class ProjectStatsError(RuntimeError):
    """Raised when project statistics cannot be computed."""


@dataclass(frozen=True)
class ProjectStats:
    """Aggregate issue statistics for a project.

    :param total: Total number of issues.
    :type total: int
    :param open_count: Number of open issues.
    :type open_count: int
    :param closed_count: Number of closed issues.
    :type closed_count: int
    :param type_counts: Counts by issue type.
    :type type_counts: Dict[str, int]
    """

    total: int
    open_count: int
    closed_count: int
    type_counts: Dict[str, int]


def validate_project(root: Path) -> None:
    """Validate issue data and configuration for a Taskulus project.

    :param root: Repository root path.
    :type root: Path
    :raises ProjectValidationError: If validation fails.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise ProjectValidationError(str(error)) from error

    issues_dir = project_dir / "issues"
    if not issues_dir.exists():
        raise ProjectValidationError("issues directory missing")

    try:
        configuration = load_project_configuration(project_dir / "config.yaml")
    except ConfigurationError as error:
        raise ProjectValidationError(str(error)) from error

    errors: List[str] = []
    issues: Dict[str, IssueData] = {}
    for issue_path in sorted(issues_dir.glob("*.json"), key=lambda path: path.name):
        issue = _load_issue(issue_path, errors)
        if issue is None:
            continue
        if issue.identifier in issues:
            errors.append(f"{issue_path.name}: duplicate issue id '{issue.identifier}'")
            continue
        _validate_issue_fields(issue_path.name, issue, configuration, errors)
        issues[issue.identifier] = issue

    _validate_references(issues, configuration, errors)

    if errors:
        raise ProjectValidationError(_format_errors(errors))


def collect_project_stats(root: Path) -> ProjectStats:
    """Collect project statistics from issue data.

    :param root: Repository root path.
    :type root: Path
    :return: Aggregated project statistics.
    :rtype: ProjectStats
    :raises ProjectStatsError: If stats cannot be computed.
    """
    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise ProjectStatsError(str(error)) from error

    issues_dir = project_dir / "issues"
    if not issues_dir.exists():
        raise ProjectStatsError("issues directory missing")

    issues: List[IssueData] = []
    for issue_path in sorted(issues_dir.glob("*.json"), key=lambda path: path.name):
        try:
            payload = json.loads(issue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ProjectStatsError(
                f"{issue_path.name}: invalid json: {error}"
            ) from error
        try:
            issues.append(IssueData.model_validate(payload))
        except PydanticValidationError as error:
            raise ProjectStatsError(
                f"{issue_path.name}: invalid issue data: {error}"
            ) from error

    total = len(issues)
    closed_count = sum(1 for issue in issues if issue.status == "closed")
    open_count = total - closed_count
    type_counts: Dict[str, int] = {}
    for issue in issues:
        type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

    return ProjectStats(
        total=total,
        open_count=open_count,
        closed_count=closed_count,
        type_counts=type_counts,
    )


def _load_issue(issue_path: Path, errors: List[str]) -> Optional[IssueData]:
    try:
        payload = json.loads(issue_path.read_text(encoding="utf-8"))
    except OSError as error:
        errors.append(f"{issue_path.name}: unable to read issue: {error}")
        return None
    except json.JSONDecodeError as error:
        errors.append(f"{issue_path.name}: invalid json: {error}")
        return None
    try:
        return IssueData.model_validate(payload)
    except PydanticValidationError as error:
        errors.append(f"{issue_path.name}: invalid issue data: {error}")
        return None


def _validate_issue_fields(
    filename: str,
    issue: IssueData,
    configuration: ProjectConfiguration,
    errors: List[str],
) -> None:
    valid_types = configuration.hierarchy + configuration.types
    if issue.identifier != Path(filename).stem:
        errors.append(
            f"{filename}: issue id '{issue.identifier}' does not match filename"
        )
    if issue.issue_type not in valid_types:
        errors.append(f"{filename}: unknown issue type '{issue.issue_type}'")
    if issue.priority not in configuration.priorities:
        errors.append(f"{filename}: invalid priority '{issue.priority}'")

    statuses = _collect_workflow_statuses(configuration, issue.issue_type, errors)
    if statuses is not None and issue.status not in statuses:
        errors.append(f"{filename}: invalid status '{issue.status}'")

    if issue.status == "closed" and issue.closed_at is None:
        errors.append(f"{filename}: closed issues must have closed_at set")
    if issue.status != "closed" and issue.closed_at is not None:
        errors.append(f"{filename}: non-closed issues must not set closed_at")

    for dependency in issue.dependencies:
        if dependency.dependency_type not in ALLOWED_DEPENDENCY_TYPES:
            errors.append(
                f"{filename}: invalid dependency type '{dependency.dependency_type}'"
            )


def _collect_workflow_statuses(
    configuration: ProjectConfiguration,
    issue_type: str,
    errors: List[str],
) -> Optional[Set[str]]:
    try:
        workflow = get_workflow_for_issue_type(configuration, issue_type)
    except ValueError as error:
        errors.append(str(error))
        return None
    statuses: Set[str] = set(workflow.keys())
    for transitions in workflow.values():
        statuses.update(transitions)
    return statuses


def _validate_references(
    issues: Dict[str, IssueData],
    configuration: ProjectConfiguration,
    errors: List[str],
) -> None:
    for issue in issues.values():
        if issue.parent:
            parent = issues.get(issue.parent)
            if parent is None:
                errors.append(
                    f"{issue.identifier}: parent '{issue.parent}' does not exist"
                )
            else:
                try:
                    validate_parent_child_relationship(
                        configuration, parent.issue_type, issue.issue_type
                    )
                except InvalidHierarchyError as error:
                    errors.append(f"{issue.identifier}: {error}")

        for dependency in issue.dependencies:
            if dependency.target not in issues:
                errors.append(
                    f"{issue.identifier}: dependency target '{dependency.target}' does not exist"
                )


def _format_errors(errors: List[str]) -> str:
    return "validation failed:\n" + "\n".join(errors)
