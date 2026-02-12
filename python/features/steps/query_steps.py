"""Behave steps for query scenarios."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from taskulus.issue_listing import _list_issues_with_local


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


@when('I run "tsk --help"')
def when_run_help(context: object) -> None:
    run_cli(context, "tsk --help")


@when('I run "tsk --unknown"')
def when_run_unknown(context: object) -> None:
    run_cli(context, "tsk --unknown")


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


@when('I run "tsk list --status open"')
def when_run_list_status(context: object) -> None:
    run_cli(context, "tsk list --status open")


@when('I run "tsk list --type task"')
def when_run_list_type(context: object) -> None:
    run_cli(context, "tsk list --type task")


@when('I run "tsk list --assignee dev@example.com"')
def when_run_list_assignee(context: object) -> None:
    run_cli(context, "tsk list --assignee dev@example.com")


@when('I run "tsk list --label auth"')
def when_run_list_label(context: object) -> None:
    run_cli(context, "tsk list --label auth")


@when('I run "tsk list --sort priority"')
def when_run_list_sort(context: object) -> None:
    run_cli(context, "tsk list --sort priority")


@when('I run "tsk list --search login"')
def when_run_list_search(context: object) -> None:
    run_cli(context, "tsk list --search login")


@when('I run "tsk list --search Searchable"')
def when_run_list_search_comment(context: object) -> None:
    run_cli(context, "tsk list --search Searchable")


@when('I run "tsk list --search Dup"')
def when_run_list_search_dup(context: object) -> None:
    run_cli(context, "tsk list --search Dup")


@when('I run "tsk list --sort invalid"')
def when_run_list_invalid_sort(context: object) -> None:
    run_cli(context, "tsk list --sort invalid")


@when('I run "tsk list --no-local"')
def when_run_list_no_local(context: object) -> None:
    run_cli(context, "tsk list --no-local")


@when('I run "tsk list --local-only"')
def when_run_list_local_only(context: object) -> None:
    run_cli(context, "tsk list --local-only")


@when('I run "tsk list --local-only --no-local"')
def when_run_list_local_conflict(context: object) -> None:
    run_cli(context, "tsk list --local-only --no-local")


@then('stdout should list "tsk-high" before "tsk-low"')
def then_stdout_lists_high_before_low(context: object) -> None:
    output = context.result.stdout
    assert output.index("tsk-high") < output.index("tsk-low")


@given("the daemon list request will fail")
def given_daemon_list_request_fails(context: object) -> None:
    import taskulus.issue_listing as issue_listing

    context.original_request_index_list = issue_listing.request_index_list

    def fake_request(root: object) -> list[object]:
        raise RuntimeError("daemon error")

    issue_listing.request_index_list = fake_request


@given("local listing will fail")
def given_local_listing_fails(context: object) -> None:
    import taskulus.issue_listing as issue_listing

    project_dir = load_project_directory(context)
    (project_dir.parent / "project-local" / "issues").mkdir(parents=True, exist_ok=True)
    context.original_list_with_local = issue_listing._list_issues_with_local

    def fake_list(*_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("local listing failed")

    issue_listing._list_issues_with_local = fake_list


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
