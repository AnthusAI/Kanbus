"""Behave steps for compatibility mode."""

from __future__ import annotations

from behave import when

from features.steps.shared import run_cli


@when('I run "tsk --beads list"')
def when_run_list_beads(context: object) -> None:
    run_cli(context, "tsk --beads list")


@when('I run "tsk --beads list --no-local"')
def when_run_list_beads_no_local(context: object) -> None:
    run_cli(context, "tsk --beads list --no-local")


@when('I run "tsk --beads ready"')
def when_run_ready_beads(context: object) -> None:
    run_cli(context, "tsk --beads ready")


@when('I run "tsk --beads ready --no-local"')
def when_run_ready_beads_no_local(context: object) -> None:
    run_cli(context, "tsk --beads ready --no-local")


@when('I run "tsk --beads show bdx-epic"')
def when_run_show_beads(context: object) -> None:
    run_cli(context, "tsk --beads show bdx-epic")


@when('I run "tsk --beads show bdx-missing"')
def when_run_show_missing_beads(context: object) -> None:
    run_cli(context, "tsk --beads show bdx-missing")
