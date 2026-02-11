"""Unit tests for index building."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from taskulus.index import build_index_from_directory
from taskulus.models import DependencyLink, IssueData


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


def build_issue(
    identifier: str,
    issue_type: str,
    status: str,
    parent: str | None,
    labels: Iterable[str],
    dependencies: list[DependencyLink],
) -> IssueData:
    """Build an IssueData instance for index tests.

    :param identifier: Issue ID.
    :type identifier: str
    :param issue_type: Issue type.
    :type issue_type: str
    :param status: Issue status.
    :type status: str
    :param parent: Parent issue ID.
    :type parent: str | None
    :param labels: Issue labels.
    :type labels: Iterable[str]
    :param dependencies: Dependencies list.
    :type dependencies: list[DependencyLink]
    :return: Issue data instance.
    :rtype: IssueData
    """
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)
    return IssueData(
        id=identifier,
        title=f"Title {identifier}",
        description="",
        type=issue_type,
        status=status,
        priority=2,
        assignee=None,
        creator=None,
        parent=parent,
        labels=list(labels),
        dependencies=dependencies,
        comments=[],
        created_at=timestamp,
        updated_at=timestamp,
        closed_at=None,
        custom={},
    )


def test_build_index_populates_lookup_maps(tmp_path: Path) -> None:
    """Index should populate lookup maps from issue files."""
    parent_issue = build_issue(
        "tsk-parent",
        "epic",
        "open",
        None,
        ["planning"],
        [],
    )
    child_one = build_issue(
        "tsk-child1",
        "task",
        "open",
        "tsk-parent",
        ["implementation"],
        [],
    )
    child_two = build_issue(
        "tsk-child2",
        "task",
        "in_progress",
        "tsk-parent",
        [],
        [],
    )
    bug_issue = build_issue(
        "tsk-bug01",
        "bug",
        "open",
        "tsk-parent",
        [],
        [],
    )
    story_issue = build_issue(
        "tsk-story01",
        "story",
        "closed",
        None,
        [],
        [],
    )

    for issue in [parent_issue, child_one, child_two, bug_issue, story_issue]:
        write_issue_file(tmp_path, issue)

    index = build_index_from_directory(tmp_path)
    assert len(index.by_id) == 5
    assert {issue.identifier for issue in index.by_status["open"]} == {
        "tsk-parent",
        "tsk-child1",
        "tsk-bug01",
    }
    assert {issue.identifier for issue in index.by_type["task"]} == {
        "tsk-child1",
        "tsk-child2",
    }
    assert {issue.identifier for issue in index.by_parent["tsk-parent"]} == {
        "tsk-child1",
        "tsk-child2",
        "tsk-bug01",
    }


def test_build_index_tracks_reverse_dependencies(tmp_path: Path) -> None:
    """Index should track reverse blocked-by dependencies."""
    blocked_by = DependencyLink(target="tsk-bbb", type="blocked-by")
    blocker = build_issue(
        "tsk-bbb",
        "task",
        "open",
        None,
        [],
        [],
    )
    dependent = build_issue(
        "tsk-aaa",
        "task",
        "open",
        None,
        [],
        [blocked_by],
    )

    for issue in [blocker, dependent]:
        write_issue_file(tmp_path, issue)

    index = build_index_from_directory(tmp_path)
    assert {issue.identifier for issue in index.reverse_dependencies["tsk-bbb"]} == {
        "tsk-aaa"
    }
