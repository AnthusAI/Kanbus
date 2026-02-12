"""Behave steps for project utility scenarios."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import os

from behave import given, then, when

from features.steps.shared import ensure_git_repository, write_issue_file
from taskulus.models import IssueData
from taskulus.project import (
    ProjectMarkerError,
    discover_project_directories,
    load_project_directory,
    _discover_taskulus_projects,
)


def _create_repo(context: object, name: str) -> Path:
    root = Path(context.temp_dir) / name
    root.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(root)
    context.working_directory = root
    return root


@given("a repository with a single project directory")
def given_repo_single_project(context: object) -> None:
    root = _create_repo(context, "single-project")
    (root / "project").mkdir()


@given("an empty repository without a project directory")
def given_repo_without_project(context: object) -> None:
    _create_repo(context, "empty-project")


@given("a repository with multiple project directories")
def given_repo_multiple_projects(context: object) -> None:
    root = _create_repo(context, "multi-project")
    (root / "project").mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "project").mkdir(parents=True)


def _build_issue(identifier: str, title: str) -> IssueData:
    timestamp = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
    return IssueData(
        id=identifier,
        title=title,
        description="",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=timestamp,
        updated_at=timestamp,
        closed_at=None,
        custom={},
    )


@given("a repository with multiple projects and issues")
def given_repo_multiple_projects_with_issues(context: object) -> None:
    root = _create_repo(context, "multi-project-issues")
    alpha_project = root / "alpha" / "project"
    beta_project = root / "beta" / "project"
    (alpha_project / "issues").mkdir(parents=True)
    (beta_project / "issues").mkdir(parents=True)
    write_issue_file(alpha_project, _build_issue("tsk-alpha", "Alpha task"))
    write_issue_file(beta_project, _build_issue("tsk-beta", "Beta task"))


@given("a repository with multiple projects and local issues")
def given_repo_multiple_projects_with_local_issues(context: object) -> None:
    root = _create_repo(context, "multi-project-local")
    alpha_project = root / "alpha" / "project"
    beta_project = root / "beta" / "project"
    (alpha_project / "issues").mkdir(parents=True)
    (beta_project / "issues").mkdir(parents=True)
    write_issue_file(alpha_project, _build_issue("tsk-alpha", "Alpha task"))
    write_issue_file(beta_project, _build_issue("tsk-beta", "Beta task"))
    local_project = root / "alpha" / "project-local"
    (local_project / "issues").mkdir(parents=True)
    write_issue_file(local_project, _build_issue("tsk-alpha-local", "Alpha local task"))


@given("a repository with a .taskulus file referencing another project")
def given_repo_taskulus_external_project(context: object) -> None:
    root = _create_repo(context, "taskulus-external")
    (root / "project" / "issues").mkdir(parents=True)
    write_issue_file(root / "project", _build_issue("tsk-internal", "Internal task"))
    external_root = Path(context.temp_dir) / "external-project"
    external_project = external_root / "project"
    (external_project / "issues").mkdir(parents=True)
    write_issue_file(external_project, _build_issue("tsk-external", "External task"))
    (root / ".taskulus").write_text(f"{external_project}\n", encoding="utf-8")
    context.external_project_path = external_project.resolve()

@given("a repository with a .taskulus file referencing a missing path")
def given_repo_taskulus_missing_path(context: object) -> None:
    root = _create_repo(context, "taskulus-missing")
    (root / ".taskulus").write_text("missing/project\n", encoding="utf-8")


@given("a repository with a .taskulus file referencing a valid path with blank lines")
def given_repo_taskulus_with_blank_lines(context: object) -> None:
    root = _create_repo(context, "taskulus-blank-lines")
    (root / "extras" / "project").mkdir(parents=True)
    (root / ".taskulus").write_text("\nextras/project\n\n", encoding="utf-8")
    context.expected_project_dir = (root / "extras" / "project").resolve()


@given("a non-git directory without projects")
def given_non_git_directory(context: object) -> None:
    root = Path(context.temp_dir) / "no-git"
    root.mkdir(parents=True, exist_ok=True)
    context.working_directory = root


@given("a repository with a fake git root pointing to a file")
def given_repo_fake_git_root(context: object) -> None:
    root = _create_repo(context, "fake-git-root")
    fake_file = root / "not-a-dir"
    fake_file.write_text("data", encoding="utf-8")
    bin_dir = root / "fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    git_path = bin_dir / "git"
    git_path.write_text(f"#!/bin/sh\necho {fake_file}\n", encoding="utf-8")
    git_path.chmod(0o755)
    context.original_path_env = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{context.original_path_env}"


@when("project directories are discovered")
def when_project_dirs_discovered(context: object) -> None:
    root = Path(context.working_directory)
    try:
        context.project_dirs = discover_project_directories(root)
        context.project_error = None
    except ProjectMarkerError as error:
        context.project_dirs = []
        context.project_error = str(error)


@when("taskulus dotfile paths are discovered from the filesystem root")
def when_taskulus_dotfile_paths_from_root(context: object) -> None:
    context.project_dirs = _discover_taskulus_projects(Path("/"))
    context.project_error = None


@when("the project directory is loaded")
def when_project_dir_loaded(context: object) -> None:
    root = Path(context.working_directory)
    try:
        context.project_dir = load_project_directory(root)
        context.project_error = None
    except ProjectMarkerError as error:
        context.project_dir = None
        context.project_error = str(error)


@then("exactly one project directory should be returned")
def then_single_project_returned(context: object) -> None:
    assert len(context.project_dirs) == 1


@then('project discovery should fail with "project not initialized"')
def then_project_not_initialized(context: object) -> None:
    assert context.project_error == "project not initialized"


@then('project discovery should fail with "multiple projects found"')
def then_project_multiple(context: object) -> None:
    assert context.project_error == "multiple projects found"


@then('project discovery should fail with "taskulus path not found"')
def then_project_missing_path(context: object) -> None:
    assert context.project_error.startswith("taskulus path not found")


@then("project discovery should include the referenced path")
def then_project_includes_referenced_path(context: object) -> None:
    expected = getattr(context, "expected_project_dir", None)
    assert expected is not None
    assert expected in context.project_dirs


@then("project discovery should return no projects")
def then_project_returns_no_projects(context: object) -> None:
    assert context.project_dirs == []
