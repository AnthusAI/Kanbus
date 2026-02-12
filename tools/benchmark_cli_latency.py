"""Benchmark end-to-end CLI latency including process startup."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from taskulus.project import discover_project_directories
from benchmark_discovery_fixtures import FixturePlan, generate_multi_project, generate_single_project


@dataclass(frozen=True)
class TimingSummary:
    """Summary statistics for timing measurements."""

    runs: int
    min_ms: float
    median_ms: float
    max_ms: float


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark end-to-end CLI latency including process startup."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "tools" / "tmp" / "benchmark-cli-latency",
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
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of timed runs per scenario.",
    )
    parser.add_argument(
        "--python-executable",
        type=str,
        default=sys.executable,
        help="Python executable used to run the CLI.",
    )
    parser.add_argument(
        "--rust-binary",
        type=Path,
        default=ROOT / "rust" / "target" / "release" / "taskulus",
        help="Path to the Rust CLI binary.",
    )
    return parser.parse_args(list(argv))


def _remove_caches(root: Path) -> None:
    project_dirs = discover_project_directories(root)
    for project_dir in project_dirs:
        cache_dir = project_dir / ".cache"
        if cache_dir.exists():
            for entry in cache_dir.glob("*"):
                entry.unlink()
            cache_dir.rmdir()


def _write_dotfile(root: Path) -> None:
    project_dirs = discover_project_directories(root)
    if not project_dirs:
        return
    lines = []
    for project_dir in project_dirs:
        try:
            lines.append(str(project_dir.relative_to(root)))
        except ValueError:
            lines.append(str(project_dir))
    (root / ".taskulus").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_timed_command(command: list[str], cwd: Path, env: dict[str, str]) -> float:
    start = perf_counter()
    subprocess.run(command, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return (perf_counter() - start) * 1000.0


def _measure_cli(
    command: list[str], cwd: Path, env: dict[str, str], iterations: int
) -> TimingSummary:
    timings = []
    for _ in range(iterations):
        _remove_caches(cwd)
        timings.append(_run_timed_command(command, cwd, env))
    timings.sort()
    return TimingSummary(
        runs=len(timings),
        min_ms=timings[0],
        median_ms=statistics.median(timings),
        max_ms=timings[-1],
    )


def _ensure_rust_binary(path: Path) -> None:
    if path.exists():
        return
    raise RuntimeError(
        f"Rust CLI binary not found at {path}. "
        "Build it with `cargo build --release --manifest-path rust/Cargo.toml`."
    )


def main(argv: Iterable[str]) -> int:
    """Run end-to-end CLI latency benchmarks.

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

    _write_dotfile(single_root)
    _write_dotfile(multi_root)

    _ensure_rust_binary(args.rust_binary)

    env = os.environ.copy()
    env.setdefault("TASKULUS_NO_DAEMON", "1")
    env.setdefault("PYTHONPATH", str(PYTHON_SRC))

    python_base = [args.python_executable, "-m", "taskulus.cli"]
    rust_base = [str(args.rust_binary)]

    python_single_list = _measure_cli(python_base + ["list"], single_root, env, args.iterations)
    python_single_ready = _measure_cli(python_base + ["ready"], single_root, env, args.iterations)
    python_multi_list = _measure_cli(python_base + ["list"], multi_root, env, args.iterations)
    python_multi_ready = _measure_cli(python_base + ["ready"], multi_root, env, args.iterations)

    rust_single_list = _measure_cli(rust_base + ["list"], single_root, env, args.iterations)
    rust_single_ready = _measure_cli(rust_base + ["ready"], single_root, env, args.iterations)
    rust_multi_list = _measure_cli(rust_base + ["list"], multi_root, env, args.iterations)
    rust_multi_ready = _measure_cli(rust_base + ["ready"], multi_root, env, args.iterations)

    payload = {
        "fixtures_root": str(root),
        "projects": plan.projects,
        "issues_per_project": plan.issues_per_project,
        "iterations": args.iterations,
        "python": {
            "single": {"list": python_single_list.__dict__, "ready": python_single_ready.__dict__},
            "multi": {"list": python_multi_list.__dict__, "ready": python_multi_ready.__dict__},
        },
        "rust": {
            "single": {"list": rust_single_list.__dict__, "ready": rust_single_ready.__dict__},
            "multi": {"list": rust_multi_list.__dict__, "ready": rust_multi_ready.__dict__},
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
