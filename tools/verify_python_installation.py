#!/usr/bin/env python3
"""Verify Kanbus Python installation in a clean virtual environment."""

from __future__ import annotations

import argparse
import os
import shutil
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


def run_command(command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
    """Run a subprocess command and capture output.

    :param command: Command and arguments to execute.
    :type command: list[str]
    :param cwd: Working directory for the command.
    :type cwd: Path | None
    :param env: Environment variables for the command.
    :type env: dict[str, str] | None
    :return: Command result with stdout/stderr and return code.
    :rtype: CommandResult
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
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


def locate_venv_python(venv_dir: Path) -> Path:
    """Locate the Python executable inside a virtual environment.

    :param venv_dir: Path to the virtual environment.
    :type venv_dir: Path
    :return: Path to the venv Python interpreter.
    :rtype: Path
    :raises RuntimeError: If the interpreter cannot be found.
    """
    candidates = [
        venv_dir / "bin" / "python",
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "Scripts" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("virtual environment python not found")


def locate_venv_tsk(venv_dir: Path) -> Path | None:
    """Locate the Kanbus CLI script inside a virtual environment.

    :param venv_dir: Path to the virtual environment.
    :type venv_dir: Path
    :return: Path to the CLI script if found, otherwise None.
    :rtype: Path | None
    """
    candidates = [
        venv_dir / "bin" / "kanbus",
        venv_dir / "Scripts" / "kanbus.exe",
        venv_dir / "Scripts" / "kanbus",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


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


def verify_installation(repo_root: Path, keep_venv: bool, base_python: str) -> None:
    """Verify Kanbus installation via pip in an isolated venv.

    :param repo_root: Path to the repository root.
    :type repo_root: Path
    :param keep_venv: Whether to keep the temporary virtualenv directory.
    :type keep_venv: bool
    :return: None.
    :rtype: None
    """
    python_package = repo_root / "python"
    if not python_package.is_dir():
        raise RuntimeError("python package directory not found")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        venv_dir = temp_path / "venv"
        run_command([base_python, "-m", "venv", str(venv_dir)])
        venv_python = locate_venv_python(venv_dir)

        ensure_success(
            run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"]),
            "pip upgrade",
        )
        ensure_success(
            run_command(
                [str(venv_python), "-m", "pip", "install", "-e", str(python_package)]
            ),
            "pip install",
        )

        tsk_path = locate_venv_tsk(venv_dir)
        if tsk_path is None:
            raise RuntimeError("kanbus script not found in virtual environment")

        env = os.environ.copy()
        env["PATH"] = f"{tsk_path.parent}{os.pathsep}{env.get('PATH', '')}"

        ensure_success(
            run_command([str(tsk_path), "--version"], env=env),
            "kanbus --version",
        )

        repo_dir = temp_path / "repo"
        repo_dir.mkdir()
        ensure_success(run_command(["git", "init"], cwd=repo_dir), "git init")

        ensure_success(run_command([str(tsk_path), "init"], cwd=repo_dir, env=env), "kanbus init")
        ensure_success(
            run_command([str(tsk_path), "doctor"], cwd=repo_dir, env=env),
            "kanbus doctor",
        )

        if keep_venv:
            preserved = repo_root / "tools" / "tmp" / "venv-install-check"
            preserved.parent.mkdir(parents=True, exist_ok=True)
            if preserved.exists():
                shutil.rmtree(preserved)
            shutil.copytree(venv_dir, preserved)


def _python_meets_requirement(python_executable: str) -> bool:
    result = run_command(
        [python_executable, "-c", "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")"]
    )
    if result.return_code != 0:
        return False
    version = result.stdout.strip().splitlines()[-1]
    try:
        major, minor = (int(value) for value in version.split(".", maxsplit=1))
    except ValueError:
        return False
    return (major, minor) >= (3, 11)


def _select_base_python(candidate: str | None) -> str:
    if candidate and _python_meets_requirement(candidate):
        return candidate
    if _python_meets_requirement(sys.executable):
        return sys.executable
    fallback = shutil.which("python3.11")
    if fallback and _python_meets_requirement(fallback):
        return fallback
    raise RuntimeError("Python 3.11+ is required for installation verification")


def main(argv: list[str]) -> int:
    """Run installation verification.

    :param argv: Command-line arguments.
    :type argv: list[str]
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Verify Kanbus Python installation")
    parser.add_argument(
        "--keep-venv",
        action="store_true",
        help="Keep the virtual environment under tools/tmp/venv-install-check.",
    )
    parser.add_argument(
        "--python",
        help="Path to a Python 3.11+ interpreter to create the virtual environment.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    try:
        base_python = _select_base_python(args.python)
        verify_installation(repo_root, args.keep_venv, base_python)
    except RuntimeError as error:
        print(str(error))
        return 1
    print("Python installation check succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
