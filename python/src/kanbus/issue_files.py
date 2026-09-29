"""Issue file input/output helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Set

from kanbus.models import IssueData
from virtuus import Table


def _issue_table(issues_directory: Path) -> Table:
    """Open canonical issue files through Virtuus."""
    table = Table(
        "issues",
        primary_key="identifier",
        directory=str(issues_directory),
        validation="error",
        storage="memory",
        pretty_json=True,
    )
    table.add_gsi("by_status", "status")
    table.add_gsi("by_type", "issue_type")
    table.add_gsi("by_parent", "parent")
    table.load_from_dir()
    return table


def list_issue_identifiers(issues_directory: Path) -> Set[str]:
    """List issue identifiers based on JSON filenames.

    :param issues_directory: Directory containing issue files.
    :type issues_directory: Path
    :return: Set of issue identifiers.
    :rtype: Set[str]
    """
    if not issues_directory.is_dir():
        return set()
    return {
        str(record["identifier"])
        for record in _issue_table(issues_directory).scan()
        if "identifier" in record
    }


def read_issue_from_file(issue_path: Path) -> IssueData:
    """Read an issue from a JSON file.

    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    :return: Parsed issue data.
    :rtype: IssueData
    """
    record = _issue_table(issue_path.parent).get(issue_path.stem)
    if record is None:
        raise FileNotFoundError(issue_path)
    return IssueData.model_validate(record)


def write_issue_to_file(issue: IssueData, issue_path: Path) -> None:
    """Write an issue to a JSON file with pretty formatting.

    :param issue: Issue data to serialize.
    :type issue: IssueData
    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    """
    if issue_path.is_dir():
        raise IsADirectoryError(issue_path)
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    _issue_table(issue_path.parent).put(issue.model_dump(by_alias=True, mode="json"))
