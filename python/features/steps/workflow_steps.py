"""Behave steps for workflow and hierarchy scenarios."""

from __future__ import annotations

from datetime import datetime, timezone

import copy

import yaml
from behave import given, then, when

from features.steps.shared import (
    build_issue,
    initialize_default_project,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.models import ProjectConfiguration
from taskulus.workflows import get_workflow_for_issue_type


@given('an issue "{identifier}" of type "{issue_type}" with status "{status}"')
def given_issue_with_type_and_status(
    context: object, identifier: str, issue_type: str, status: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", issue_type, status, None, [])
    if status == "closed":
        issue = issue.model_copy(
            update={"closed_at": datetime(2026, 2, 11, tzinfo=timezone.utc)}
        )
    write_issue_file(project_dir, issue)


@given('an issue "{identifier}" exists')
def given_issue_exists(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('an issue "{identifier}" exists with status "{status}"')
def given_issue_exists_with_status(
    context: object, identifier: str, status: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", status, None, [])
    if status == "closed":
        issue = issue.model_copy(
            update={"closed_at": datetime(2026, 2, 11, tzinfo=timezone.utc)}
        )
    write_issue_file(project_dir, issue)


@given('a "{issue_type}" issue "{identifier}" exists')
def given_typed_issue_exists(context: object, issue_type: str, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", issue_type, "open", None, [])
    write_issue_file(project_dir, issue)


@given('an "{issue_type}" issue "{identifier}" exists')
def given_typed_issue_exists_an(
    context: object, issue_type: str, identifier: str
) -> None:
    given_typed_issue_exists(context, issue_type, identifier)


@given('issue "{identifier}" has no closed_at timestamp')
def given_issue_no_closed_at(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue = issue.model_copy(update={"closed_at": None})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has a closed_at timestamp')
def given_issue_has_closed_at(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue = issue.model_copy(
        update={"closed_at": datetime(2026, 2, 11, tzinfo=timezone.utc)}
    )
    write_issue_file(project_dir, issue)


@then('issue "{identifier}" should have status "{status}"')
def then_issue_status_matches(context: object, identifier: str, status: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.status == status


@then('issue "{identifier}" should have assignee "{assignee}"')
def then_issue_assignee_matches(
    context: object, identifier: str, assignee: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.assignee == assignee


@then('issue "{identifier}" should have a closed_at timestamp')
def then_issue_has_closed_at(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.closed_at is not None


@then('issue "{identifier}" should have no closed_at timestamp')
def then_issue_no_closed_at(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.closed_at is None


@given("a configuration without a default workflow")
def given_config_without_default_workflow(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["workflows"] = {"epic": {"open": ["in_progress"]}}
    config_path = project_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@when('I look up the workflow for issue type "{issue_type}"')
def when_lookup_workflow(context: object, issue_type: str) -> None:
    project_dir = load_project_directory(context)
    config_path = project_dir / "config.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    context.workflow_error = None
    try:
        configuration = ProjectConfiguration.model_validate(data)
        get_workflow_for_issue_type(configuration, issue_type)
    except ValueError as error:
        context.workflow_error = str(error)


@then('workflow lookup should fail with "default workflow not defined"')
def then_workflow_lookup_failed(context: object) -> None:
    assert context.workflow_error == "default workflow not defined"
