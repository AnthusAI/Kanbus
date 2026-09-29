"""Issue file input/output helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Set

from kanbus.models import IssueData
from kanbus.daemon_client import is_daemon_enabled, request_virtuus
from virtuus import Table


def _issue_table(issues_directory: Path) -> Table:
    """Open canonical issue files through Virtuus."""
    table = Table(
        "issues",
        primary_key="id",
        directory=str(issues_directory),
        validation="warn",
        storage="memory",
        pretty_json=True,
    )
    table.add_gsi("by_status", "status")
    table.add_gsi("by_type", "type")
    table.add_gsi("by_parent", "parent")
    table.add_gsi("by_label", "labels[*]")
    table.add_gsi(
        "blocked_by", "dependencies[dependency_type=blocked-by].target"
    )
    table.load_from_dir()
    return table


def _service_spec(issues_directory: Path) -> dict[str, object]:
    return {
        "name": "issues",
        "primary_key": "id",
        "directory": str(issues_directory),
        "validation": "warn",
        "pretty_json": True,
        "reconcile_seconds": 2,
        "indexes": [
            {"name": "by_status", "partition_key": "status"},
            {"name": "by_type", "partition_key": "type"},
            {"name": "by_parent", "partition_key": "parent"},
            {"name": "by_label", "partition_key": "labels[*]"},
            {
                "name": "blocked_by",
                "partition_key": "dependencies[dependency_type=blocked-by].target",
            },
        ],
    }


def _project_root(issues_directory: Path) -> Path:
    """Find the Kanbus root associated with an issue directory."""
    for candidate in (issues_directory, *issues_directory.parents):
        if (candidate / ".kanbus.yml").is_file():
            return candidate
    parent = issues_directory.parent
    if parent.name in {"project", "project-local"}:
        return parent.parent
    return parent


def _use_service(issues_directory: Path) -> bool:
    """Return whether this directory belongs to a daemon-addressable project."""
    root = _project_root(issues_directory)
    return is_daemon_enabled() and (root / ".kanbus.yml").is_file()


def _service_request(issues_directory: Path, request: dict[str, object]) -> object:
    """Open the retained table and execute one service operation."""
    root = _project_root(issues_directory)
    opened = request_virtuus(root, {"action": "open_table", "spec": _service_spec(issues_directory)})
    if not isinstance(opened, dict) or not isinstance(opened.get("handle"), str):
        raise RuntimeError("Virtuus daemon returned no table handle")
    request["handle"] = opened["handle"]
    return request_virtuus(root, request)


def list_issue_identifiers(issues_directory: Path) -> Set[str]:
    """List issue identifiers based on JSON filenames.

    :param issues_directory: Directory containing issue files.
    :type issues_directory: Path
    :return: Set of issue identifiers.
    :rtype: Set[str]
    """
    if not issues_directory.is_dir():
        return set()
    return {path.stem for path in issues_directory.glob("*.json")}


def read_issue_from_file(issue_path: Path) -> IssueData:
    """Read an issue from a JSON file.

    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    :return: Parsed issue data.
    :rtype: IssueData
    """
    record = (
        _service_request(issue_path.parent, {"action": "get", "pk": issue_path.stem})
        if _use_service(issue_path.parent)
        else _issue_table(issue_path.parent).get(issue_path.stem)
    )
    if record is None:
        raise FileNotFoundError(issue_path)
    return IssueData.model_validate(record)


def read_issues_from_directory(issues_directory: Path) -> list[IssueData]:
    """Load canonical issue files through one Virtuus table scan."""
    if not issues_directory.is_dir():
        return []
    records = (
        _service_request(issues_directory, {"action": "scan"})
        if _use_service(issues_directory)
        else _issue_table(issues_directory).scan()
    )
    return sorted(
        (IssueData.model_validate(record) for record in records),
        key=lambda issue: issue.identifier,
    )


def write_issue_to_file(issue: IssueData, issue_path: Path) -> None:
    """Write an issue to a JSON file with pretty formatting.

    :param issue: Issue data to serialize.
    :type issue: IssueData
    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    """
    if issue_path.is_dir():
        raise IsADirectoryError(issue_path)
    record = issue.model_dump(by_alias=True, mode="json")
    if _use_service(issue_path.parent):
        _service_request(issue_path.parent, {"action": "put", "record": record})
    else:
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        _issue_table(issue_path.parent).put(record)


def delete_issue_file(issue_path: Path) -> None:
    """Delete an issue through the resident Virtuus table when available."""
    if _use_service(issue_path.parent):
        _service_request(issue_path.parent, {"action": "delete", "pk": issue_path.stem})
    elif issue_path.exists():
        _issue_table(issue_path.parent).delete(issue_path.stem)
