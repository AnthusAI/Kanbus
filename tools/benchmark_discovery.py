"""Benchmark recursive project discovery and listing operations."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterable
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from taskulus.project import discover_project_directories
from taskulus.issue_files import read_issue_from_file
from taskulus.issue_listing import list_issues
from taskulus.dependencies import list_ready_issues
from taskulus.models import IssueData

from benchmark_discovery_fixtures import FixturePlan, generate_multi_project, generate_single_project

os.environ.setdefault("TASKULUS_NO_DAEMON", "1")


@dataclass(frozen=True)
class ScenarioResult:
    """Timing metrics for a benchmark scenario."""

    discover_ms: float
    list_ms: float
    ready_ms: float
    project_count: int
    issue_count: int


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    :param argv: Raw argument list.
    :type argv: Iterable[str]
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description="Benchmark recursive project discovery and listing operations."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "tools" / "tmp" / "benchmark-discovery-fixtures",
        help="Fixture root directory.",
    )
    parser.add_argument(
        "--projects",
        type=int,
        default=10,
        help="Number of projects in the multi-project scenario.",
    )
    parser.add_argument(
        "--issues-per-project",
        type=int,
        default=200,
        help="Issues per project.",
    )
    return parser.parse_args(list(argv))


def _remove_cache(project_dir: Path) -> None:
    """Remove cache files for a single project directory.

    :param project_dir: Project directory containing a .cache folder.
    :type project_dir: Path
    :return: None.
    :rtype: None
    """
    cache_dir = project_dir / ".cache"
    if cache_dir.exists():
        for entry in cache_dir.glob("*"):
            entry.unlink()
        cache_dir.rmdir()


def _remove_caches(project_dirs: Iterable[Path]) -> None:
    """Remove cache files for multiple project directories.

    :param project_dirs: Iterable of project directories.
    :type project_dirs: Iterable[Path]
    :return: None.
    :rtype: None
    """
    for project_dir in project_dirs:
        _remove_cache(project_dir)


def _time_call(callable_fn) -> float:
    """Measure execution time of a callable.

    :param callable_fn: Callable to invoke.
    :type callable_fn: Callable[[], Any]
    :return: Elapsed time in milliseconds.
    :rtype: float
    """
    start = perf_counter()
    callable_fn()
    return (perf_counter() - start) * 1000.0


def _benchmark_scenario(root: Path) -> ScenarioResult:
    """Run serial discovery/list/ready benchmarks for a fixture root.

    :param root: Fixture root to scan.
    :type root: Path
    :return: Scenario timing metrics.
    :rtype: ScenarioResult
    """
    discover_ms = _time_call(lambda: discover_project_directories(root))
    project_dirs = discover_project_directories(root)
    _remove_caches(project_dirs)

    list_ms = _time_call(lambda: list_issues(root))
    ready_ms = _time_call(lambda: list_ready_issues(root))

    issues = list_issues(root)
    return ScenarioResult(
        discover_ms=discover_ms,
        list_ms=list_ms,
        ready_ms=ready_ms,
        project_count=len(project_dirs),
        issue_count=len(issues),
    )


def _blocked_by_dependency(issue: IssueData) -> bool:
    """Return whether the issue is blocked by any dependency.

    :param issue: Issue data to inspect.
    :type issue: IssueData
    :return: True if blocked-by dependency exists.
    :rtype: bool
    """
    return any(
        dependency.dependency_type == "blocked-by" for dependency in issue.dependencies
    )


def _load_issues_for_project(project_dir: Path) -> list[IssueData]:
    """Load all issues for a single project directory.

    :param project_dir: Project directory containing issues.
    :type project_dir: Path
    :return: List of issues.
    :rtype: list[IssueData]
    """
    issues_dir = project_dir / "issues"
    issues = []
    for path in sorted(issues_dir.glob("*.json"), key=lambda item: item.name):
        issues.append(read_issue_from_file(path))
    return issues


def _parallel_load(project_dirs: list[Path]) -> list[IssueData]:
    """Load issues for multiple projects in parallel.

    :param project_dirs: Project directories to load.
    :type project_dirs: list[Path]
    :return: Flattened list of issues.
    :rtype: list[IssueData]
    """
    if not project_dirs:
        return []
    from concurrent.futures import ThreadPoolExecutor

    max_workers = min(32, len(project_dirs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_load_issues_for_project, project_dirs))
    return [issue for batch in results for issue in batch]


def _benchmark_parallel(root: Path) -> ScenarioResult:
    """Run parallel discovery/list/ready benchmarks for a fixture root.

    :param root: Fixture root to scan.
    :type root: Path
    :return: Scenario timing metrics.
    :rtype: ScenarioResult
    """
    discover_ms = _time_call(lambda: discover_project_directories(root))
    project_dirs = discover_project_directories(root)
    _remove_caches(project_dirs)

    list_ms = _time_call(lambda: _parallel_load(project_dirs))
    ready_ms = _time_call(
        lambda: [
            issue
            for issue in _parallel_load(project_dirs)
            if issue.status != "closed" and not _blocked_by_dependency(issue)
        ]
    )
    issues = _parallel_load(project_dirs)
    return ScenarioResult(
        discover_ms=discover_ms,
        list_ms=list_ms,
        ready_ms=ready_ms,
        project_count=len(project_dirs),
        issue_count=len(issues),
    )


def main(argv: Iterable[str]) -> int:
    """Run discovery benchmarks.

    :param argv: Command-line arguments.
    :type argv: Iterable[str]
    :return: Exit code.
    :rtype: int
    """
    args = _parse_args(argv)
    plan = FixturePlan(projects=args.projects, issues_per_project=args.issues_per_project)

    root = args.root
    single_root = generate_single_project(root, plan).parent
    multi_root = generate_multi_project(root, plan)

    single_result = _benchmark_scenario(single_root)
    multi_result = _benchmark_scenario(multi_root)
    single_parallel = _benchmark_parallel(single_root)
    multi_parallel = _benchmark_parallel(multi_root)

    payload = {
        "fixtures_root": str(root),
        "projects": plan.projects,
        "issues_per_project": plan.issues_per_project,
        "serial": {
            "single": single_result.__dict__,
            "multi": multi_result.__dict__,
        },
        "parallel": {
            "single": single_parallel.__dict__,
            "multi": multi_parallel.__dict__,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
