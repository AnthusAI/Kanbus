"""Behave steps for project initialization."""

from __future__ import annotations

from pathlib import Path
from behave import given, then

from features.steps.shared import ensure_git_repository


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


@given("a git repository with an existing Kanbus project")
def given_existing_kanbus_project(context: object) -> None:
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


@then('a ".kanbus.yml" file should be created')
def then_marker_created(context: object) -> None:
    assert (context.working_directory / ".kanbus.yml").is_file()


@then('a "CONTRIBUTING_AGENT.template.md" file should be created')
def then_project_management_template_created(context: object) -> None:
    assert (context.working_directory / "CONTRIBUTING_AGENT.template.md").is_file()


@then('CONTRIBUTING_AGENT.template.md should contain "{text}"')
def then_project_management_template_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    content = (context.working_directory / "CONTRIBUTING_AGENT.template.md").read_text(
        encoding="utf-8"
    )
    assert normalized in content


@then('a "project" directory should exist')
def then_project_directory_exists(context: object) -> None:
    assert (context.working_directory / "project").is_dir()


@then('a "project/config.yaml" file should not exist')
def then_default_config_missing(context: object) -> None:
    assert not (context.working_directory / "project" / "config.yaml").exists()


@then('a "project/issues" directory should exist and contain only guard files')
def then_issues_directory_only_guards(context: object) -> None:
    issues_dir = context.working_directory / "project" / "issues"
    assert issues_dir.is_dir()
    names = {p.name for p in issues_dir.iterdir()}
    assert names == {
        "AGENTS.md",
        "DO_NOT_EDIT",
    }, f"expected only guard files, got {names}"


@then('the file "{path}" should exist')
def then_file_exists(context: object, path: str) -> None:
    full_path = context.working_directory / path
    assert full_path.exists(), f"expected file {path} to exist"
    assert full_path.is_file(), f"expected {path} to be a file"


@then('the file "{path}" should contain "{text}"')
def then_file_contains(context: object, path: str, text: str) -> None:
    full_path = context.working_directory / path
    content = full_path.read_text(encoding="utf-8")
    assert text in content, f"expected {path} to contain {text!r}"


@then('a "project-local/issues" directory should exist')
def then_local_issues_directory_exists(context: object) -> None:
    assert (context.working_directory / "project-local" / "issues").is_dir()


@then("the command should fail with exit code 1")
def then_command_failed(context: object) -> None:
    if context.result.exit_code != 1:
        print(f"Expected exit code 1, got {context.result.exit_code}")
        print(f"STDOUT: {context.result.stdout}")
        print(f"STDERR: {context.result.stderr}")
    assert context.result.exit_code == 1


@then("the command should fail")
def then_command_failed_generic(context: object) -> None:
    assert context.result.exit_code != 0


@then("project/issues/ and project/events/ should contain AGENTS.md with the warning")
def then_issues_events_agents_created(context: object) -> None:
    for subdir in ("issues", "events"):
        path = context.working_directory / "project" / subdir / "AGENTS.md"
        assert path.is_file(), f"expected {path}"
        content = path.read_text(encoding="utf-8")
        assert "DO NOT EDIT HERE" in content
        assert "The Way" in content or "Kanbus" in content


@then("project/issues/ and project/events/ should contain DO_NOT_EDIT with the warning")
def then_issues_events_do_not_edit_created(context: object) -> None:
    for subdir in ("issues", "events"):
        path = context.working_directory / "project" / subdir / "DO_NOT_EDIT"
        assert path.is_file(), f"expected {path}"
        content = path.read_text(encoding="utf-8")
        assert "DO NOT EDIT" in content
        assert "The Way" in content
