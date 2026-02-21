"""Console snapshot helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.issue_files import read_issue_from_file
from kanbus.migration import MigrationError, load_beads_issues
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project import (
    ProjectMarkerError,
    find_project_local_directory,
    get_configuration_path,
    resolve_labeled_projects,
)


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
        shared = _read_issues_from_dir(issues_dir)
        for issue in shared:
            issues.append(_tag_issue(issue, source="shared"))
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ConsoleSnapshotError("issue file is invalid") from error

    local_dir = find_project_local_directory(project_dir)
    if local_dir is not None:
        local_issues_dir = local_dir / "issues"
        if local_issues_dir.is_dir():
            try:
                local = _read_issues_from_dir(local_issues_dir)
                for issue in local:
                    issues.append(_tag_issue(issue, source="local"))
            except (OSError, json.JSONDecodeError, ValidationError) as error:
                raise ConsoleSnapshotError("issue file is invalid") from error

    issues.sort(key=lambda issue: issue.identifier)
    return issues


def _load_issues_with_virtual_projects(
    root: Path,
    configuration: ProjectConfiguration,
) -> List[IssueData]:
    try:
        labeled = resolve_labeled_projects(root)
    except Exception as error:
        raise ConsoleSnapshotError(str(error)) from error

    all_issues: List[IssueData] = []
    for project in labeled:
        issues_dir = project.project_dir / "issues"
        if issues_dir.is_dir():
            try:
                shared = _read_issues_from_dir(issues_dir)
                for issue in shared:
                    all_issues.append(
                        _tag_issue(issue, project_label=project.label, source="shared")
                    )
            except Exception as error:
                raise ConsoleSnapshotError(str(error)) from error

            local_dir = find_project_local_directory(project.project_dir)
            if local_dir is not None:
                local_issues_dir = local_dir / "issues"
                if local_issues_dir.is_dir():
                    try:
                        local = _read_issues_from_dir(local_issues_dir)
                        for issue in local:
                            all_issues.append(
                                _tag_issue(
                                    issue,
                                    project_label=project.label,
                                    source="local",
                                )
                            )
                    except Exception as error:
                        raise ConsoleSnapshotError(str(error)) from error
        else:
            repo_root = project.project_dir.parent
            if repo_root is not None:
                beads_path = repo_root / ".beads" / "issues.jsonl"
                if beads_path.exists():
                    try:
                        beads_issues = load_beads_issues(repo_root)
                        for issue in beads_issues:
                            all_issues.append(
                                _tag_issue(
                                    issue,
                                    project_label=project.label,
                                    source="shared",
                                )
                            )
                    except MigrationError as error:
                        raise ConsoleSnapshotError(str(error)) from error

    all_issues.sort(key=lambda issue: issue.identifier)
    return all_issues


def _read_issues_from_dir(issues_dir: Path) -> List[IssueData]:
    issues: List[IssueData] = []
    entries = sorted(
        (entry for entry in issues_dir.iterdir() if entry.is_file()),
        key=lambda item: item.name,
    )
    for entry in entries:
        if entry.suffix != ".json":
            continue
        issues.append(read_issue_from_file(entry))
    return issues


def _tag_issue(
    issue: IssueData,
    project_label: str | None = None,
    source: str | None = None,
) -> IssueData:
    custom = {**issue.custom}
    if project_label is not None:
        custom["project_label"] = project_label
    if source is not None:
        custom["source"] = source
    return issue.model_copy(update={"custom": custom})


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
