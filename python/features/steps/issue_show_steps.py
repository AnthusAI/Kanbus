"""Behave steps for issue display."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import click
from behave import given, then, when

from features.steps.shared import (
    build_issue,
    ensure_git_repository,
    load_project_directory,
    read_issue_file,
    write_default_kanbus_config,
    write_issue_file,
)
from kanbus.config_loader import load_project_configuration
from kanbus.issue_display import format_issue_for_display
from kanbus.models import DependencyLink, IssueComment


@given('an issue "{identifier}" exists with title "{title}"')
def given_issue_exists_with_title_generic(
    context: object, identifier: str, title: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, title, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "kanbus-aaa" has status "open" and type "task"')
def given_issue_status_and_type(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    issue = issue.model_copy(update={"status": "open", "issue_type": "task"})
    write_issue_file(project_dir, issue)


@given("a workspace with multiple Kanbus projects and duplicate fragments")
def given_workspace_with_duplicate_fragments(context: object) -> None:
    root = Path(context.temp_dir) / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(root)
    alpha_repo = root / "alpha"
    beta_repo = root / "beta"
    alpha_project = alpha_repo / "project"
    beta_project = beta_repo / "project"
    (alpha_project / "issues").mkdir(parents=True, exist_ok=True)
    (beta_project / "issues").mkdir(parents=True, exist_ok=True)
    write_default_kanbus_config(alpha_repo, project_key="alpha")
    write_default_kanbus_config(beta_repo, project_key="beta")
    write_issue_file(
        alpha_project,
        build_issue("alpha-aaaaaa", "Alpha task", "task", "open", None, []),
    )
    write_issue_file(
        beta_project, build_issue("beta-aaaaaa", "Beta task", "task", "open", None, [])
    )
    context.working_directory = root


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
