"""Behave steps for project initialization."""

from __future__ import annotations

from pathlib import Path
from behave import given, then, when

from features.steps.shared import ensure_git_repository, run_cli


@given("an empty git repository")
def given_empty_git_repository(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    context.working_directory = repository_path


@given("a directory that is not a git repository")
def given_directory_not_git_repository(context: object) -> None:
    repository_path = Path(context.temp_dir) / "not-a-repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    context.working_directory = repository_path


@given("a git repository with an existing Taskulus project")
def given_existing_taskulus_project(context: object) -> None:
    repository_path = Path(context.temp_dir) / "existing"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    (repository_path / "project" / "issues").mkdir(parents=True)
    context.working_directory = repository_path


@given("a git repository metadata directory")
def given_git_metadata_directory(context: object) -> None:
    repository_path = Path(context.temp_dir) / "metadata"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    context.working_directory = repository_path / ".git"


@when('I run "tsk init"')
def when_run_tsk_init(context: object) -> None:
    run_cli(context, "tsk init")


@when('I run "tsk init --local"')
def when_run_tsk_init_local(context: object) -> None:
    run_cli(context, "tsk init --local")


@then('a ".taskulus.yaml" file should not exist')
def then_marker_missing(context: object) -> None:
    assert not (context.working_directory / ".taskulus.yaml").exists()


@then('a "project" directory should exist')
def then_project_directory_exists(context: object) -> None:
    assert (context.working_directory / "project").is_dir()


@then('a "project/config.yaml" file should not exist')
def then_default_config_missing(context: object) -> None:
    assert not (context.working_directory / "project" / "config.yaml").exists()


@then('a "project/issues" directory should exist and be empty')
def then_issues_directory_empty(context: object) -> None:
    issues_dir = context.working_directory / "project" / "issues"
    assert issues_dir.is_dir()
    assert list(issues_dir.iterdir()) == []


@then('a "project/wiki" directory should not exist')
def then_wiki_directory_missing(context: object) -> None:
    assert not (context.working_directory / "project" / "wiki").exists()


@then('a "project-local/issues" directory should exist')
def then_local_issues_directory_exists(context: object) -> None:
    assert (context.working_directory / "project-local" / "issues").is_dir()


@then("the command should fail with exit code 1")
def then_command_failed(context: object) -> None:
    assert context.result.exit_code == 1


@then("the command should fail")
def then_command_failed_generic(context: object) -> None:
    assert context.result.exit_code != 0
