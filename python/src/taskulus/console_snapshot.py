"""Console snapshot helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from taskulus.config_loader import ConfigurationError, load_project_configuration
from taskulus.models import IssueData
from taskulus.project import ProjectMarkerError, get_configuration_path


class ConsoleSnapshotError(RuntimeError):
    """Raised when building a console snapshot fails."""


class ConsoleProjectConfig(BaseModel):
    """Console-visible project configuration."""

    model_config = ConfigDict(extra="ignore")

    prefix: str
    hierarchy: List[str]
    types: List[str]
    workflows: Dict[str, Dict[str, List[str]]]
    initial_status: str
    priorities: Dict[int, str]
    default_priority: int
    beads_compatibility: bool = False


def build_console_snapshot(root: Path) -> Dict[str, object]:
    """Build a console snapshot payload for the given repository root.

    :param root: Repository root path.
    :type root: Path
    :return: Snapshot payload.
    :rtype: Dict[str, object]
    :raises ConsoleSnapshotError: If snapshot creation fails.
    """
    project_dir = _load_project_directory(root)
    config = _load_console_config(project_dir)
    issues = _load_console_issues(project_dir)
    updated_at = _format_timestamp(datetime.now(timezone.utc))
    return {
        "config": config.model_dump(),
        "issues": [issue.model_dump(by_alias=True, mode="json") for issue in issues],
        "updated_at": updated_at,
    }


def _load_project_directory(root: Path) -> Path:
    try:
        configuration_path = get_configuration_path(root)
    except (ProjectMarkerError, ConfigurationError) as error:
        raise ConsoleSnapshotError(str(error)) from error
    configuration = load_project_configuration(configuration_path)
    return configuration_path.parent / configuration.project_directory


def _load_console_config(project_dir: Path) -> ConsoleProjectConfig:
    config_path = project_dir / "config.yaml"
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConsoleSnapshotError("project/config.yaml not found") from error
    except OSError as error:
        raise ConsoleSnapshotError(str(error)) from error

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ConsoleSnapshotError("config.yaml is invalid") from error

    if not isinstance(parsed, dict):
        raise ConsoleSnapshotError("config.yaml is invalid")

    try:
        return ConsoleProjectConfig.model_validate(parsed)
    except ValidationError as error:
        raise ConsoleSnapshotError("config.yaml is invalid") from error


def _load_console_issues(project_dir: Path) -> List[IssueData]:
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


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
