"""Behave steps for migration."""

from __future__ import annotations

import shutil
from pathlib import Path

from behave import given, then, when
import yaml

from features.steps.shared import ensure_git_repository, load_project_directory, run_cli


def _fixture_beads_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "specs" / "fixtures" / "beads_repo" / ".beads"


@given("a git repository with a .beads issues database")
def given_repo_with_beads(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    target_beads = repository_path / ".beads"
    shutil.copytree(_fixture_beads_dir(), target_beads)
    context.working_directory = repository_path


@given("a git repository without a .beads directory")
def given_repo_without_beads(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    context.working_directory = repository_path


@given("a Taskulus project already exists")
def given_taskulus_project_exists(context: object) -> None:
    repository_path = context.working_directory
    marker_path = repository_path / ".taskulus.yaml"
    marker_path.write_text(
        yaml.safe_dump({"project_dir": "project"}, sort_keys=False),
        encoding="utf-8",
    )
    (repository_path / "project").mkdir(parents=True, exist_ok=True)


@when('I run "tsk migrate"')
def when_run_migrate(context: object) -> None:
    run_cli(context, "tsk migrate")


@then("a Taskulus project should be initialized")
def then_taskulus_initialized(context: object) -> None:
    assert (context.working_directory / ".taskulus.yaml").is_file()
    project_dir = load_project_directory(context)
    assert project_dir.is_dir()


@then("all Beads issues should be converted to Taskulus issues")
def then_beads_converted(context: object) -> None:
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    lines = [line for line in issues_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    project_dir = load_project_directory(context)
    issue_files = list((project_dir / "issues").glob("*.json"))
    assert len(issue_files) == len(lines)


@then('stderr should contain "no .beads directory"')
def then_stderr_contains_missing_beads(context: object) -> None:
    assert "no .beads directory" in context.result.stderr
