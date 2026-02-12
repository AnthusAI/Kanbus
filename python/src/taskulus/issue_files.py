"""Issue file input/output helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Set

from taskulus.models import IssueData


def list_issue_identifiers(issues_directory: Path) -> Set[str]:
    """List issue identifiers based on JSON filenames.

    :param issues_directory: Directory containing issue files.
    :type issues_directory: Path
    :return: Set of issue identifiers.
    :rtype: Set[str]
    """
    return {path.stem for path in issues_directory.glob("*.json")}


def read_issue_from_file(issue_path: Path) -> IssueData:
    """Read an issue from a JSON file.

    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    :return: Parsed issue data.
    :rtype: IssueData
    """
    payload = json.loads(issue_path.read_bytes())
    return IssueData.model_validate(payload)


def write_issue_to_file(issue: IssueData, issue_path: Path) -> None:
    """Write an issue to a JSON file with pretty formatting.

    :param issue: Issue data to serialize.
    :type issue: IssueData
    :param issue_path: Path to the issue JSON file.
    :type issue_path: Path
    """
    payload = issue.model_dump(by_alias=True, mode="json")
    issue_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )
