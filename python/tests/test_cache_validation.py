"""Additional cache validation tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from taskulus.cache import (
    build_index_from_cache,
    collect_issue_file_mtimes,
    load_cache_if_valid,
)
from taskulus.models import IssueData


def _make_issue(identifier: str) -> IssueData:
    now = datetime.now(timezone.utc)
    return IssueData(
        id=identifier,
        title="Test",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        description="",
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )


def test_collect_issue_file_mtimes_ignores_non_json(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("noop", encoding="utf-8")
    mtimes = collect_issue_file_mtimes(tmp_path)
    assert mtimes == {}


def test_load_cache_if_valid_missing_cache_returns_none(tmp_path: Path) -> None:
    assert load_cache_if_valid(tmp_path / "missing.json", tmp_path) is None


def test_load_cache_if_valid_rejects_mismatch(tmp_path: Path) -> None:
    cache_path = tmp_path / "index.json"
    cache_path.write_text(
        json.dumps({"file_mtimes": {"a.json": 1.0}}), encoding="utf-8"
    )

    assert load_cache_if_valid(cache_path, tmp_path) is None


def test_build_index_from_cache_skips_missing_ids() -> None:
    issue = _make_issue("tsk-001")
    issue_with_parent = issue.model_copy(
        update={"parent": "tsk-parent", "labels": ["a"]}
    )
    index = build_index_from_cache([issue_with_parent], {"tsk-002": ["tsk-missing"]})
    assert index.by_parent["tsk-parent"][0].identifier == "tsk-001"
    assert index.by_label["a"][0].identifier == "tsk-001"
    assert index.reverse_dependencies["tsk-002"] == []
