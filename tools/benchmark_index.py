"""Benchmark Virtuus resident issue-table performance."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from kanbus.models import DependencyLink, IssueData
from virtuus import Table

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


def generate_issues(identifiers: Iterable[str]) -> list[dict[str, object]]:
    """Generate issue JSON files for benchmarking.

    :param issues_directory: Directory to write issue files into.
    :type issues_directory: Path
    :param identifiers: Issue identifiers to write.
    :type identifiers: Iterable[str]
    :return: None.
    :rtype: None
    """
    now = datetime.now(timezone.utc)
    return [create_issue(identifier, now).model_dump(by_alias=True, mode="json") for identifier in identifiers]


def _run_serial_benchmark(records: list[dict[str, object]]) -> dict[str, float]:
    start = perf_counter()
    table = Table("issues", primary_key="id", storage="memory")
    table.add_gsi("by_status", "status")
    table.bulk_load(records)
    build_seconds = perf_counter() - start
    build_ms = build_seconds * 1000.0

    start = perf_counter()
    cached = table.scan()
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
    identifiers = [f"kanbus-{i:06d}" for i in range(ISSUE_COUNT)]
    records = generate_issues(identifiers)

    serial_results = _run_serial_benchmark(records)

    results = {
        "issue_count": ISSUE_COUNT,
        "build_ms": serial_results["build_ms"],
        "cache_load_ms": serial_results["cache_load_ms"],
        "parallel": serial_results,
        "build_target_ms": PYTHON_INDEX_BUILD_TARGET_MS,
        "cache_load_target_ms": PYTHON_CACHE_LOAD_TARGET_MS,
    }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    run_benchmark()
