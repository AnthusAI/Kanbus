"""In-memory index building for Taskulus issues."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, List

from taskulus.models import IssueData


@dataclass
class IssueIndex:
    """In-memory lookup tables for issues."""

    by_id: Dict[str, IssueData] = field(default_factory=dict)
    by_status: Dict[str, List[IssueData]] = field(default_factory=dict)
    by_type: Dict[str, List[IssueData]] = field(default_factory=dict)
    by_parent: Dict[str, List[IssueData]] = field(default_factory=dict)
    by_label: Dict[str, List[IssueData]] = field(default_factory=dict)
    reverse_dependencies: Dict[str, List[IssueData]] = field(default_factory=dict)


def build_index_from_directory(issues_directory: Path) -> IssueIndex:
    """Build an IssueIndex by scanning issue files in a directory.

    :param issues_directory: Directory containing issue JSON files.
    :type issues_directory: Path
    :return: In-memory issue index.
    :rtype: IssueIndex
    """
    index = IssueIndex()
    issue_paths = sorted(
        issues_directory.glob("*.json"), key=lambda path: path.name
    )
    for issue_path in issue_paths:
        payload = json.loads(issue_path.read_text(encoding="utf-8"))
        issue = IssueData.model_validate(payload)
        index.by_id[issue.identifier] = issue
        index.by_status.setdefault(issue.status, []).append(issue)
        index.by_type.setdefault(issue.issue_type, []).append(issue)
        if issue.parent is not None:
            index.by_parent.setdefault(issue.parent, []).append(issue)
        for label in issue.labels:
            index.by_label.setdefault(label, []).append(issue)
        for dependency in issue.dependencies:
            if dependency.dependency_type == "blocked-by":
                index.reverse_dependencies.setdefault(dependency.target, []).append(
                    issue
                )
    return index
