"""Behave steps for local issue routing."""

from __future__ import annotations

from pathlib import Path

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    capture_issue_identifier,
    load_project_directory,
    run_cli,
    write_issue_file,
)


def _local_project_directory(context: object) -> Path:
    project_dir = load_project_directory(context)
    local_dir = project_dir.parent / "project-local"
    (local_dir / "issues").mkdir(parents=True, exist_ok=True)
    return local_dir


@when('I run "tsk create --local Local task"')
def when_run_create_local(context: object) -> None:
    run_cli(context, "tsk create --local Local task")


@when('I run "tsk promote tsk-local01"')
def when_run_promote(context: object) -> None:
    run_cli(context, "tsk promote tsk-local01")


@when('I run "tsk localize tsk-shared01"')
def when_run_localize(context: object) -> None:
    run_cli(context, "tsk localize tsk-shared01")


@when('I run "tsk promote tsk-missing"')
def when_run_promote_missing(context: object) -> None:
    run_cli(context, "tsk promote tsk-missing")


@when('I run "tsk promote tsk-dupe01"')
def when_run_promote_dupe(context: object) -> None:
    run_cli(context, "tsk promote tsk-dupe01")


@when('I run "tsk localize tsk-missing"')
def when_run_localize_missing(context: object) -> None:
    run_cli(context, "tsk localize tsk-missing")


@when('I run "tsk localize tsk-dupe02"')
def when_run_localize_dupe(context: object) -> None:
    run_cli(context, "tsk localize tsk-dupe02")


@given('a local issue "tsk-local01" exists')
def given_local_issue_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("tsk-local01", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "tsk-dupe01" exists')
def given_local_issue_dupe_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("tsk-dupe01", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "tsk-other" exists')
def given_local_issue_other_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("tsk-other", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "tsk-dupe02" exists')
def given_local_issue_dupe02_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("tsk-dupe02", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "tsk-local" exists')
def given_local_issue_local_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("tsk-local", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('.gitignore already includes "project-local/"')
def given_gitignore_includes_project_local(context: object) -> None:
    project_dir = load_project_directory(context)
    gitignore_path = project_dir.parent / ".gitignore"
    gitignore_path.write_text("project-local/\n", encoding="utf-8")


@given("a .gitignore without a trailing newline exists")
def given_gitignore_without_trailing_newline(context: object) -> None:
    project_dir = load_project_directory(context)
    gitignore_path = project_dir.parent / ".gitignore"
    gitignore_path.write_text("node_modules", encoding="utf-8")


@then("a local issue file should be created in the local issues directory")
def then_local_issue_file_created(context: object) -> None:
    _ = capture_issue_identifier(context)
    local_dir = _local_project_directory(context)
    issues = list((local_dir / "issues").glob("*.json"))
    assert len(issues) == 1


@then('issue "tsk-local01" should exist in the shared issues directory')
def then_issue_exists_shared_local(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "tsk-local01.json"
    assert issue_path.exists()


@then('issue "tsk-local01" should not exist in the local issues directory')
def then_issue_missing_local_local(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue_path = local_dir / "issues" / "tsk-local01.json"
    assert not issue_path.exists()


@then('issue "tsk-shared01" should exist in the local issues directory')
def then_issue_exists_local_shared(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue_path = local_dir / "issues" / "tsk-shared01.json"
    assert issue_path.exists()


@then('issue "tsk-shared01" should not exist in the shared issues directory')
def then_issue_missing_shared_shared(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "tsk-shared01.json"
    assert not issue_path.exists()


@then('.gitignore should include "project-local/"')
def then_gitignore_includes_project_local(context: object) -> None:
    project_dir = load_project_directory(context)
    gitignore_path = project_dir.parent / ".gitignore"
    contents = gitignore_path.read_text(encoding="utf-8")
    assert "project-local/" in contents.splitlines()


@then('.gitignore should include "project-local/" only once')
def then_gitignore_includes_once(context: object) -> None:
    project_dir = load_project_directory(context)
    gitignore_path = project_dir.parent / ".gitignore"
    contents = gitignore_path.read_text(encoding="utf-8")
    entries = [line.strip() for line in contents.splitlines() if line.strip()]
    assert entries.count("project-local/") == 1
