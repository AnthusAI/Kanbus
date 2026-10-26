"""Guard against per-issue board reloads in ready, dep add, dep tree and move.

Generates a large board, runs each command through the Python and Rust
command-line interfaces, and fails when a command exceeds its wall-clock
budget. A command that reloads or rescans the board once per issue is
quadratic and exceeds the budget by an order of magnitude, while a command that
reads each issue file once stays far below it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tools" / "perf_baseline.json"
RUST_BINARY = ROOT / "rust" / "target" / "release" / "kbs"
PYTHON_SOURCE = ROOT / "python" / "src"

SOURCE_INDEX = 10
TARGET_INDEX = 500
TREE_INDEX_OFFSET = 1


@dataclass(frozen=True)
class CommandSpecification:
    """A command to time, with an optional untimed command that undoes it."""

    label: str
    arguments: List[str]
    undo_arguments: List[str] | None


def _issue_identifier(index: int) -> str:
    """Build the deterministic identifier for a generated issue.

    :param index: Zero-based issue index.
    :type index: int
    :return: Issue identifier.
    :rtype: str
    """
    return f"kanbus-{index:06d}"


def _write_generated_issues(project_directory: Path, issue_count: int) -> None:
    """Write generated issues, with a blocked-by chain, into the board.

    :param project_directory: Project directory containing the issues folder.
    :type project_directory: Path
    :param issue_count: Number of issues to generate.
    :type issue_count: int
    """
    issues_directory = project_directory / "issues"
    for index in range(issue_count):
        identifier = _issue_identifier(index)
        dependencies = []
        if index % 5 == 1:
            dependencies.append(
                {"target": _issue_identifier(index - 1), "type": "blocked-by"}
            )
        record = {
            "id": identifier,
            "title": f"Generated issue {index}",
            "description": "",
            "type": "task",
            "status": "closed" if index % 7 == 0 else "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": [],
            "dependencies": dependencies,
            "comments": [],
            "created_at": "2026-10-25T22:09:18.985174Z",
            "updated_at": "2026-10-25T22:09:18.985253Z",
            "closed_at": None,
            "right_now_summary": None,
            "right_now_updated_at": None,
            "custom": {},
        }
        (issues_directory / f"{identifier}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )


def _environment() -> Dict[str, str]:
    """Build the process environment shared by all commands.

    :return: Environment variables for subprocesses.
    :rtype: Dict[str, str]
    """
    environment = dict(os.environ)
    environment["KANBUS_DAEMON"] = "0"
    environment["KANBUS_REALTIME_BROKER"] = "off"
    environment["PYTHONPATH"] = str(PYTHON_SOURCE)
    return environment


def _initialize_board(board_root: Path, issue_count: int) -> None:
    """Create a git repository with an initialized, populated board.

    :param board_root: Empty directory to turn into a board.
    :type board_root: Path
    :param issue_count: Number of issues to generate.
    :type issue_count: int
    :raises RuntimeError: If initialization fails.
    """
    environment = _environment()
    for command in (
        ["git", "init", "-q"],
        [sys.executable, "-m", "kanbus.cli", "init"],
    ):
        completed = subprocess.run(
            command,
            cwd=board_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"board setup failed: {' '.join(command)}: {completed.stderr}"
            )
    _write_generated_issues(board_root / "project", issue_count)


def _command_specifications() -> List[CommandSpecification]:
    """List the commands under guard.

    :return: Command specifications.
    :rtype: List[CommandSpecification]
    """
    source = _issue_identifier(SOURCE_INDEX)
    target = _issue_identifier(TARGET_INDEX)
    return [
        CommandSpecification("ready", ["ready"], None),
        CommandSpecification(
            "dep tree",
            ["dep", "tree", _issue_identifier(SOURCE_INDEX + TREE_INDEX_OFFSET)],
            None,
        ),
        CommandSpecification(
            "dep add",
            ["dep", source, "blocked-by", target],
            ["dep", source, "remove", "blocked-by", target],
        ),
        CommandSpecification(
            "move (update --type)",
            ["move", source, "bug"],
            ["move", source, "task"],
        ),
    ]


def _runtime_commands() -> Dict[str, List[str]]:
    """Return the base command line for each runtime.

    :return: Mapping of runtime name to command prefix.
    :rtype: Dict[str, List[str]]
    :raises RuntimeError: If the Rust binary has not been built.
    """
    if not RUST_BINARY.is_file():
        raise RuntimeError(
            f"missing {RUST_BINARY}; run 'cargo build --release --bin kbs' in rust/"
        )
    return {
        "python": [sys.executable, "-m", "kanbus.cli"],
        "rust": [str(RUST_BINARY)],
    }


def _run_timed(
    command: List[str], board_root: Path, maximum_seconds: float
) -> tuple[float, str]:
    """Run one command and return its elapsed time and standard output.

    :param command: Full command line.
    :type command: List[str]
    :param board_root: Working directory.
    :type board_root: Path
    :param maximum_seconds: Kill the command after this many seconds.
    :type maximum_seconds: float
    :return: Elapsed seconds and standard output.
    :rtype: tuple[float, str]
    :raises RuntimeError: If the command fails.
    :raises subprocess.TimeoutExpired: If the budget is exceeded.
    """
    started = perf_counter()
    completed = subprocess.run(
        command,
        cwd=board_root,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=maximum_seconds,
        check=False,
    )
    elapsed = perf_counter() - started
    if completed.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} exited {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return elapsed, completed.stdout


def main() -> int:
    """Run the guard and report per-command timings.

    :return: Exit code 0 when every command is within budget, 1 otherwise.
    :rtype: int
    """
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["board_load"]
    issue_count = int(baseline["issue_count"])
    budgets: Dict[str, Dict[str, float]] = baseline["max_seconds"]
    runtimes = _runtime_commands()

    scratch = Path(tempfile.mkdtemp(prefix="kanbus-board-load-"))
    failures: List[str] = []
    timings: Dict[str, Dict[str, float]] = {name: {} for name in runtimes}
    outputs: Dict[str, Dict[str, str]] = {name: {} for name in runtimes}
    try:
        _initialize_board(scratch, issue_count)
        for runtime_name, prefix in runtimes.items():
            for specification in _command_specifications():
                budget = float(budgets[runtime_name][specification.label])
                try:
                    elapsed, output = _run_timed(
                        [*prefix, *specification.arguments], scratch, budget
                    )
                except subprocess.TimeoutExpired:
                    failures.append(
                        f"{runtime_name} {specification.label} exceeded "
                        f"{budget:.1f}s on {issue_count} issues"
                    )
                    continue
                timings[runtime_name][specification.label] = round(elapsed, 3)
                outputs[runtime_name][specification.label] = output
                if specification.undo_arguments is not None:
                    _run_timed([*prefix, *specification.undo_arguments], scratch, 600)
        for label in outputs["python"]:
            if label.startswith("move") or label == "dep add":
                continue
            if outputs["python"][label] != outputs["rust"].get(label):
                failures.append(f"{label} output differs between runtimes")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    summary = {
        "issue_count": issue_count,
        "timings_seconds": timings,
        "status": "ok" if not failures else "failed",
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
