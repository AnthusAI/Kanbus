from __future__ import annotations

import json
from pathlib import Path

from kanbus import cache, index
from kanbus.models import DependencyLink

from test_helpers import build_issue


def _write_issue(path: Path, issue_id: str, **kwargs: object) -> None:
    issue = build_issue(issue_id, **kwargs)
    path.write_text(
        json.dumps(issue.model_dump(by_alias=True, mode="json")), encoding="utf-8"
    )


def test_load_issue_data_and_batch(tmp_path: Path) -> None:
    issue_path = tmp_path / "kanbus-1.json"
    _write_issue(issue_path, "kanbus-1", issue_type="bug")

    loaded = index._load_issue_data(issue_path)
    batched = index._load_issue_batch([issue_path])

    assert loaded.identifier == "kanbus-1"
    assert batched[0].issue_type == "bug"


def test_add_issue_to_index_indexes_all_dimensions() -> None:
    issue = build_issue(
        "kanbus-1",
        issue_type="task",
        status="open",
        parent="kanbus-parent",
        labels=["backend"],
    )
    issue = issue.model_copy(
        update={
            "dependencies": [
                DependencyLink.model_validate(
                    {"target": "kanbus-base", "type": "blocked-by"}
                )
            ]
        }
    )
    issue_index = index.IssueIndex()

    index._add_issue_to_index(issue_index, issue)

    assert issue_index.by_id["kanbus-1"].identifier == "kanbus-1"
    assert issue_index.by_status["open"][0].identifier == "kanbus-1"
    assert issue_index.by_type["task"][0].identifier == "kanbus-1"
    assert issue_index.by_parent["kanbus-parent"][0].identifier == "kanbus-1"
    assert issue_index.by_label["backend"][0].identifier == "kanbus-1"
    assert issue_index.reverse_dependencies["kanbus-base"][0].identifier == "kanbus-1"


def test_build_index_from_directory_filters_and_loads(tmp_path: Path) -> None:
    _write_issue(tmp_path / "kanbus-2.json", "kanbus-2", issue_type="bug", status="closed")
    _write_issue(tmp_path / "kanbus-1.json", "kanbus-1", issue_type="task", status="open")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    issue_index = index.build_index_from_directory(tmp_path)

    assert set(issue_index.by_id.keys()) == {"kanbus-1", "kanbus-2"}
    assert [i.identifier for i in issue_index.by_status["open"]] == ["kanbus-1"]
    assert [i.identifier for i in issue_index.by_type["bug"]] == ["kanbus-2"]


def test_collect_issue_file_mtimes_ignores_non_json(tmp_path: Path) -> None:
    json_path = tmp_path / "kanbus-1.json"
    json_path.write_text("{}", encoding="utf-8")
    (tmp_path / "ignore.md").write_text("x", encoding="utf-8")

    mtimes = cache.collect_issue_file_mtimes(tmp_path)
    assert set(mtimes.keys()) == {"kanbus-1.json"}


def test_normalize_mtime_rounds_to_microseconds() -> None:
    assert cache._normalize_mtime(1.12345678) == 1.123457


def test_load_cache_if_valid_missing_or_stale(tmp_path: Path) -> None:
    cache_path = tmp_path / "index.json"

    assert cache.load_cache_if_valid(cache_path, tmp_path) is None

    cache_path.write_text(
        json.dumps({"file_mtimes": {"kanbus-1.json": 1.0}, "issues": []}),
        encoding="utf-8",
    )
    assert cache.load_cache_if_valid(cache_path, tmp_path) is None


def test_write_cache_and_reload(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()

    issue = build_issue("kanbus-1", status="open", issue_type="task", labels=["l1"])
    issue_index = index.IssueIndex(
        by_id={issue.identifier: issue},
        by_status={"open": [issue]},
        by_type={"task": [issue]},
        by_label={"l1": [issue]},
        reverse_dependencies={"kanbus-x": [issue]},
    )
    mtimes = {"kanbus-1.json": 123.456789}
    cache_path = tmp_path / ".cache" / "index.json"

    cache.write_cache(issue_index, cache_path, mtimes)
    loaded = cache.load_cache_if_valid(cache_path, issues_dir)

    assert loaded is None

    issue_file = issues_dir / "kanbus-1.json"
    issue_file.write_text(
        json.dumps(issue.model_dump(by_alias=True, mode="json")), encoding="utf-8"
    )
    current_mtimes = cache.collect_issue_file_mtimes(issues_dir)
    cache.write_cache(issue_index, cache_path, current_mtimes)

    loaded = cache.load_cache_if_valid(cache_path, issues_dir)
    assert loaded is not None
    assert loaded.by_id["kanbus-1"].identifier == "kanbus-1"
    assert loaded.reverse_dependencies["kanbus-x"][0].identifier == "kanbus-1"


def test_build_index_from_cache_ignores_unknown_reverse_dependency_ids() -> None:
    issue = build_issue("kanbus-1", issue_type="task", status="open", parent="kanbus-0")

    rebuilt = cache.build_index_from_cache(
        [issue], {"kanbus-x": ["kanbus-1", "missing-id"]}
    )

    assert rebuilt.by_id["kanbus-1"].identifier == "kanbus-1"
    assert rebuilt.by_parent["kanbus-0"][0].identifier == "kanbus-1"
    assert [item.identifier for item in rebuilt.reverse_dependencies["kanbus-x"]] == [
        "kanbus-1"
    ]
