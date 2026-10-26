"""Behave steps for query scenarios."""

from __future__ import annotations

from behave import given, then, when
from pathlib import Path
from types import SimpleNamespace

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from features.steps.shared import initialize_default_project
from kanbus.config_loader import load_project_configuration
from kanbus.issue_listing import _list_issues_with_local
from kanbus.project import get_configuration_path


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
    project_dir = _resolve_issue_project_directory(context, identifier)
    issue_path = project_dir / "issues" / f"{identifier}.json"
    if issue_path.exists():
        issue = read_issue_file(project_dir, identifier)
        issue = issue.model_copy(update={"status": status})
    else:
        issue = build_issue(identifier, "Title", "task", status, None, [])
    write_issue_file(project_dir, issue)


def _resolve_issue_project_directory(context: object, identifier: str) -> Path:
    virtual_state = getattr(context, "virtual_project_state", None)
    if virtual_state is not None:
        for project in virtual_state.virtual_projects.values():
            if (project.shared_dir / "issues" / f"{identifier}.json").exists():
                return project.shared_dir
            if (project.local_dir / "issues" / f"{identifier}.json").exists():
                return project.local_dir
        return virtual_state.current_project_dir
    return load_project_directory(context)


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
    try:
        issue = read_issue_file(project_dir, identifier)
    except FileNotFoundError:
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


@when("I list issues directly after configuration path lookup fails")
def when_list_issues_directly_after_configuration_failure(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    from kanbus.issue_listing import list_issues

    try:
        list_issues(Path(working_directory))
    except RuntimeError as error:
        context.result = SimpleNamespace(
            exit_code=1, stdout="", stderr=str(error), output=str(error)
        )
        return
    context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")


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
    root = Path(context.working_directory)
    configuration = load_project_configuration(get_configuration_path(root))
    issues = _list_issues_with_local(
        project_dir,
        local_dir,
        include_local=False,
        local_only=False,
        overlay_config=configuration.overlay,
        project_label=configuration.project_key,
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


@then('stdout should contain the line "{expected}"')
def then_stdout_contains_line(context: object, expected: str) -> None:
    lines = context.result.stdout.splitlines()
    assert expected in lines
