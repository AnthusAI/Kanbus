"""Console snapshot helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from pydantic import ValidationError
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.issue_listing import IssueListingError, list_issues
from kanbus.migration import MigrationError, load_beads_issues
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project import ProjectMarkerError, get_configuration_path


class ConsoleSnapshotError(RuntimeError):
    """Raised when building a console snapshot fails."""


def build_console_snapshot(root: Path) -> Dict[str, object]:
    """Build a console snapshot payload for the given repository root.

    :param root: Repository root path.
    :type root: Path
    :return: Snapshot payload.
    :rtype: Dict[str, object]
    :raises ConsoleSnapshotError: If snapshot creation fails.
    """
    project_dir, config = _load_project_context(root)
    issues = _load_console_issues(root, project_dir, config)
    updated_at = _format_timestamp(datetime.now(timezone.utc))
    return {
        "config": config.model_dump(),
        "issues": [issue.model_dump(by_alias=True, mode="json") for issue in issues],
        "updated_at": updated_at,
    }


def _load_project_context(root: Path) -> tuple[Path, ProjectConfiguration]:
    try:
        configuration_path = get_configuration_path(root)
    except (ProjectMarkerError, ConfigurationError) as error:
        raise ConsoleSnapshotError(str(error)) from error
    try:
        configuration = load_project_configuration(configuration_path)
    except ConfigurationError as error:
        raise ConsoleSnapshotError(str(error)) from error
    project_dir = configuration_path.parent / configuration.project_directory
    return project_dir, configuration


def _load_console_issues(
    root: Path,
    project_dir: Path,
    configuration: ProjectConfiguration,
) -> List[IssueData]:
    if configuration.virtual_projects:
        return _load_issues_with_virtual_projects(root, configuration)
    if configuration.beads_compatibility:
        try:
            issues = load_beads_issues(root)
        except MigrationError as error:
            raise ConsoleSnapshotError(str(error)) from error
        issues.sort(key=lambda issue: issue.identifier)
        return issues
    issues_dir = project_dir / "issues"
    if not issues_dir.exists():
        raise ConsoleSnapshotError("project/issues directory not found")
    if not issues_dir.is_dir():
        raise ConsoleSnapshotError("project/issues directory not found")

    issues: List[IssueData] = []
    try:
        entries = sorted(
            (entry for entry in issues_dir.iterdir() if entry.is_file()),
            key=lambda item: item.name,
        )
    except OSError as error:
        raise ConsoleSnapshotError(str(error)) from error

    for entry in entries:
        if entry.suffix != ".json":
            continue
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConsoleSnapshotError("issue file is invalid") from error
        try:
            issues.append(IssueData.model_validate(payload))
        except ValidationError as error:
            raise ConsoleSnapshotError("issue file is invalid") from error

    issues.sort(key=lambda issue: issue.identifier)
    return issues


def _load_issues_with_virtual_projects(
    root: Path,
    configuration: ProjectConfiguration,
) -> List[IssueData]:
    try:
        beads_mode = configuration.beads_compatibility
        issues = list_issues(root, beads_mode=beads_mode)
    except IssueListingError as error:
        raise ConsoleSnapshotError(str(error)) from error
    issues.sort(key=lambda issue: issue.identifier)
    return issues


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
