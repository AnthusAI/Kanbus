#!/usr/bin/env python3
"""Smoke-test the Rust Taskulus binary in a temp repository."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


@dataclass(frozen=True)
class CommandResult:
    """Result of a subprocess command."""

    command: list[str]
    return_code: int
    stdout: str
    stderr: str


def run_command(command: list[str], cwd: Path | None = None) -> CommandResult:
    """Run a subprocess command and capture output.

    :param command: Command and arguments to execute.
    :type command: list[str]
    :param cwd: Working directory for the command.
    :type cwd: Path | None
    :return: Command result with stdout/stderr and return code.
    :rtype: CommandResult
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=command,
        return_code=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


def ensure_success(result: CommandResult, label: str) -> None:
    """Ensure the command succeeded or raise an error.

    :param result: Command result.
    :type result: CommandResult
    :param label: Human-readable label for the command.
    :type label: str
    :raises RuntimeError: If the command failed.
    """
    if result.return_code != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{label} failed: {details}")


def verify_binary(binary: Path) -> None:
    """Verify the Taskulus binary in a temp git repository.

    :param binary: Path to the Taskulus binary.
    :type binary: Path
    :return: None.
    :rtype: None
    """
    if not binary.exists():
        raise RuntimeError("binary not found")

    with TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir(parents=True)
        ensure_success(run_command(["git", "init"], cwd=repo_dir), "git init")
        ensure_success(run_command([str(binary), "init"], cwd=repo_dir), "tsk init")
        ensure_success(run_command([str(binary), "doctor"], cwd=repo_dir), "tsk doctor")


def main(argv: list[str]) -> int:
    """Run binary verification.

    :param argv: Command-line arguments.
    :type argv: list[str]
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Verify Taskulus Rust binary")
    parser.add_argument("--binary", help="Path to the Taskulus binary")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    binary = Path(args.binary) if args.binary else repo_root / "rust" / "target" / "release" / "taskulus"
    try:
        verify_binary(binary)
    except RuntimeError as error:
        print(str(error))
        return 1
    print("Rust binary check succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
