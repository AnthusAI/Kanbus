"""Behave steps for issue creation."""

from __future__ import annotations

from behave import then, when
from pathlib import Path
from types import SimpleNamespace

from features.steps.shared import (
    capture_issue_identifier,
    load_project_directory,
    read_issue_file,
    run_cli,
)
from taskulus.issue_creation import IssueCreationError, create_issue


@when('I run "tsk create Implement OAuth2 flow"')
def when_run_create_default(context: object) -> None:
    run_cli(context, "tsk create Implement OAuth2 flow")


@when('I run "tsk create implement oauth2 flow"')
def when_run_create_duplicate_title(context: object) -> None:
    run_cli(context, "tsk create implement oauth2 flow")


@when(
    'I run "tsk create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent tsk-epic01 --label auth --label urgent --description \\"Bug in login\\""'
)
def when_run_create_full(context: object) -> None:
    run_cli(
        context,
        "tsk create Fix login bug --type bug --priority 1 --assignee dev@example.com "
        '--parent tsk-epic01 --label auth --label urgent --description "Bug in login"',
    )


@when('I run "tsk create Bad Issue --type nonexistent"')
def when_run_create_invalid_type(context: object) -> None:
    run_cli(context, "tsk create Bad Issue --type nonexistent")


@when('I run "tsk create Orphan --parent tsk-nonexistent"')
def when_run_create_missing_parent(context: object) -> None:
    run_cli(context, "tsk create Orphan --parent tsk-nonexistent")


@when('I run "tsk create"')
def when_run_create_without_title(context: object) -> None:
    run_cli(context, "tsk create")


@when('I run "tsk create Bad Priority --priority 99"')
def when_run_create_invalid_priority(context: object) -> None:
    run_cli(context, "tsk create Bad Priority --priority 99")


@when('I run "tsk create Child Task --type {issue_type} --parent tsk-parent"')
def when_run_create_child_task_with_parent(context: object, issue_type: str) -> None:
    run_cli(
        context,
        f"tsk create Child Task --type {issue_type} --parent tsk-parent",
    )


@when('I run "tsk create Child --type {issue_type} --parent tsk-bug01"')
def when_run_create_child_with_bug_parent(context: object, issue_type: str) -> None:
    run_cli(
        context,
        f"tsk create Child --type {issue_type} --parent tsk-bug01",
    )


@when('I run "tsk create Standalone Task --type task"')
def when_run_create_standalone_task(context: object) -> None:
    run_cli(context, "tsk create Standalone Task --type task")


@when('I run "tsk create Snapshot issue"')
def when_run_create_snapshot_issue(context: object) -> None:
    run_cli(context, "tsk create Snapshot issue")


@when('I create an issue directly with title "Implement OAuth2 flow"')
def when_create_issue_directly(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    root = Path(working_directory)
    try:
        create_issue(
            root=root,
            title="Implement OAuth2 flow",
            issue_type=None,
            priority=None,
            assignee=None,
            parent=None,
            labels=[],
            description="",
            local=False,
        )
    except IssueCreationError as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")


@then("the command should succeed")
def then_command_succeeds(context: object) -> None:
    assert context.result.exit_code == 0


@then("stdout should contain a valid issue ID")
def then_stdout_contains_issue_id(context: object) -> None:
    capture_issue_identifier(context)


@then("an issue file should be created in the issues directory")
def then_issue_file_created(context: object) -> None:
    project_dir = load_project_directory(context)
    issues = list((project_dir / "issues").glob("*.json"))
    assert len(issues) == 1


@then("the issues directory should contain {issue_count:d} issue file")
def then_issues_directory_contains_count(context: object, issue_count: int) -> None:
    project_dir = load_project_directory(context)
    issues = list((project_dir / "issues").glob("*.json"))
    assert len(issues) == issue_count


@then('the created issue should have title "Implement OAuth2 flow"')
def then_created_issue_title(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.title == "Implement OAuth2 flow"


@then('the created issue should have type "task"')
def then_created_issue_type(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.issue_type == "task"


@then('the created issue should have status "open"')
def then_created_issue_status(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.status == "open"


@then("the created issue should have priority 2")
def then_created_issue_priority(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.priority == 2


@then("the created issue should have an empty labels list")
def then_created_issue_labels_empty(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.labels == []


@then("the created issue should have an empty dependencies list")
def then_created_issue_dependencies_empty(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.dependencies == []


@then("the created issue should have a created_at timestamp")
def then_created_issue_created_at(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.created_at is not None


@then("the created issue should have an updated_at timestamp")
def then_created_issue_updated_at(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.updated_at is not None


@then('the created issue should have type "bug"')
def then_created_issue_type_bug(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.issue_type == "bug"


@then("the created issue should have priority 1")
def then_created_issue_priority_one(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.priority == 1


@then('the created issue should have assignee "dev@example.com"')
def then_created_issue_assignee(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.assignee == "dev@example.com"


@then('the created issue should have parent "tsk-epic01"')
def then_created_issue_parent(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.parent == "tsk-epic01"


@then('the created issue should have labels "auth, urgent"')
def then_created_issue_labels(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.labels == ["auth", "urgent"]


@then('the created issue should have description "Bug in login"')
def then_created_issue_description(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.description == "Bug in login"


@then("the created issue should have no parent")
def then_created_issue_no_parent(context: object) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.parent is None
