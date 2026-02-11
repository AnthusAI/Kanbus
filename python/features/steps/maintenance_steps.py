"""Behave steps for maintenance scenarios."""

from __future__ import annotations

from behave import then, when

from features.steps.shared import run_cli


@when('I run "tsk validate"')
def when_run_validate(context: object) -> None:
    run_cli(context, "tsk validate")


@when('I run "tsk stats"')
def when_run_stats(context: object) -> None:
    run_cli(context, "tsk stats")


@then('stdout should contain "total issues"')
def then_stdout_contains_total(context: object) -> None:
    assert "total issues" in context.result.stdout


@then('stdout should contain "open issues"')
def then_stdout_contains_open(context: object) -> None:
    assert "open issues" in context.result.stdout


@then('stdout should contain "closed issues"')
def then_stdout_contains_closed(context: object) -> None:
    assert "closed issues" in context.result.stdout


@then('stdout should contain "type: task"')
def then_stdout_contains_task(context: object) -> None:
    assert "type: task" in context.result.stdout


@then('stdout should contain "type: bug"')
def then_stdout_contains_bug(context: object) -> None:
    assert "type: bug" in context.result.stdout
