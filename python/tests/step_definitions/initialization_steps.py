"""Step definitions for project initialization scenarios."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
import yaml
from click.testing import CliRunner
from pytest_bdd import given, then, when

from taskulus.cli import cli


@dataclass
class InitializationContext:
    """State container for initialization scenarios."""

    working_directory: Optional[Path] = None
    result: Optional[object] = None


@pytest.fixture
def context() -> InitializationContext:
    return InitializationContext()


def _run_cli_in_directory(context: InitializationContext, command: str) -> None:
    runner = CliRunner()
    args = command.split()[1:]

    if context.working_directory is None:
        raise RuntimeError("working directory not set")

    previous = Path.cwd()
    try:
        os.chdir(context.working_directory)
        context.result = runner.invoke(cli, args)
    finally:
        os.chdir(previous)


@given("an empty git repository")
def given_empty_git_repository(tmp_path: Path, context: InitializationContext) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repository_path, check=True, capture_output=True
    )
    context.working_directory = repository_path


@given("a directory that is not a git repository")
def given_directory_not_git_repository(
    tmp_path: Path, context: InitializationContext
) -> None:
    repository_path = tmp_path / "not-a-repo"
    repository_path.mkdir()
    context.working_directory = repository_path


@given("a git repository with an existing Taskulus project")
def given_existing_taskulus_project(
    tmp_path: Path, context: InitializationContext
) -> None:
    repository_path = tmp_path / "existing"
    repository_path.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repository_path, check=True, capture_output=True
    )
    (repository_path / ".taskulus.yaml").write_text(
        yaml.safe_dump({"project_dir": "project"}, sort_keys=False),
        encoding="utf-8",
    )
    (repository_path / "project").mkdir()
    context.working_directory = repository_path


@when('I run "tsk init"')
def when_run_tsk_init(context: InitializationContext) -> None:
    _run_cli_in_directory(context, "tsk init")


@when('I run "tsk init --dir tracking"')
def when_run_tsk_init_custom_dir(context: InitializationContext) -> None:
    _run_cli_in_directory(context, "tsk init --dir tracking")


@then('a ".taskulus.yaml" file should exist in the repository root')
def then_marker_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / ".taskulus.yaml").exists()


@then('a ".taskulus.yaml" file should exist pointing to "tracking"')
def then_marker_points_tracking(context: InitializationContext) -> None:
    assert context.working_directory is not None
    data = yaml.safe_load((context.working_directory / ".taskulus.yaml").read_text())
    assert data["project_dir"] == "tracking"


@then('a "project" directory should exist')
def then_project_directory_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / "project").is_dir()


@then('a "tracking" directory should exist')
def then_tracking_directory_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / "tracking").is_dir()


@then('a "project/config.yaml" file should exist with default configuration')
def then_default_config_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / "project" / "config.yaml").is_file()


@then('a "tracking/config.yaml" file should exist with default configuration')
def then_default_config_exists_tracking(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / "tracking" / "config.yaml").is_file()


@then('a "project/issues" directory should exist and be empty')
def then_issues_directory_empty(context: InitializationContext) -> None:
    assert context.working_directory is not None
    issues_dir = context.working_directory / "project" / "issues"
    assert issues_dir.is_dir()
    assert list(issues_dir.iterdir()) == []


@then('a "project/wiki" directory should exist')
def then_wiki_directory_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / "project" / "wiki").is_dir()


@then('a "project/wiki/index.md" file should exist')
def then_wiki_index_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert (context.working_directory / "project" / "wiki" / "index.md").is_file()


@then('a "project/.cache" directory should not exist yet')
def then_cache_not_exists(context: InitializationContext) -> None:
    assert context.working_directory is not None
    assert not (context.working_directory / "project" / ".cache").exists()


@then("the command should fail with exit code 1")
def then_command_failed(context: InitializationContext) -> None:
    assert context.result is not None
    assert context.result.exit_code == 1


@then('stderr should contain "already initialized"')
def then_stderr_contains_initialized(context: InitializationContext) -> None:
    assert context.result is not None
    assert "already initialized" in context.result.stderr


@then('stderr should contain "not a git repository"')
def then_stderr_contains_not_git(context: InitializationContext) -> None:
    assert context.result is not None
    assert "not a git repository" in context.result.stderr
