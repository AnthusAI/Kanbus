"""Behave steps for issue creation."""

from __future__ import annotations

from behave import given, then, when
from pathlib import Path
from types import SimpleNamespace

from features.steps.shared import (
    capture_issue_identifier,
    load_project_directory,
    read_issue_file,
)
from kanbus.issue_creation import IssueCreationError, create_issue


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


@given("issue creation status validation fails")
def given_issue_creation_status_validation_fails(context: object) -> None:
    import kanbus.issue_creation as issue_creation
    from kanbus.workflows import InvalidTransitionError

    if not hasattr(context, "original_validate_status_value"):
        context.original_validate_status_value = issue_creation.validate_status_value

    def fake_validate_status_value(*args: object, **kwargs: object) -> None:
        raise InvalidTransitionError("unknown status")

    issue_creation.validate_status_value = fake_validate_status_value


@then("the command should succeed")
def then_command_succeeds(context: object) -> None:
    if context.result.exit_code != 0:
        print(f"Command failed with exit code {context.result.exit_code}")
        print(f"STDOUT: {context.result.stdout}")
        print(f"STDERR: {context.result.stderr}")
        # Some commands may write only to the combined output stream.
        if hasattr(context.result, "output"):
            print(f"OUTPUT: {context.result.output}")
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


@then('the created issue should have parent "{parent_identifier}"')
def then_created_issue_parent(context: object, parent_identifier: str) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.parent == parent_identifier


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
