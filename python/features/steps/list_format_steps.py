"""Behave steps for list formatting scenarios."""

from __future__ import annotations

import os

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from kanbus.config_loader import load_project_configuration
from kanbus.issue_line import compute_widths, format_issue_line
from kanbus.project import get_configuration_path


@given("issues for list color coverage exist")
def given_issues_for_list_color_coverage(context: object) -> None:
    project_dir = load_project_directory(context)
    issues = [
        build_issue("kanbus-line-epic", "Epic", "epic", "open", None, []),
        build_issue(
            "kanbus-line-task", "Task", "task", "in_progress", "kanbus-line-epic", []
        ),
        build_issue("kanbus-line-bug", "Bug", "bug", "blocked", None, []),
        build_issue("kanbus-line-story", "Story", "story", "closed", None, []),
        build_issue("kanbus-line-chore", "Chore", "chore", "deferred", None, []),
        build_issue(
            "kanbus-line-initiative", "Initiative", "initiative", "unknown", None, []
        ),
        build_issue(
            "kanbus-line-sub", "Sub", "sub-task", "open", "kanbus-line-epic", []
        ),
        build_issue("kanbus-line-event", "Event", "event", "open", None, []),
        build_issue("kanbus-line-unknown", "Unknown", "mystery", "open", None, []),
    ]
    updates = {
        "kanbus-line-epic": {"priority": 0},
        "kanbus-line-task": {"priority": 1},
        "kanbus-line-bug": {"priority": 2},
        "kanbus-line-story": {"priority": 3},
        "kanbus-line-chore": {"priority": 4},
        "kanbus-line-initiative": {"priority": 9},
        "kanbus-line-sub": {"priority": 2},
        "kanbus-line-event": {"priority": 2},
        "kanbus-line-unknown": {"priority": 2},
    }
    identifiers = []
    for issue in issues:
        issue = issue.model_copy(update=updates.get(issue.identifier, {}))
        write_issue_file(project_dir, issue)
        identifiers.append(issue.identifier)
    context.list_color_issue_ids = identifiers


@when("I format list lines for color coverage")
def when_format_list_lines_for_color_coverage(context: object) -> None:
    if not hasattr(context, "original_no_color"):
        context.original_no_color = os.environ.get("NO_COLOR")
    os.environ.pop("NO_COLOR", None)
    project_dir = load_project_directory(context)
    configuration = load_project_configuration(get_configuration_path(project_dir))
    identifiers = getattr(context, "list_color_issue_ids", [])
    issues = [read_issue_file(project_dir, identifier) for identifier in identifiers]
    widths = compute_widths(issues, project_context=False)
    lines = [
        format_issue_line(
            issue,
            porcelain=False,
            widths=widths,
            project_context=False,
            configuration=configuration,
            use_color=True,
        )
        for issue in issues
    ]
    context.formatted_output = "\n".join(lines)


@when('I format the list line for issue "{identifier}"')
def when_format_list_line_for_issue(context: object, identifier: str) -> None:
    if not hasattr(context, "original_no_color"):
        context.original_no_color = os.environ.get("NO_COLOR")
    os.environ.pop("NO_COLOR", None)
    project_dir = load_project_directory(context)
    configuration = load_project_configuration(get_configuration_path(project_dir))
    issue = read_issue_file(project_dir, identifier)
    widths = compute_widths([issue], project_context=False)
    context.formatted_output = format_issue_line(
        issue,
        porcelain=False,
        widths=widths,
        project_context=False,
        configuration=configuration,
        use_color=True,
    )


@when('I format the list line for issue "{identifier}" with NO_COLOR set')
def when_format_list_line_for_issue_no_color(context: object, identifier: str) -> None:
    if not hasattr(context, "original_no_color"):
        context.original_no_color = os.environ.get("NO_COLOR")
    os.environ["NO_COLOR"] = "1"
    project_dir = load_project_directory(context)
    configuration = load_project_configuration(get_configuration_path(project_dir))
    issue = read_issue_file(project_dir, identifier)
    widths = compute_widths([issue], project_context=False)
    context.formatted_output = format_issue_line(
        issue,
        porcelain=False,
        widths=widths,
        project_context=False,
        configuration=configuration,
    )


@then("each formatted line should contain ANSI color codes")
def then_each_formatted_line_contains_ansi(context: object) -> None:
    output = getattr(context, "formatted_output", "")
    lines = [line for line in output.splitlines() if line.strip()]
    assert lines, "no formatted lines"
    assert all("\x1b[" in line for line in lines)


@then("the formatted output should contain no ANSI color codes")
def then_formatted_output_has_no_ansi(context: object) -> None:
    output = getattr(context, "formatted_output", "")
    lines = [line for line in output.splitlines() if line.strip()]
    assert lines, "no formatted lines"
    assert all("\x1b[" not in line for line in lines)
