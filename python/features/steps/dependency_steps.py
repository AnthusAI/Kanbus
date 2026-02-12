"""Behave steps for dependency scenarios."""

from __future__ import annotations

from behave import given, then, when

from dataclasses import dataclass

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from taskulus.dependencies import DependencyError, add_dependency
from taskulus.models import DependencyLink


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


@when('I run "tsk dep add tsk-child --blocked-by tsk-parent"')
def when_run_dep_add_blocked(context: object) -> None:
    from features.steps.shared import run_cli

    run_cli(context, "tsk dep add tsk-child --blocked-by tsk-parent")


@when('I run "tsk dep add tsk-left --relates-to tsk-right"')
def when_run_dep_add_relates(context: object) -> None:
    from features.steps.shared import run_cli

    run_cli(context, "tsk dep add tsk-left --relates-to tsk-right")


@when('I run "tsk dep add tsk-left --blocked-by tsk-right"')
def when_run_dep_add_blocked_left(context: object) -> None:
    run_cli(context, "tsk dep add tsk-left --blocked-by tsk-right")


@when('I run "tsk dep remove tsk-left --blocked-by tsk-right"')
def when_run_dep_remove(context: object) -> None:
    run_cli(context, "tsk dep remove tsk-left --blocked-by tsk-right")


@when('I run "tsk dep remove tsk-left --relates-to tsk-right"')
def when_run_dep_remove_relates(context: object) -> None:
    run_cli(context, "tsk dep remove tsk-left --relates-to tsk-right")


@when('I run "tsk dep add tsk-b --blocked-by tsk-a"')
def when_run_dep_add_cycle(context: object) -> None:
    run_cli(context, "tsk dep add tsk-b --blocked-by tsk-a")


@when('I run "tsk dep add tsk-a --blocked-by tsk-c"')
def when_run_dep_add_shared_downstream(context: object) -> None:
    run_cli(context, "tsk dep add tsk-a --blocked-by tsk-c")


@when('I run "tsk dep add tsk-missing --blocked-by tsk-parent"')
def when_run_dep_add_missing_issue(context: object) -> None:
    run_cli(context, "tsk dep add tsk-missing --blocked-by tsk-parent")


@when('I run "tsk ready"')
def when_run_ready(context: object) -> None:
    run_cli(context, "tsk ready")


@when('I run "tsk ready --local-only --no-local"')
def when_run_ready_conflict(context: object) -> None:
    run_cli(context, "tsk ready --local-only --no-local")


@when('I run "tsk ready --local-only"')
def when_run_ready_local_only(context: object) -> None:
    run_cli(context, "tsk ready --local-only")


@when('I run "tsk ready --no-local"')
def when_run_ready_no_local(context: object) -> None:
    run_cli(context, "tsk ready --no-local")


@when('I run "tsk dep tree tsk-child"')
def when_run_dep_tree_child(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-child")


@when('I run "tsk dep tree tsk-c --depth 1"')
def when_run_dep_tree_depth(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-c --depth 1")


@when('I run "tsk dep tree tsk-root"')
def when_run_dep_tree_root(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-root")


@when('I run "tsk dep tree tsk-missing"')
def when_run_dep_tree_missing(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-missing")


@when('I run "tsk dep tree tsk-a"')
def when_run_dep_tree_a(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-a")


@when('I run "tsk dep tree tsk-child --format json"')
def when_run_dep_tree_json(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-child --format json")


@when('I run "tsk dep tree tsk-child --format dot"')
def when_run_dep_tree_dot(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-child --format dot")


@when('I run "tsk dep tree tsk-child --format invalid"')
def when_run_dep_tree_invalid(context: object) -> None:
    run_cli(context, "tsk dep tree tsk-child --format invalid")


@given("a dependency tree with more than 25 nodes exists")
def given_large_dependency_tree(context: object) -> None:
    project_dir = load_project_directory(context)
    chain_length = 26
    for index in range(chain_length):
        identifier = "tsk-root" if index == 0 else f"tsk-node-{index}"
        issue = build_issue(identifier, f"Node {index}", "task", "open", None, [])
        if index < chain_length - 1:
            target = f"tsk-node-{index + 1}"
            issue = issue.model_copy(
                update={
                    "dependencies": [DependencyLink(target=target, type="blocked-by")]
                }
            )
        write_issue_file(project_dir, issue)


@when('I run "tsk dep add tsk-child"')
def when_run_dep_add_missing_target(context: object) -> None:
    run_cli(context, "tsk dep add tsk-child")


@when('I run "tsk dep remove tsk-child"')
def when_run_dep_remove_missing_target(context: object) -> None:
    run_cli(context, "tsk dep remove tsk-child")


@when('I run "tsk dep remove tsk-missing --blocked-by tsk-parent"')
def when_run_dep_remove_missing_issue(context: object) -> None:
    run_cli(context, "tsk dep remove tsk-missing --blocked-by tsk-parent")


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
        add_dependency(root, "tsk-left", "tsk-right", "invalid-type")
    except DependencyError as error:
        context.result = _DummyResult(exit_code=1, stdout="", stderr=str(error))
        return
    context.result = _DummyResult(exit_code=0, stdout="", stderr="")


@then('issue "{identifier}" should have 1 dependency')
def then_issue_has_single_dependency(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert len(issue.dependencies) == 1
