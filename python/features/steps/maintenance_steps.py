"""Behave steps for maintenance scenarios."""

from __future__ import annotations

from behave import given, then, when
from pathlib import Path
from types import SimpleNamespace

from datetime import datetime, timezone
import json
import shutil

from features.steps.shared import (
    build_issue,
    load_project_directory,
    write_issue_file,
)
from kanbus.maintenance import (
    ProjectValidationError,
    _collect_workflow_statuses,
    validate_project,
)
from kanbus.models import DependencyLink
from kanbus.doctor import DoctorError, run_doctor


@when("I validate the project directly")
def when_validate_project_directly(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    root = Path(working_directory)
    try:
        validate_project(root)
    except ProjectValidationError as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")


@when("I run doctor diagnostics directly")
def when_run_doctor_directly(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    root = Path(working_directory)
    try:
        run_doctor(root)
    except DoctorError as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")


@given("an issue file contains invalid JSON")
def given_issue_file_contains_invalid_json(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "invalid.json"
    issue_path.write_text("{invalid json", encoding="utf-8")


@given("an issue file is unreadable")
def given_issue_file_is_unreadable(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "unreadable.json"
    issue_path.mkdir(parents=True, exist_ok=True)


@given("the issues directory is missing")
def given_issues_directory_missing(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    if issues_dir.exists():
        shutil.rmtree(issues_dir)


@given("an issue file contains invalid issue data")
def given_issue_file_contains_invalid_issue_data(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "invalid-data.json"
    issue_path.write_text(json.dumps({"id": "kanbus-bad"}), encoding="utf-8")


@given("an issue file contains out-of-range priority")
def given_issue_file_contains_out_of_range_priority(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-priority", "Priority", "task", "open", None, [])
    issue = issue.model_copy(update={"priority": -1})
    write_issue_file(project_dir, issue)


@given("invalid issues exist with multiple validation errors")
def given_invalid_issues_with_errors(context: object) -> None:
    project_dir = load_project_directory(context)
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)

    issue_unknown = build_issue(
        "kanbus-unknown", "Unknown", "unknown", "open", None, []
    )
    issue_unknown = issue_unknown.model_copy(update={"priority": 99})
    write_issue_file(project_dir, issue_unknown)

    issue_status_bad = build_issue("kanbus-status", "Bad", "task", "bogus", None, [])
    write_issue_file(project_dir, issue_status_bad)

    issue_closed = build_issue("kanbus-closed", "Closed", "task", "closed", None, [])
    issue_closed = issue_closed.model_copy(update={"closed_at": None})
    write_issue_file(project_dir, issue_closed)

    issue_open_closed_at = build_issue("kanbus-open", "Open", "task", "open", None, [])
    issue_open_closed_at = issue_open_closed_at.model_copy(
        update={"closed_at": timestamp}
    )
    write_issue_file(project_dir, issue_open_closed_at)

    issue_mismatch = build_issue(
        "kanbus-mismatch", "Mismatch", "task", "open", None, []
    )
    mismatch_path = project_dir / "issues" / "wrong-id.json"
    mismatch_path.write_text(
        json.dumps(issue_mismatch.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )

    issue_dep = build_issue("kanbus-dep", "Dep", "task", "open", None, [])
    issue_dep = issue_dep.model_copy(
        update={
            "dependencies": [
                DependencyLink(target="kanbus-missing", type="unsupported")
            ]
        }
    )
    write_issue_file(project_dir, issue_dep)

    issue_parent_missing = build_issue(
        "kanbus-orphan", "Orphan", "task", "open", "kanbus-missing", []
    )
    write_issue_file(project_dir, issue_parent_missing)

    issue_parent = build_issue("kanbus-bug", "Bug parent", "bug", "open", None, [])
    write_issue_file(project_dir, issue_parent)
    issue_child = build_issue("kanbus-child", "Child", "task", "open", "kanbus-bug", [])
    write_issue_file(project_dir, issue_child)


@given("duplicate issue identifiers exist")
def given_duplicate_issue_identifiers(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-dup", "Duplicate", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    duplicate_path = project_dir / "issues" / "kanbus-dup-copy.json"
    duplicate_path.write_text(
        json.dumps(issue.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )


@when('workflow statuses are collected for issue type "{issue_type}"')
def when_collect_workflow_statuses(context: object, issue_type: str) -> None:
    configuration = getattr(context, "configuration", None)
    if configuration is None:
        project_dir = load_project_directory(context)
        config_path = project_dir / "config.yaml"
        import yaml
        from kanbus.models import ProjectConfiguration

        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        configuration = ProjectConfiguration.model_validate(data)
    errors: list[str] = []
    statuses = _collect_workflow_statuses(configuration, issue_type, errors)
    context.workflow_status_errors = errors
    context.workflow_statuses = statuses


@then('workflow status collection should fail with "{message}"')
def then_workflow_status_collection_failed(context: object, message: str) -> None:
    errors = getattr(context, "workflow_status_errors", [])
    assert message in errors
