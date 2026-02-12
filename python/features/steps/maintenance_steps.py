"""Behave steps for maintenance scenarios."""

from __future__ import annotations

from behave import given, then, when

from datetime import datetime, timezone
import json
import shutil

from features.steps.shared import (
    build_issue,
    load_project_directory,
    run_cli,
    write_issue_file,
)
from taskulus.maintenance import _collect_workflow_statuses
from taskulus.models import DependencyLink


@when('I run "tsk validate"')
def when_run_validate(context: object) -> None:
    run_cli(context, "tsk validate")


@when('I run "tsk stats"')
def when_run_stats(context: object) -> None:
    run_cli(context, "tsk stats")


@when('I run "tsk doctor"')
def when_run_doctor(context: object) -> None:
    run_cli(context, "tsk doctor")


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
    issue_path.write_text(json.dumps({"id": "tsk-bad"}), encoding="utf-8")


@given("an issue file contains out-of-range priority")
def given_issue_file_contains_out_of_range_priority(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-priority", "Priority", "task", "open", None, [])
    issue = issue.model_copy(update={"priority": -1})
    write_issue_file(project_dir, issue)


@given("invalid issues exist with multiple validation errors")
def given_invalid_issues_with_errors(context: object) -> None:
    project_dir = load_project_directory(context)
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)

    issue_unknown = build_issue("tsk-unknown", "Unknown", "unknown", "open", None, [])
    issue_unknown = issue_unknown.model_copy(update={"priority": 99})
    write_issue_file(project_dir, issue_unknown)

    issue_status_bad = build_issue("tsk-status", "Bad", "task", "bogus", None, [])
    write_issue_file(project_dir, issue_status_bad)

    issue_closed = build_issue("tsk-closed", "Closed", "task", "closed", None, [])
    issue_closed = issue_closed.model_copy(update={"closed_at": None})
    write_issue_file(project_dir, issue_closed)

    issue_open_closed_at = build_issue("tsk-open", "Open", "task", "open", None, [])
    issue_open_closed_at = issue_open_closed_at.model_copy(
        update={"closed_at": timestamp}
    )
    write_issue_file(project_dir, issue_open_closed_at)

    issue_mismatch = build_issue("tsk-mismatch", "Mismatch", "task", "open", None, [])
    mismatch_path = project_dir / "issues" / "wrong-id.json"
    mismatch_path.write_text(
        json.dumps(issue_mismatch.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )

    issue_dep = build_issue("tsk-dep", "Dep", "task", "open", None, [])
    issue_dep = issue_dep.model_copy(
        update={
            "dependencies": [DependencyLink(target="tsk-missing", type="unsupported")]
        }
    )
    write_issue_file(project_dir, issue_dep)

    issue_parent_missing = build_issue(
        "tsk-orphan", "Orphan", "task", "open", "tsk-missing", []
    )
    write_issue_file(project_dir, issue_parent_missing)

    issue_parent = build_issue("tsk-bug", "Bug parent", "bug", "open", None, [])
    write_issue_file(project_dir, issue_parent)
    issue_child = build_issue("tsk-child", "Child", "task", "open", "tsk-bug", [])
    write_issue_file(project_dir, issue_child)


@given("duplicate issue identifiers exist")
def given_duplicate_issue_identifiers(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-dup", "Duplicate", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    duplicate_path = project_dir / "issues" / "tsk-dup-copy.json"
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
        from taskulus.models import ProjectConfiguration

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
