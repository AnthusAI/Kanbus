"""Behave steps for project discovery scenarios."""

from __future__ import annotations

from pathlib import Path

from behave import given, then

from features.steps.shared import build_issue, ensure_git_repository, write_issue_file
from kanbus.ids import format_issue_key


def _create_repo(context: object, name: str) -> Path:
    root = Path(context.temp_dir) / name
    root.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(root)
    context.working_directory = root
    return root


def _write_issue(project_dir: Path, identifier: str, title: str) -> None:
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    issue = build_issue(identifier, title, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given("a repository with nested project directories")
def given_repo_with_nested_projects(context: object) -> None:
    root = _create_repo(context, "nested-projects")
    root_project = root / "project"
    nested_project = root / "nested" / "project"
    _write_issue(root_project, "kanbus-root", "Root task")
    _write_issue(nested_project, "kanbus-nested", "Nested task")
    context.discovered_issue_keys = [
        format_issue_key("kanbus-root", project_context=False),
        format_issue_key("kanbus-nested", project_context=False),
    ]


@given("a repository with a project directory above the current directory")
def given_repo_project_above_cwd(context: object) -> None:
    root = _create_repo(context, "project-above")
    project_dir = root / "project"
    _write_issue(project_dir, "kanbus-above", "Above task")
    child_dir = root / "child"
    child_dir.mkdir(parents=True, exist_ok=True)
    context.working_directory = child_dir
    context.above_issue_key = format_issue_key("kanbus-above", project_context=True)


@given("a project directory with a sibling project-local directory")
def given_repo_with_project_local(context: object) -> None:
    root = _create_repo(context, "project-local")
    project_dir = root / "project"
    local_dir = root / "project-local"
    _write_issue(project_dir, "kanbus-shared1", "Shared task")
    _write_issue(local_dir, "kanbus-local1", "Local task")
    context.shared_issue_key = format_issue_key("kanbus-shared1", project_context=True)
    context.local_issue_key = format_issue_key("kanbus-local1", project_context=True)


@given("a repository with a .kanbus file referencing another project")
def given_repo_with_kanbus_dotfile(context: object) -> None:
    root = _create_repo(context, "kanbus-dotfile")
    external_root = Path(context.temp_dir) / "dotfile-external"
    external_project = external_root / "project"
    _write_issue(external_project, "kanbus-external", "External task")
    (root / ".kanbus").write_text(
        f"{external_project}\n",
        encoding="utf-8",
    )
    context.external_project_path = external_project.resolve()


@given("a repository with a .kanbus file referencing a missing path")
def given_repo_with_kanbus_dotfile_missing(context: object) -> None:
    root = _create_repo(context, "kanbus-dotfile-missing")
    (root / ".kanbus").write_text("missing/project\n", encoding="utf-8")


@then("issues from all discovered projects should be listed")
def then_issues_from_all_projects(context: object) -> None:
    for key in getattr(context, "discovered_issue_keys", []):
        assert key in context.result.stdout


@then("no issues should be listed")
def then_no_issues_listed(context: object) -> None:
    above_key = getattr(context, "above_issue_key", None)
    if above_key:
        assert above_key not in context.result.stdout
        return
    assert context.result.stdout.strip() == ""


@then("local issues should be included")
def then_local_issues_included(context: object) -> None:
    assert context.local_issue_key in context.result.stdout


@then("local issues should not be listed")
def then_local_issues_not_listed(context: object) -> None:
    assert context.local_issue_key not in context.result.stdout


@then("only local issues should be listed")
def then_only_local_issues_listed(context: object) -> None:
    assert context.local_issue_key in context.result.stdout
    assert context.shared_issue_key not in context.result.stdout


@then("issues from the referenced project should be listed")
def then_issues_from_referenced_project_listed(context: object) -> None:
    expected = format_issue_key("kanbus-external", project_context=False)
    assert expected in context.result.stdout
