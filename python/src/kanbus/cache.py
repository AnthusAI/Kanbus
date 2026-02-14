"""Index cache utilities for Kanbus."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from kanbus.index import IssueIndex
from kanbus.models import IssueData


@dataclass
class IndexCache:
    """Serialized index cache representation."""

    version: int
    built_at: datetime
    file_mtimes: Dict[str, float]
    issues: List[IssueData]
    reverse_deps: Dict[str, List[str]]


def _normalize_mtime(value: float) -> float:
    """Normalize file modification times for cache consistency.

    :param value: Raw modification time value.
    :type value: float
    :return: Rounded modification time to microsecond precision.
    :rtype: float
    """
    return round(value, 6)


def collect_issue_file_mtimes(issues_directory: Path) -> Dict[str, float]:
    """Collect file modification times for issues.

    :param issues_directory: Directory containing issue files.
    :type issues_directory: Path
    :return: Mapping of filename to mtime.
    :rtype: Dict[str, float]
    """
    mtimes: Dict[str, float] = {}
    for entry in os.scandir(issues_directory):
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        mtimes[entry.name] = _normalize_mtime(entry.stat().st_mtime)
    return mtimes


def load_cache_if_valid(
    cache_path: Path, issues_directory: Path
) -> Optional[IssueIndex]:
    """Load cached index if the cache is valid.

    :param cache_path: Path to cache file.
    :type cache_path: Path
    :param issues_directory: Directory containing issue files.
    :type issues_directory: Path
    :return: IssueIndex if cache is valid, otherwise None.
    :rtype: Optional[IssueIndex]
    """
    if not cache_path.exists():
        return None

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    file_mtimes = payload.get("file_mtimes", {})
    current_mtimes = collect_issue_file_mtimes(issues_directory)
    if file_mtimes != current_mtimes:
        return None

    issues = [IssueData.model_validate(item) for item in payload.get("issues", [])]
    reverse_deps = payload.get("reverse_deps", {})
    return build_index_from_cache(issues, reverse_deps)


def write_cache(
    index: IssueIndex, cache_path: Path, file_mtimes: Dict[str, float]
) -> None:
    """Write an index cache file to disk.

    :param index: Issue index to serialize.
    :type index: IssueIndex
    :param cache_path: Path to cache file.
    :type cache_path: Path
    :param file_mtimes: File modification time mapping.
    :type file_mtimes: Dict[str, float]
    """
    cache = IndexCache(
        version=1,
        built_at=datetime.now(timezone.utc),
        file_mtimes=file_mtimes,
        issues=list(index.by_id.values()),
        reverse_deps={
            target: [issue.identifier for issue in issues]
            for target, issues in index.reverse_dependencies.items()
        },
    )
    payload = {
        "version": cache.version,
        "built_at": cache.built_at.isoformat().replace("+00:00", "Z"),
        "file_mtimes": cache.file_mtimes,
        "issues": [
            issue.model_dump(by_alias=True, mode="json") for issue in cache.issues
        ],
        "reverse_deps": cache.reverse_deps,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def build_index_from_cache(
    issues: List[IssueData], reverse_deps: Dict[str, List[str]]
) -> IssueIndex:
    """Rebuild an IssueIndex from cached data.

    :param issues: Issues from cache.
    :type issues: List[IssueData]
    :param reverse_deps: Reverse dependency mapping.
    :type reverse_deps: Dict[str, List[str]]
    :return: IssueIndex populated from cache.
    :rtype: IssueIndex
    """
    index = IssueIndex()
    for issue in issues:
        index.by_id[issue.identifier] = issue
        index.by_status.setdefault(issue.status, []).append(issue)
        index.by_type.setdefault(issue.issue_type, []).append(issue)
        if issue.parent is not None:
            index.by_parent.setdefault(issue.parent, []).append(issue)
        for label in issue.labels:
            index.by_label.setdefault(label, []).append(issue)

    for target, issue_ids in reverse_deps.items():
        index.reverse_dependencies[target] = [
            index.by_id[identifier]
            for identifier in issue_ids
            if identifier in index.by_id
        ]

    return index
