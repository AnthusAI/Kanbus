"""Benchmark index build and cache load performance."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from kanbus.cache import collect_issue_file_mtimes, load_cache_if_valid, write_cache
from kanbus.index import IssueIndex, build_index_from_directory
from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.models import DependencyLink, IssueData

ISSUE_COUNT = 1000
PYTHON_INDEX_BUILD_TARGET_MS = 50.0
PYTHON_CACHE_LOAD_TARGET_MS = 50.0


def create_issue(identifier: str, now: datetime) -> IssueData:
    """Create an IssueData instance for benchmarking.

    :param identifier: Issue identifier to use.
    :type identifier: str
    :param now: Timestamp to set for created and updated fields.
    :type now: datetime
    :return: Populated issue data.
    :rtype: IssueData
    """
    dependencies = []
    if identifier.endswith("0"):
        dependencies = [DependencyLink(target="kanbus-000001", type="blocked-by")]
    return IssueData(
        id=identifier,
        title=f"Benchmark issue {identifier}",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=["benchmark"],
        dependencies=dependencies,
        comments=[],
        description="",
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )


def generate_issues(issues_directory: Path, identifiers: Iterable[str]) -> None:
    """Generate issue JSON files for benchmarking.

    :param issues_directory: Directory to write issue files into.
    :type issues_directory: Path
    :param identifiers: Issue identifiers to write.
    :type identifiers: Iterable[str]
    :return: None.
    :rtype: None
    """
    now = datetime.now(timezone.utc)
    issues_directory.mkdir(parents=True, exist_ok=True)
    for identifier in identifiers:
        issue = create_issue(identifier, now)
        write_issue_to_file(issue, issues_directory / f"{identifier}.json")


def _build_index_parallel(issues_directory: Path) -> IssueIndex:
    issue_paths = [
        path for path in issues_directory.glob("*.json") if path.is_file()
    ]
    issue_paths.sort(key=lambda path: path.name)
    max_workers = min(32, len(issue_paths)) or 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        issues = list(executor.map(read_issue_from_file, issue_paths))
    index = IssueIndex()
    for issue in issues:
        index.by_id[issue.identifier] = issue
        index.by_status.setdefault(issue.status, []).append(issue)
        index.by_type.setdefault(issue.issue_type, []).append(issue)
        if issue.parent is not None:
            index.by_parent.setdefault(issue.parent, []).append(issue)
        for label in issue.labels:
            index.by_label.setdefault(label, []).append(issue)
        for dependency in issue.dependencies:
            if dependency.dependency_type == "blocked-by":
                index.reverse_dependencies.setdefault(dependency.target, []).append(issue)
    return index


def _run_serial_benchmark(issues_directory: Path, cache_path: Path) -> dict[str, float]:
    start = perf_counter()
    index = build_index_from_directory(issues_directory)
    build_seconds = perf_counter() - start
    build_ms = build_seconds * 1000.0

    mtimes = collect_issue_file_mtimes(issues_directory)
    write_cache(index, cache_path, mtimes)

    start = perf_counter()
    cached = load_cache_if_valid(cache_path, issues_directory)
    cache_seconds = perf_counter() - start
    cache_ms = cache_seconds * 1000.0

    if cached is None:
        raise RuntimeError("cache did not load")

    return {"build_ms": build_ms, "cache_load_ms": cache_ms}


def _run_parallel_benchmark(issues_directory: Path, cache_path: Path) -> dict[str, float]:
    start = perf_counter()
    index = _build_index_parallel(issues_directory)
    build_seconds = perf_counter() - start
    build_ms = build_seconds * 1000.0

    mtimes = collect_issue_file_mtimes(issues_directory)
    write_cache(index, cache_path, mtimes)

    start = perf_counter()
    cached = load_cache_if_valid(cache_path, issues_directory)
    cache_seconds = perf_counter() - start
    cache_ms = cache_seconds * 1000.0

    if cached is None:
        raise RuntimeError("cache did not load")

    return {"build_ms": build_ms, "cache_load_ms": cache_ms}


def run_benchmark() -> None:
    """Run index build and cache load benchmarks.

    :return: None.
    :rtype: None
    """
    temp_root = Path(Path.cwd() / "tools" / "tmp" / f"index-benchmark-{uuid4().hex}")
    issues_directory = temp_root / "project" / "issues"
    cache_path = temp_root / "project" / ".cache" / "index.json"

    identifiers = [f"kanbus-{i:06d}" for i in range(ISSUE_COUNT)]
    generate_issues(issues_directory, identifiers)

    serial_results = _run_serial_benchmark(issues_directory, cache_path)
    parallel_results = _run_parallel_benchmark(issues_directory, cache_path)

    results = {
        "issue_count": ISSUE_COUNT,
        "build_ms": serial_results["build_ms"],
        "cache_load_ms": serial_results["cache_load_ms"],
        "parallel": {
            "build_ms": parallel_results["build_ms"],
            "cache_load_ms": parallel_results["cache_load_ms"],
        },
        "build_target_ms": PYTHON_INDEX_BUILD_TARGET_MS,
        "cache_load_target_ms": PYTHON_CACHE_LOAD_TARGET_MS,
    }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    run_benchmark()
