"""Unit tests for index cache serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from taskulus.cache import (
    collect_issue_file_mtimes,
    load_cache_if_valid,
    write_cache,
)
from taskulus.index import build_index_from_directory
from taskulus.models import IssueData


def write_issue_file(directory: Path, issue: IssueData) -> None:
    """Write an issue JSON file with standard formatting.

    :param directory: Directory to write into.
    :type directory: Path
    :param issue: Issue data to serialize.
    :type issue: IssueData
    """
    payload = issue.model_dump(by_alias=True, mode="json")
    issue_path = directory / f"{issue.identifier}.json"
    issue_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def build_issue(identifier: str, status: str) -> IssueData:
    """Build an IssueData instance for cache tests.

    :param identifier: Issue ID.
    :type identifier: str
    :param status: Issue status.
    :type status: str
    :return: Issue data instance.
    :rtype: IssueData
    """
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)
    return IssueData(
        id=identifier,
        title=f"Title {identifier}",
        description="",
        type="task",
        status=status,
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=timestamp,
        updated_at=timestamp,
        closed_at=None,
        custom={},
    )


def test_cache_loads_when_mtimes_match(tmp_path: Path) -> None:
    """Cache should load when mtimes match current files."""
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    cache_path = tmp_path / ".cache" / "index.json"

    issue_one = build_issue("tsk-aaa", "open")
    issue_two = build_issue("tsk-bbb", "closed")
    write_issue_file(issues_dir, issue_one)
    write_issue_file(issues_dir, issue_two)

    index = build_index_from_directory(issues_dir)
    file_mtimes = collect_issue_file_mtimes(issues_dir)
    write_cache(index, cache_path, file_mtimes)

    loaded = load_cache_if_valid(cache_path, issues_dir)
    assert loaded is not None
    assert len(loaded.by_id) == 2


def test_cache_invalidates_on_mtime_change(tmp_path: Path) -> None:
    """Cache should invalidate when mtimes change."""
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    cache_path = tmp_path / ".cache" / "index.json"

    issue_one = build_issue("tsk-aaa", "open")
    write_issue_file(issues_dir, issue_one)

    index = build_index_from_directory(issues_dir)
    file_mtimes = collect_issue_file_mtimes(issues_dir)
    write_cache(index, cache_path, file_mtimes)

    issue_path = issues_dir / "tsk-aaa.json"
    issue_path.write_text(
        issue_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )

    loaded = load_cache_if_valid(cache_path, issues_dir)
    assert loaded is None
