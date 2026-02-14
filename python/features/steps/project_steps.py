"""Behave steps for project utility scenarios."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import os
import shutil

from behave import given, then, when
import yaml

from features.steps.shared import ensure_git_repository, write_issue_file
from kanbus.models import IssueData
from kanbus.project import (
    ProjectMarkerError,
    discover_project_directories,
    discover_kanbus_projects,
    get_configuration_path,
    load_project_directory,
)


def _set_env_override(context: object, name: str, attr: str, value: str) -> None:
    if attr not in context.__dict__:
        context.__dict__[attr] = os.environ.get(name)
    os.environ[name] = value


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


@given("a repository with a project directory that cannot be canonicalized")
def given_repo_project_cannot_canonicalize(context: object) -> None:
    root = _create_repo(context, "canonicalize-failure")
    project_dir = root / "project"
    project_dir.mkdir()
    _set_env_override(
        context,
        "KANBUS_TEST_CANONICALIZE_FAILURE",
        "original_canonicalize_env",
        "1",
    )
    original_mode = project_dir.stat().st_mode
    project_dir.chmod(0)
    context.unreadable_path = project_dir
    context.unreadable_mode = original_mode


@given("project directory canonicalization will fail")
def given_project_directory_canonicalization_failure(context: object) -> None:
    _set_env_override(
        context,
        "KANBUS_TEST_CANONICALIZE_FAILURE",
        "original_canonicalize_env",
        "1",
    )


@given("configuration path lookup will fail")
def given_configuration_path_lookup_failure(context: object) -> None:
    _set_env_override(
        context,
        "KANBUS_TEST_CONFIGURATION_PATH_FAILURE",
        "original_configuration_path_failure_env",
        "1",
    )


@given("a repository directory that is unreadable")
def given_repo_unreadable(context: object) -> None:
    root = _create_repo(context, "unreadable-projects")
    original_mode = root.stat().st_mode
    root.chmod(0)
    context.unreadable_path = root
    context.unreadable_mode = original_mode


@given("a repository directory that has been removed")
def given_repo_removed(context: object) -> None:
    root = _create_repo(context, "removed-projects")
    shutil.rmtree(root)
    context.working_directory = root


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
    write_issue_file(alpha_project, _build_issue("kanbus-alpha", "Alpha task"))
    write_issue_file(beta_project, _build_issue("kanbus-beta", "Beta task"))


@given("a repository with multiple projects and local issues")
def given_repo_multiple_projects_with_local_issues(context: object) -> None:
    root = _create_repo(context, "multi-project-local")
    alpha_project = root / "alpha" / "project"
    beta_project = root / "beta" / "project"
    (alpha_project / "issues").mkdir(parents=True)
    (beta_project / "issues").mkdir(parents=True)
    write_issue_file(alpha_project, _build_issue("kanbus-alpha", "Alpha task"))
    write_issue_file(beta_project, _build_issue("kanbus-beta", "Beta task"))
    local_project = root / "alpha" / "project-local"
    (local_project / "issues").mkdir(parents=True)
    write_issue_file(local_project, _build_issue("kanbus-alpha-local", "Alpha local task"))


@given("a repository with a .kanbus.yml file referencing another project")
def given_repo_kanbus_external_project(context: object) -> None:
    root = _create_repo(context, "kanbus-external")
    (root / "project" / "issues").mkdir(parents=True)
    write_issue_file(root / "project", _build_issue("kanbus-internal", "Internal task"))
    external_root = Path(context.temp_dir) / "external-project"
    external_project = external_root / "project"
    (external_project / "issues").mkdir(parents=True)
    write_issue_file(external_project, _build_issue("kanbus-external", "External task"))
    payload = {
        "project_directory": "project",
        "external_projects": [str(external_project)],
        "project_key": "kanbus",
        "hierarchy": ["initiative", "epic", "task", "sub-task"],
        "types": ["bug", "story", "chore"],
        "workflows": {
            "default": {
                "open": ["in_progress", "closed", "deferred"],
                "in_progress": ["open", "blocked", "closed"],
                "blocked": ["in_progress", "closed"],
                "closed": ["open"],
                "deferred": ["open", "closed"],
            }
        },
        "initial_status": "open",
        "priorities": {
            0: {"name": "critical", "color": "red"},
            1: {"name": "high", "color": "bright_red"},
            2: {"name": "medium", "color": "yellow"},
            3: {"name": "low", "color": "blue"},
            4: {"name": "trivial", "color": "white"},
        },
        "default_priority": 2,
    }
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    context.external_project_path = external_project.resolve()
    context.external_issue_title = "External task"


@given("a repository with a .kanbus.yml file referencing a missing path")
def given_repo_kanbus_missing_path(context: object) -> None:
    root = _create_repo(context, "kanbus-missing")
    payload = {
        "project_directory": "project",
        "external_projects": ["missing/project"],
        "project_key": "kanbus",
        "hierarchy": ["initiative", "epic", "task", "sub-task"],
        "types": ["bug", "story", "chore"],
        "workflows": {
            "default": {
                "open": ["in_progress", "closed", "deferred"],
                "in_progress": ["open", "blocked", "closed"],
                "blocked": ["in_progress", "closed"],
                "closed": ["open"],
                "deferred": ["open", "closed"],
            }
        },
        "initial_status": "open",
        "priorities": {
            0: {"name": "critical", "color": "red"},
            1: {"name": "high", "color": "bright_red"},
            2: {"name": "medium", "color": "yellow"},
            3: {"name": "low", "color": "blue"},
            4: {"name": "trivial", "color": "white"},
        },
        "default_priority": 2,
    }
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


@given("a repository with an invalid .kanbus.yml file")
def given_repo_invalid_kanbus_config(context: object) -> None:
    root = _create_repo(context, "kanbus-invalid")
    (root / ".kanbus.yml").write_text(
        "unknown_field: value\n",
        encoding="utf-8",
    )


@given(
    "a repository with a .kanbus.yml file referencing a valid path with blank lines"
)
def given_repo_kanbus_with_blank_lines(context: object) -> None:
    root = _create_repo(context, "kanbus-blank-lines")
    (root / "extras" / "project").mkdir(parents=True)
    payload = {
        "project_directory": "extras/project",
        "external_projects": [],
        "project_key": "kanbus",
        "hierarchy": ["initiative", "epic", "task", "sub-task"],
        "types": ["bug", "story", "chore"],
        "workflows": {
            "default": {
                "open": ["in_progress", "closed", "deferred"],
                "in_progress": ["open", "blocked", "closed"],
                "blocked": ["in_progress", "closed"],
                "closed": ["open"],
                "deferred": ["open", "closed"],
            }
        },
        "initial_status": "open",
        "priorities": {
            0: {"name": "critical", "color": "red"},
            1: {"name": "high", "color": "bright_red"},
            2: {"name": "medium", "color": "yellow"},
            3: {"name": "low", "color": "blue"},
            4: {"name": "trivial", "color": "white"},
        },
        "default_priority": 2,
    }
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
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


@when("kanbus configuration paths are discovered from the filesystem root")
def when_kanbus_configuration_paths_from_root(context: object) -> None:
    try:
        context.project_dirs = discover_kanbus_projects(Path("/"))
        context.project_error = None
    except ProjectMarkerError as error:
        context.project_dirs = []
        context.project_error = str(error)


@when("the project directory is loaded")
def when_project_dir_loaded(context: object) -> None:
    root = Path(context.working_directory)
    try:
        context.project_dir = load_project_directory(root)
        context.project_dirs = [context.project_dir]
        context.project_error = None
    except ProjectMarkerError as error:
        context.project_dir = None
        context.project_dirs = []
        context.project_error = str(error)


@when("the configuration path is requested")
def when_configuration_path_requested(context: object) -> None:
    root = Path(context.working_directory)
    try:
        context.configuration_path = get_configuration_path(root)
        context.project_error = None
    except ProjectMarkerError as error:
        context.configuration_path = None
        context.project_error = str(error)


@then("exactly one project directory should be returned")
def then_single_project_returned(context: object) -> None:
    assert len(context.project_dirs) == 1


@then('project discovery should fail with "project not initialized"')
def then_project_not_initialized(context: object) -> None:
    assert context.project_error == "project not initialized"


@then('project discovery should fail with "multiple projects found"')
def then_project_multiple(context: object) -> None:
    assert context.project_error is not None
    assert "multiple projects found" in context.project_error


@then('project discovery should fail with "kanbus path not found"')
def then_project_missing_path(context: object) -> None:
    assert context.project_error.startswith("kanbus path not found")


@then('project discovery should fail with "unknown configuration fields"')
def then_project_unknown_fields(context: object) -> None:
    assert context.project_error == "unknown configuration fields"


@then("project discovery should include the referenced path")
def then_project_includes_referenced_path(context: object) -> None:
    expected = getattr(context, "expected_project_dir", None)
    assert expected is not None
    expected = expected.resolve()
    resolved = [path.resolve() for path in context.project_dirs]
    assert expected in resolved


@then("project discovery should return no projects")
def then_project_returns_no_projects(context: object) -> None:
    assert context.project_dirs == []


@then('configuration path lookup should fail with "project not initialized"')
def then_config_path_missing(context: object) -> None:
    assert context.project_error == "project not initialized"


@then('project discovery should fail with "Permission denied"')
def then_project_permission_denied(context: object) -> None:
    assert context.project_error is not None
    assert "Permission denied" in context.project_error
