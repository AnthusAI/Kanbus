#!/usr/bin/env python3
"""Run installation verification for Python and Rust."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


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
    :param cwd: Path | None
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


def main(argv: list[str]) -> int:
    """Run installation checks.

    :param argv: Command-line arguments.
    :type argv: list[str]
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Verify Taskulus installation suite")
    parser.add_argument(
        "--python",
        help="Path to a Python 3.11+ interpreter for install verification.",
    )
    parser.add_argument(
        "--skip-python",
        action="store_true",
        help="Skip Python installation verification.",
    )
    parser.add_argument(
        "--skip-rust",
        action="store_true",
        help="Skip Rust release build and binary verification.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    tools_dir = repo_root / "tools"

    try:
        if not args.skip_rust:
            build_result = run_command(
                [sys.executable, str(tools_dir / "build_rust_release.py")]
            )
            ensure_success(build_result, "rust release build")
            binary_path = build_result.stdout.strip().splitlines()[-1]
            ensure_success(
                run_command(
                    [
                        sys.executable,
                        str(tools_dir / "verify_rust_binary.py"),
                        "--binary",
                        binary_path,
                    ]
                ),
                "rust binary verification",
            )
        if not args.skip_python:
            command = [sys.executable, str(tools_dir / "verify_python_installation.py")]
            if args.python:
                command.extend(["--python", args.python])
            ensure_success(run_command(command), "python installation verification")
    except RuntimeError as error:
        print(str(error))
        return 1
    print("Installation suite check succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
