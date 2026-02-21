"""Behave steps for dependency scenarios."""

from __future__ import annotations

from behave import given, then, when

from dataclasses import dataclass
from pathlib import Path

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from kanbus.dependencies import DependencyError, add_dependency, list_ready_issues
from kanbus.models import DependencyLink


@given('issue "{identifier}" depends on "{target}" with type "{dependency_type}"')
def given_issue_depends_on(
    context: object, identifier: str, target: str, dependency_type: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    dependency = DependencyLink(target=target, type=dependency_type)
    issue = issue.model_copy(update={"dependencies": [dependency]})
    write_issue_file(project_dir, issue)


@then('issue "{identifier}" should depend on "{target}" with type "{dependency_type}"')
def then_issue_should_depend_on(
    context: object, identifier: str, target: str, dependency_type: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert any(
        link.target == target and link.dependency_type == dependency_type
        for link in issue.dependencies
    )


@then(
    'issue "{identifier}" should not depend on "{target}" with type "{dependency_type}"'
)
def then_issue_should_not_depend_on(
    context: object, identifier: str, target: str, dependency_type: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert not any(
        link.target == target and link.dependency_type == dependency_type
        for link in issue.dependencies
    )


@when("ready issues are listed for a single project")
def when_ready_issues_listed_for_single_project(context: object) -> None:
    root = Path(context.working_directory)
    canonical_root = root.resolve()
    issues = list_ready_issues(
        root=canonical_root, include_local=True, local_only=False
    )
    context.ready_issue_ids = [issue.identifier for issue in issues]


@then('the ready list should contain "{identifier}"')
def then_ready_list_should_contain(context: object, identifier: str) -> None:
    ready_ids = getattr(context, "ready_issue_ids", [])
    assert identifier in ready_ids


@given("a dependency tree with more than 25 nodes exists")
def given_large_dependency_tree(context: object) -> None:
    project_dir = load_project_directory(context)
    chain_length = 26
    for index in range(chain_length):
        identifier = "kanbus-root" if index == 0 else f"kanbus-node-{index}"
        issue = build_issue(identifier, f"Node {index}", "task", "open", None, [])
        if index < chain_length - 1:
            target = f"kanbus-node-{index + 1}"
            issue = issue.model_copy(
                update={
                    "dependencies": [DependencyLink(target=target, type="blocked-by")]
                }
            )
        write_issue_file(project_dir, issue)


@dataclass
class _DummyResult:
    exit_code: int
    stdout: str
    stderr: str


@when("I add an invalid dependency type")
def when_add_invalid_dependency_type(context: object) -> None:
    project_dir = load_project_directory(context)
    root = project_dir.parent
    try:
        add_dependency(root, "kanbus-left", "kanbus-right", "invalid-type")
    except DependencyError as error:
        context.result = _DummyResult(exit_code=1, stdout="", stderr=str(error))
        return
    context.result = _DummyResult(exit_code=0, stdout="", stderr="")


@then('issue "{identifier}" should have 1 dependency')
def then_issue_has_single_dependency(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert len(issue.dependencies) == 1
