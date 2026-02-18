"""Behave steps for issue display."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import click
from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from kanbus.config_loader import load_project_configuration
from kanbus.issue_display import format_issue_for_display
from kanbus.models import DependencyLink, IssueComment


@given('an issue "kanbus-aaa" exists with title "Implement OAuth2 flow"')
def given_issue_exists_with_title(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-aaa", "Implement OAuth2 flow", "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('an issue "kanbus-desc" exists with title "Describe me"')
def given_issue_desc_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-desc", "Describe me", "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "kanbus-aaa" has status "open" and type "task"')
def given_issue_status_and_type(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    issue = issue.model_copy(update={"status": "open", "issue_type": "task"})
    write_issue_file(project_dir, issue)


@when('I run "kanbus show kanbus-aaa"')
def when_run_show(context: object) -> None:
    run_cli(context, "kanbus show kanbus-aaa")


@when('I run "kanbus show kanbus-desc"')
def when_run_show_desc(context: object) -> None:
    run_cli(context, "kanbus show kanbus-desc")


@when('I run "kanbus show kanbus-aaa --json"')
def when_run_show_json(context: object) -> None:
    run_cli(context, "kanbus show kanbus-aaa --json")


@when('I run "kanbus show kanbus-labels"')
def when_run_show_labels(context: object) -> None:
    run_cli(context, "kanbus show kanbus-labels")


@when('I run "kanbus show kanbus-missing"')
def when_run_show_missing(context: object) -> None:
    run_cli(context, "kanbus show kanbus-missing")


@when('I format issue "kanbus-labels" for display')
def when_format_issue_for_display(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-labels")
    context.formatted_output = format_issue_for_display(issue)


@when('I format issue "{identifier}" for display')
def when_format_issue_for_display_generic(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    context.formatted_output = format_issue_for_display(issue)


@when('I format issue "{identifier}" for display with color enabled')
def when_format_issue_for_display_with_color(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    config_path = project_dir.parent / ".kanbus.yml"
    configuration = (
        load_project_configuration(config_path) if config_path.exists() else None
    )
    command = click.Command("test")
    click_context = click.Context(command, color=True)
    with click_context.scope():
        context.formatted_output = format_issue_for_display(
            issue, configuration=configuration
        )


@when(
    'I format issue "{identifier}" for display with color enabled without configuration'
)
def when_format_issue_display_without_configuration(
    context: object, identifier: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    command = click.Command("test")
    click_context = click.Context(command, color=True)
    with click_context.scope():
        context.formatted_output = format_issue_for_display(issue, configuration=None)


@when('I format issue "{identifier}" for display with NO_COLOR set')
def when_format_issue_display_no_color(context: object, identifier: str) -> None:
    if not hasattr(context, "original_no_color"):
        context.original_no_color = os.environ.get("NO_COLOR")
    os.environ["NO_COLOR"] = "1"
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    context.formatted_output = format_issue_for_display(issue, configuration=None)


@then("the formatted output should contain ANSI color codes")
def then_formatted_output_contains_ansi(context: object) -> None:
    output = getattr(context, "formatted_output", "")
    assert "\x1b[" in output


@then('the formatted output should contain text "{text}"')
def then_formatted_output_contains_text(context: object, text: str) -> None:
    output = getattr(context, "formatted_output", "")
    assert text in output


@given('issue "{identifier}" has dependency "{target}" of type "{dependency_type}"')
def given_issue_has_dependency(
    context: object, identifier: str, target: str, dependency_type: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    dependency = DependencyLink(target=target, type=dependency_type)
    issue = issue.model_copy(update={"dependencies": [dependency]})
    write_issue_file(project_dir, issue)


@given(
    'issue "{identifier}" has a comment from "{author}" with text "{text}" and no id'
)
def given_issue_comment_no_id(
    context: object, identifier: str, author: str, text: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    comment = IssueComment(
        id=None,
        author=author,
        text=text,
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
    )
    issue = issue.model_copy(update={"comments": [comment]})
    write_issue_file(project_dir, issue)


@given(
    'issue "{identifier}" has a comment from "{author}" with text "{text}" and id "{comment_id}"'
)
def given_issue_comment_with_id(
    context: object, identifier: str, author: str, text: str, comment_id: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    comment = IssueComment(
        id=comment_id,
        author=author,
        text=text,
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
    )
    issue = issue.model_copy(update={"comments": [comment]})
    write_issue_file(project_dir, issue)
