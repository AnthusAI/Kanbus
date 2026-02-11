"""Behave steps for project initialization."""

from __future__ import annotations

from pathlib import Path

import yaml
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
    (repository_path / ".taskulus.yaml").write_text(
        yaml.safe_dump({"project_dir": "project"}, sort_keys=False),
        encoding="utf-8",
    )
    (repository_path / "project").mkdir()
    context.working_directory = repository_path


@when('I run "tsk init"')
def when_run_tsk_init(context: object) -> None:
    run_cli(context, "tsk init")


@when('I run "tsk init --dir tracking"')
def when_run_tsk_init_custom_dir(context: object) -> None:
    run_cli(context, "tsk init --dir tracking")


@then('a ".taskulus.yaml" file should exist in the repository root')
def then_marker_exists(context: object) -> None:
    assert (context.working_directory / ".taskulus.yaml").exists()


@then('a ".taskulus.yaml" file should exist pointing to "tracking"')
def then_marker_points_tracking(context: object) -> None:
    data = yaml.safe_load((context.working_directory / ".taskulus.yaml").read_text())
    assert data["project_dir"] == "tracking"


@then('a "project" directory should exist')
def then_project_directory_exists(context: object) -> None:
    assert (context.working_directory / "project").is_dir()


@then('a "tracking" directory should exist')
def then_tracking_directory_exists(context: object) -> None:
    assert (context.working_directory / "tracking").is_dir()


@then('a "project/config.yaml" file should exist with default configuration')
def then_default_config_exists(context: object) -> None:
    assert (context.working_directory / "project" / "config.yaml").is_file()


@then('a "tracking/config.yaml" file should exist with default configuration')
def then_default_config_exists_tracking(context: object) -> None:
    assert (context.working_directory / "tracking" / "config.yaml").is_file()


@then('a "project/issues" directory should exist and be empty')
def then_issues_directory_empty(context: object) -> None:
    issues_dir = context.working_directory / "project" / "issues"
    assert issues_dir.is_dir()
    assert list(issues_dir.iterdir()) == []


@then('a "project/wiki" directory should exist')
def then_wiki_directory_exists(context: object) -> None:
    assert (context.working_directory / "project" / "wiki").is_dir()


@then('a "project/wiki/index.md" file should exist')
def then_wiki_index_exists(context: object) -> None:
    assert (context.working_directory / "project" / "wiki" / "index.md").is_file()


@then('a "project/.cache" directory should not exist yet')
def then_cache_not_exists(context: object) -> None:
    assert not (context.working_directory / "project" / ".cache").exists()


@then("the command should fail with exit code 1")
def then_command_failed(context: object) -> None:
    assert context.result.exit_code == 1


@then('stderr should contain "already initialized"')
def then_stderr_contains_initialized(context: object) -> None:
    assert "already initialized" in context.result.stderr


@then('stderr should contain "not a git repository"')
def then_stderr_contains_not_git(context: object) -> None:
    assert "not a git repository" in context.result.stderr
