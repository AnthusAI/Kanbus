"""Shared helpers for Behave step definitions."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

from click.testing import CliRunner

from kanbus.cli import cli
from kanbus.models import IssueData
from kanbus.project import load_project_directory as resolve_project_directory


def run_cli_args(context: object, args: list[str]) -> None:
    """Run the Kanbus CLI with an explicit list of arguments.

    Unlike run_cli, this does not shell-parse the args, so embedded newlines
    and special characters are preserved exactly as given.

    :param context: Behave context object.
    :type context: object
    :param args: List of CLI arguments (excluding the program name).
    :type args: list[str]
    """
    runner = CliRunner()

    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")

    previous = Path.cwd()
    environment = os.environ.copy()
    overrides = getattr(context, "environment_overrides", None)
    if overrides:
        environment.update(overrides)
    try:
        os.chdir(working_directory)
    except (FileNotFoundError, PermissionError) as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    try:
        result = runner.invoke(cli, args, env=environment)
        stdout = None
        stderr = None
        try:
            stdout = result.stdout
        except (AttributeError, ValueError):
            stdout = None
        try:
            stderr = result.stderr
        except (AttributeError, ValueError):
            stderr = None
        if stdout is None:
            stdout = result.output
        if stderr is None:
            stderr = ""
        if result.exit_code != 0:
            stderr = result.output
        context.result = SimpleNamespace(
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            output=result.output,
        )
    finally:
        os.chdir(previous)


def run_cli(context: object, command: str) -> None:
    """Run the Kanbus CLI in the scenario working directory.

    :param context: Behave context object.
    :type context: object
    :param command: Full command string.
    :type command: str
    """
    runner = CliRunner()
    args = shlex.split(command)[1:]

    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")

    previous = Path.cwd()
    environment = os.environ.copy()
    overrides = getattr(context, "environment_overrides", None)
    if overrides:
        environment.update(overrides)
    try:
        os.chdir(working_directory)
    except (FileNotFoundError, PermissionError) as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    try:
        result = runner.invoke(cli, args, env=environment)
        stdout = None
        stderr = None
        try:
            stdout = result.stdout
        except (AttributeError, ValueError):
            stdout = None
        try:
            stderr = result.stderr
        except (AttributeError, ValueError):
            stderr = None
        if stdout is None:
            stdout = result.output
        if stderr is None:
            stderr = ""
        if result.exit_code != 0:
            stderr = result.output
        context.result = SimpleNamespace(
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            output=result.output,
        )
    finally:
        os.chdir(previous)


def run_cli_with_input(context: object, command: str, input_text: str) -> None:
    """Run the Kanbus CLI with stdin input in the scenario working directory.

    :param context: Behave context object.
    :type context: object
    :param command: Full command string.
    :type command: str
    :param input_text: Input to provide on stdin.
    :type input_text: str
    """
    runner = CliRunner()
    args = shlex.split(command)[1:]

    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")

    previous = Path.cwd()
    environment = os.environ.copy()
    overrides = getattr(context, "environment_overrides", None)
    if overrides:
        environment.update(overrides)
    environment.setdefault("KANBUS_FORCE_INTERACTIVE", "1")
    try:
        os.chdir(working_directory)
    except (FileNotFoundError, PermissionError) as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    try:
        result = runner.invoke(cli, args, env=environment, input=input_text)
        stdout = None
        stderr = None
        try:
            stdout = result.stdout
        except (AttributeError, ValueError):
            stdout = None
        try:
            stderr = result.stderr
        except (AttributeError, ValueError):
            stderr = None
        if stdout is None:
            stdout = result.output
        if stderr is None:
            stderr = ""
        if result.exit_code != 0:
            stderr = result.output
        context.result = SimpleNamespace(
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            output=result.output,
        )
    finally:
        os.chdir(previous)


def ensure_git_repository(path: Path) -> None:
    """Initialize a git repository for test setup.

    :param path: Directory path.
    :type path: Path
    """
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def ensure_project_directory(path: Path) -> Path:
    """Create a minimal project directory for test fixtures.

    :param path: Repository root path.
    :type path: Path
    :return: Project directory path.
    :rtype: Path
    """
    project_dir = path / "project"
    (project_dir / "issues").mkdir(parents=True, exist_ok=True)
    (project_dir / "events").mkdir(parents=True, exist_ok=True)
    return project_dir


def initialize_default_project(context: object) -> None:
    """Create a default project repository and run kanbus init.

    :param context: Behave context object.
    :type context: object
    """
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    context.working_directory = repository_path
    run_cli(context, "kanbus init")
    if context.result.exit_code != 0:
        raise AssertionError("failed to initialize project")


def load_project_directory(context: object) -> Path:
    """Load the project directory from discovery.

    :param context: Behave context object.
    :type context: object
    :return: Project directory path.
    :rtype: Path
    """
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    return resolve_project_directory(working_directory)


def write_issue_file(project_dir: Path, issue: IssueData) -> None:
    """Write an issue file in JSON format.

    :param project_dir: Project directory path.
    :type project_dir: Path
    :param issue: Issue data.
    :type issue: IssueData
    """
    issue_path = project_dir / "issues" / f"{issue.identifier}.json"
    payload = issue.model_dump(by_alias=True, mode="json")
    issue_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def read_issue_file(project_dir: Path, identifier: str) -> IssueData:
    """Read an issue file from disk.

    :param project_dir: Project directory path.
    :type project_dir: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Issue data.
    :rtype: IssueData
    """
    issue_path = project_dir / "issues" / f"{identifier}.json"
    payload = json.loads(issue_path.read_text(encoding="utf-8"))
    return IssueData.model_validate(payload)


def capture_issue_identifier(context: object) -> str:
    """Capture the issue identifier from stdout.

    :param context: Behave context object.
    :type context: object
    :return: Issue identifier.
    :rtype: str
    """
    result = getattr(context, "result", None)
    if result is None:
        raise RuntimeError("command result missing")
    clean_stdout = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    match = re.search(
        r"([A-Za-z0-9]+-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        clean_stdout,
    )
    if match is not None:
        context.last_issue_id = match.group(1)
        return context.last_issue_id

    abbreviated = re.search(r"(?i)\bID:\s*([A-Za-z0-9.-]+)", clean_stdout)
    if abbreviated is None:
        abbreviated = re.search(r"\b([A-Za-z0-9]{6}(?:\.[0-9]+)?)\b", clean_stdout)
    if abbreviated is None:
        raise AssertionError("no issue identifier found in stdout")
    abbr_value = abbreviated.group(1)
    abbr_base, abbr_suffix = _parse_abbreviation(abbr_value)
    project_dir = load_project_directory(context)
    for issue_path in (project_dir / "issues").glob("*.json"):
        identifier = issue_path.stem
        if _matches_abbreviation(identifier, abbr_base, abbr_suffix):
            context.last_issue_id = identifier
            return identifier
    local_dir = project_dir.parent / "project-local" / "issues"
    if local_dir.exists():
        for issue_path in local_dir.glob("*.json"):
            identifier = issue_path.stem
            if _matches_abbreviation(identifier, abbr_base, abbr_suffix):
                context.last_issue_id = identifier
                return identifier
    raise AssertionError("no issue identifier found in stdout")


def _parse_abbreviation(value: str) -> tuple[str, str | None]:
    if "-" in value:
        _, remainder = value.split("-", 1)
    else:
        remainder = value
    if "." in remainder:
        base, suffix = remainder.split(".", 1)
        return base.lower(), suffix.lower()
    return remainder.lower(), None


def _matches_abbreviation(identifier: str, base: str, suffix: str | None) -> bool:
    if "-" in identifier:
        _, remainder = identifier.split("-", 1)
    else:
        remainder = identifier
    if "." in remainder:
        id_base, id_suffix = remainder.split(".", 1)
    else:
        id_base, id_suffix = remainder, None
    normalized = id_base.replace("-", "").lower()
    if not normalized.startswith(base):
        return False
    if suffix is None:
        return True
    if id_suffix is None:
        return False
    return id_suffix.lower() == suffix.lower()


def build_issue(
    identifier: str,
    title: str,
    issue_type: str,
    status: str,
    parent: str | None,
    labels: Iterable[str],
) -> IssueData:
    """Build an IssueData instance for setup.

    :param identifier: Issue identifier.
    :type identifier: str
    :param title: Issue title.
    :type title: str
    :param issue_type: Issue type.
    :type issue_type: str
    :param status: Issue status.
    :type status: str
    :param parent: Parent identifier.
    :type parent: str | None
    :param labels: Issue labels.
    :type labels: Iterable[str]
    :return: Issue data.
    :rtype: IssueData
    """
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)
    return IssueData(
        id=identifier,
        title=title,
        description="",
        type=issue_type,
        status=status,
        priority=2,
        assignee=None,
        creator=None,
        parent=parent,
        labels=list(labels),
        dependencies=[],
        comments=[],
        created_at=timestamp,
        updated_at=timestamp,
        closed_at=None,
        custom={},
    )
