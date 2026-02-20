#!/usr/bin/env python3
"""Build Kanbus Rust release binaries for the current platform."""

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
    cwd: Path | None


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
        cwd=cwd,
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
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        parts = [
            f"{label} failed.",
            f"Command: {' '.join(result.command)}",
        ]
        if result.cwd is not None:
            parts.append(f"Working directory: {result.cwd}")
        parts.append(f"Exit code: {result.return_code}")
        if stdout:
            parts.append("Stdout:")
            parts.append(stdout)
        if stderr:
            parts.append("Stderr:")
            parts.append(stderr)
        if not stdout and not stderr:
            parts.append("No stdout/stderr output captured.")
        raise RuntimeError("\n".join(parts))


def build_release(repo_root: Path, target: str | None) -> Path:
    """Build the release binary.

    :param repo_root: Repository root path.
    :type repo_root: Path
    :param target: Optional cargo target triple.
    :type target: str | None
    :return: Path to the release binary.
    :rtype: Path
    """
    rust_dir = repo_root / "rust"
    command = ["cargo", "build", "--release"]
    if target:
        command.extend(["--target", target])
    ensure_success(run_command(command, cwd=rust_dir), "cargo build --release")

    target_dir = rust_dir / "target"
    if target:
        target_dir = target_dir / target
    binary = target_dir / "release" / "kbs"
    if sys.platform.startswith("win"):
        binary = binary.with_suffix(".exe")
    if not binary.exists():
        raise RuntimeError("release binary not found")
    return binary


def main(argv: list[str]) -> int:
    """Run the release build.

    :param argv: Command-line arguments.
    :type argv: list[str]
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Build Kanbus Rust release binary")
    parser.add_argument(
        "--target",
        help="Optional cargo target triple for cross-compilation.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    try:
        binary = build_release(repo_root, args.target)
    except RuntimeError as error:
        print(str(error))
        return 1
    print(str(binary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
