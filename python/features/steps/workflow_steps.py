"""Behave steps for workflow and hierarchy scenarios."""

from __future__ import annotations

from datetime import datetime, timezone

import copy

import yaml
from behave import given, then, use_step_matcher, when

from features.steps.shared import (
    build_issue,
    initialize_default_project,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.models import ProjectConfiguration
from kanbus.workflows import get_workflow_for_issue_type


def _parse_labels(labels_csv: str) -> list[str]:
    return [label.strip() for label in labels_csv.split(",") if label.strip()]


def _write_issue_with_overrides(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    *,
    title: str = "Title",
    description: str = "",
    parent: str | None = None,
    labels: list[str] | None = None,
    assignee: str | None = None,
    priority: int = 2,
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(
        identifier,
        title,
        issue_type,
        status,
        parent,
        labels or [],
    )
    update_fields = {
        "description": description,
        "assignee": assignee,
        "priority": priority,
    }
    if status == "closed":
        update_fields["closed_at"] = datetime(2026, 2, 11, tzinfo=timezone.utc)
    issue = issue.model_copy(update=update_fields)
    write_issue_file(project_dir, issue)


use_step_matcher("re")


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)"'
)
def given_issue_with_type_and_status(
    context: object, identifier: str, issue_type: str, status: str
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
    )


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)" and description "(?P<description>[^"]*)"'
)
def given_issue_with_type_status_and_description(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    description: str,
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        description=description,
    )


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)" and title "(?P<title>[^"]*)"'
)
def given_issue_with_type_status_and_title(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    title: str,
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        title=title,
    )


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)" and assignee "(?P<assignee>[^"]+)"'
)
def given_issue_with_type_status_and_assignee(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    assignee: str,
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        assignee=assignee,
    )


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)" and labels "(?P<labels_csv>[^"]*)"'
)
def given_issue_with_type_status_and_labels(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    labels_csv: str,
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        labels=_parse_labels(labels_csv),
    )


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)" and parent "(?P<parent>[^"]+)"'
)
def given_issue_with_type_status_and_parent(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    parent: str,
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        parent=parent,
    )


@given(
    r'an issue "(?P<identifier>[^"]+)" of type "(?P<issue_type>[^"]+)" with status "(?P<status>[^"]+)" and priority (?P<priority>[0-9]+) and description "(?P<description>[^"]*)"'
)
def given_issue_with_type_status_priority_and_description(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    priority: str,
    description: str,
) -> None:
    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        priority=int(priority),
        description=description,
    )


use_step_matcher("parse")


@given('an issue "{identifier}" exists')
def given_issue_exists(context: object, identifier: str) -> None:
    _write_issue_with_overrides(context, identifier, "task", "open")


@given('an issue "{identifier}" exists with status "{status}"')
def given_issue_exists_with_status(
    context: object, identifier: str, status: str
) -> None:
    _write_issue_with_overrides(context, identifier, "task", status)


@given('a "{issue_type}" issue "{identifier}" exists')
def given_typed_issue_exists(context: object, issue_type: str, identifier: str) -> None:
    _write_issue_with_overrides(context, identifier, issue_type, "open")


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


@then('issue "{identifier}" should have title "{title}"')
def then_issue_title_matches(context: object, identifier: str, title: str) -> None:
    """Verify the issue title matches the expected value."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.title == title


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


@given('epic workflow allows transition from "open" to "ready"')
def given_epic_workflow_allows_ready(context: object) -> None:
    """Extend epic workflow and statuses to include ready transitions."""
    project_dir = load_project_directory(context)
    config_path = project_dir.parent / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    workflows = payload.setdefault("workflows", {})
    epic_workflow = workflows.setdefault("epic", {})
    open_targets = epic_workflow.setdefault("open", [])
    if "ready" not in open_targets:
        open_targets.append("ready")
    epic_workflow.setdefault("ready", ["in_progress", "open", "closed"])

    statuses = payload.setdefault("statuses", [])
    if not any(status.get("key") == "ready" for status in statuses):
        statuses.append(
            {
                "key": "ready",
                "name": "Ready",
                "category": "To do",
                "collapsed": False,
            }
        )

    transition_labels = payload.setdefault("transition_labels", {})
    epic_labels = transition_labels.setdefault("epic", {})
    epic_open_labels = epic_labels.setdefault("open", {})
    epic_open_labels.setdefault("ready", "Mark ready")
    ready_labels = epic_labels.setdefault("ready", {})
    ready_labels.setdefault("in_progress", "Start")
    ready_labels.setdefault("open", "Re-open")
    ready_labels.setdefault("closed", "Complete")

    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


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
