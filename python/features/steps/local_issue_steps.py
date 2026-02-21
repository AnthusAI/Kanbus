"""Behave steps for local issue routing."""

from __future__ import annotations

from pathlib import Path

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    capture_issue_identifier,
    load_project_directory,
    write_issue_file,
)


def _local_project_directory(context: object) -> Path:
    project_dir = load_project_directory(context)
    local_dir = project_dir.parent / "project-local"
    (local_dir / "issues").mkdir(parents=True, exist_ok=True)
    return local_dir


@given('a local issue "kanbus-local01" exists')
def given_local_issue_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("kanbus-local01", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "kanbus-dupe01" exists')
def given_local_issue_dupe_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("kanbus-dupe01", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "kanbus-other" exists')
def given_local_issue_other_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("kanbus-other", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "kanbus-dupe02" exists')
def given_local_issue_dupe02_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("kanbus-dupe02", "Local", "task", "open", None, [])
    write_issue_file(local_dir, issue)


@given('a local issue "kanbus-local" exists')
def given_local_issue_local_exists(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue("kanbus-local", "Local", "task", "open", None, [])
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


@then("the local issues directory should contain {issue_count:d} issue file")
def then_local_issue_directory_contains_count(
    context: object, issue_count: int
) -> None:
    local_dir = _local_project_directory(context)
    issues = list((local_dir / "issues").glob("*.json"))
    assert len(issues) == issue_count


@then('issue "kanbus-local01" should exist in the shared issues directory')
def then_issue_exists_shared_local(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "kanbus-local01.json"
    assert issue_path.exists()


@then('issue "kanbus-local01" should not exist in the local issues directory')
def then_issue_missing_local_local(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue_path = local_dir / "issues" / "kanbus-local01.json"
    assert not issue_path.exists()


@then('issue "kanbus-shared01" should exist in the local issues directory')
def then_issue_exists_local_shared(context: object) -> None:
    local_dir = _local_project_directory(context)
    issue_path = local_dir / "issues" / "kanbus-shared01.json"
    assert issue_path.exists()


@then('issue "kanbus-shared01" should not exist in the shared issues directory')
def then_issue_missing_shared_shared(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "kanbus-shared01.json"
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
