"""Behave steps for issue creation."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    capture_issue_identifier,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)


@given('an "epic" issue "tsk-epic01" exists')
def given_epic_issue_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-epic01", "Epic", "epic", "open", None, [])
    write_issue_file(project_dir, issue)


@when('I run "tsk create Implement OAuth2 flow"')
def when_run_create_default(context: object) -> None:
    run_cli(context, "tsk create Implement OAuth2 flow")


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


@then('stderr should contain "unknown issue type"')
def then_stderr_contains_unknown_type(context: object) -> None:
    assert "unknown issue type" in context.result.stderr


@then('stderr should contain "not found"')
def then_stderr_contains_not_found(context: object) -> None:
    assert "not found" in context.result.stderr
