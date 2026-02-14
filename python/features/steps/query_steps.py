"""Behave steps for query scenarios."""

from __future__ import annotations

from behave import given, then, when
import os
from pathlib import Path
from types import SimpleNamespace
import click

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from features.steps.shared import initialize_default_project
from kanbus.cli import list_command
from kanbus.issue_listing import _list_issues_with_local


@given('issues "{first}" and "{second}" exist')
def given_issues_exist(context: object, first: str, second: str) -> None:
    project_dir = load_project_directory(context)
    for identifier in (first, second):
        issue = build_issue(identifier, "Title", "task", "open", None, [])
        write_issue_file(project_dir, issue)


@given('issues "{identifier}" exist')
def given_single_issue_exists(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has status "{status}"')
def given_issue_has_status(context: object, identifier: str, status: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", status, None, [])
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has type "{issue_type}"')
def given_issue_has_type(context: object, identifier: str, issue_type: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", issue_type, "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has assignee "{assignee}"')
def given_issue_has_assignee(context: object, identifier: str, assignee: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"assignee": assignee})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has labels "{label_text}"')
def given_issue_has_labels(context: object, identifier: str, label_text: str) -> None:
    project_dir = load_project_directory(context)
    labels = [item.strip() for item in label_text.split(",") if item.strip()]
    issue = build_issue(identifier, "Title", "task", "open", None, labels)
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has priority {priority}')
def given_issue_has_priority(context: object, identifier: str, priority: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"priority": int(priority)})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has parent "{parent}"')
def given_issue_has_parent(context: object, identifier: str, parent: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue = issue.model_copy(update={"parent": parent})
    write_issue_file(project_dir, issue)


@given("a Kanbus repository with an unreadable project directory")
def given_repo_with_unreadable_project_directory(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    original_mode = project_dir.stat().st_mode
    project_dir.chmod(0)
    context.unreadable_path = project_dir
    context.unreadable_mode = original_mode


@given(
    'an issue "{identifier}" exists with status "{status}", priority {priority}, type "{issue_type}", and assignee "{assignee}"'
)
def given_issue_with_full_metadata(
    context: object,
    identifier: str,
    status: str,
    priority: str,
    issue_type: str,
    assignee: str,
) -> None:
    project_dir = load_project_directory(context)
    try:
        issue = read_issue_file(project_dir, identifier)
    except FileNotFoundError:
        issue = build_issue(identifier, "Title", issue_type, status, None, [])
    issue = issue.model_copy(
        update={
            "status": status,
            "priority": int(priority),
            "issue_type": issue_type,
            "assignee": assignee,
        }
    )
    write_issue_file(project_dir, issue)


@when('I run "kanbus --help"')
def when_run_help(context: object) -> None:
    run_cli(context, "kanbus --help")


@when('I run "kanbus --unknown"')
def when_run_unknown(context: object) -> None:
    run_cli(context, "kanbus --unknown")


@when('I run "kanbus console snapshot"')
def when_run_console_snapshot(context: object) -> None:
    run_cli(context, "kanbus console snapshot")


@when("I list issues directly after configuration path lookup fails")
def when_list_issues_directly_after_configuration_failure(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    previous = Path.cwd()
    try:
        os.chdir(working_directory)
        from kanbus.config_loader import ConfigurationError

        click_context = click.Context(list_command)
        click_context.obj = {"beads_mode": False, "beads_mode_forced": False}
        original_loader = None
        original_get_config = None
        original_list_issues = None
        try:

            def _raise_configuration_error(_: Path) -> Path:
                raise ConfigurationError("configuration path lookup failed")

            def _raise_on_load(_: Path) -> object:
                raise ConfigurationError("configuration path lookup failed")

            globals_dict = list_command.callback.__wrapped__.__globals__  # type: ignore[attr-defined]
            original_loader = globals_dict.get("load_project_configuration")
            original_get_config = globals_dict.get("get_configuration_path")
            original_list_issues = globals_dict.get("list_issues")
            globals_dict["load_project_configuration"] = _raise_on_load
            globals_dict["get_configuration_path"] = _raise_configuration_error
            globals_dict["list_issues"] = lambda *args, **kwargs: []
            list_command.callback.__wrapped__(  # type: ignore[attr-defined]
                click_context,
                status=None,
                issue_type=None,
                assignee=None,
                label=None,
                sort=None,
                search=None,
                no_local=False,
                local_only=False,
                limit=50,
                porcelain=False,
            )
        except click.ClickException as error:
            context.result = SimpleNamespace(
                exit_code=1,
                stdout="",
                stderr=str(error),
                output=str(error),
            )
            return
        finally:
            globals_dict = list_command.callback.__wrapped__.__globals__  # type: ignore[attr-defined]
            if original_loader is not None:
                globals_dict["load_project_configuration"] = original_loader
            if original_get_config is not None:
                globals_dict["get_configuration_path"] = original_get_config
            if original_list_issues is not None:
                globals_dict["list_issues"] = original_list_issues
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")
    finally:
        os.chdir(previous)


@given('issue "{identifier}" has title "{title}"')
def given_issue_has_title(context: object, identifier: str, title: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, title, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has description "{description}"')
def given_issue_has_description(
    context: object, identifier: str, description: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"description": description})
    write_issue_file(project_dir, issue)


@when('I run "kanbus list --status open"')
def when_run_list_status(context: object) -> None:
    run_cli(context, "kanbus list --status open")


@when('I run "kanbus list --type task"')
def when_run_list_type(context: object) -> None:
    run_cli(context, "kanbus list --type task")


@when('I run "kanbus list --assignee dev@example.com"')
def when_run_list_assignee(context: object) -> None:
    run_cli(context, "kanbus list --assignee dev@example.com")


@when('I run "kanbus list --label auth"')
def when_run_list_label(context: object) -> None:
    run_cli(context, "kanbus list --label auth")


@when('I run "kanbus list --sort priority"')
def when_run_list_sort(context: object) -> None:
    run_cli(context, "kanbus list --sort priority")


@when('I run "kanbus list --search login"')
def when_run_list_search(context: object) -> None:
    run_cli(context, "kanbus list --search login")


@when('I run "kanbus list --search Searchable"')
def when_run_list_search_comment(context: object) -> None:
    run_cli(context, "kanbus list --search Searchable")


@when('I run "kanbus list --search Dup"')
def when_run_list_search_dup(context: object) -> None:
    run_cli(context, "kanbus list --search Dup")


@when('I run "kanbus list --sort invalid"')
def when_run_list_invalid_sort(context: object) -> None:
    run_cli(context, "kanbus list --sort invalid")


@when('I run "kanbus list --no-local"')
def when_run_list_no_local(context: object) -> None:
    run_cli(context, "kanbus list --no-local")


@when('I run "kanbus list --local-only"')
def when_run_list_local_only(context: object) -> None:
    run_cli(context, "kanbus list --local-only")


@when('I run "kanbus list --local-only --no-local"')
def when_run_list_local_conflict(context: object) -> None:
    run_cli(context, "kanbus list --local-only --no-local")


@given("the daemon list request will fail")
def given_daemon_list_request_fails(context: object) -> None:
    import kanbus.issue_listing as issue_listing

    context.original_request_index_list = issue_listing.request_index_list

    def fake_request(root: object) -> list[object]:
        raise RuntimeError("daemon error")

    issue_listing.request_index_list = fake_request


@given("local listing will fail")
def given_local_listing_fails(context: object) -> None:
    import kanbus.issue_listing as issue_listing

    project_dir = load_project_directory(context)
    (project_dir.parent / "project-local" / "issues").mkdir(parents=True, exist_ok=True)
    context.original_load_issues = issue_listing._load_issues_from_directory

    def fake_list(*_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("local listing failed")

    issue_listing._load_issues_from_directory = fake_list


@when("shared issues are listed without local issues")
def when_shared_only_listed(context: object) -> None:
    project_dir = load_project_directory(context)
    local_dir = project_dir.parent / "project-local"
    local_dir.mkdir(parents=True, exist_ok=True)
    issues = _list_issues_with_local(
        project_dir,
        local_dir,
        include_local=False,
        local_only=False,
    )
    context.shared_only_results = issues


@then('the shared-only list should contain "{identifier}"')
def then_shared_only_contains(context: object, identifier: str) -> None:
    issues = getattr(context, "shared_only_results", [])
    assert any(issue.identifier == identifier for issue in issues)


@then('the shared-only list should not contain "{identifier}"')
def then_shared_only_not_contains(context: object, identifier: str) -> None:
    issues = getattr(context, "shared_only_results", [])
    assert not any(issue.identifier == identifier for issue in issues)


@when('I run "kanbus list --porcelain"')
def when_run_list_porcelain(context: object) -> None:
    run_cli(context, "kanbus list --porcelain")


@then('stdout should contain the line "{expected}"')
def then_stdout_contains_line(context: object, expected: str) -> None:
    lines = context.result.stdout.splitlines()
    assert expected in lines
