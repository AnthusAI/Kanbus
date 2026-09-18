"""Click commands for deterministic Issue Router operation."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import click

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.issue_router import (
    IssueRouterError,
    RouterContext,
    build_router_plan,
    format_router_plan_text,
    load_router_context,
    record_router_event,
    write_router_control,
)
from kanbus.router_state import publish_router_state
from kanbus.project import ProjectMarkerError, get_configuration_path


@click.group("router")
def router_group() -> None:
    """Plan, run, and control the deterministic Issue Router."""


@router_group.command("plan")
@click.option("--json", "json_output", is_flag=True, help="Print the stable JSON plan.")
def router_plan_command(json_output: bool) -> None:
    """Show which routed packages can start and why others are deferred."""
    context = _load_context()
    try:
        plan = build_router_plan(context)
    except IssueRouterError as error:
        _fail(str(error), 1)
    if json_output:
        click.echo(
            json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
    else:
        click.echo(format_router_plan_text(plan), nl=False)


@router_group.command("run")
@click.option("--once", "run_once", is_flag=True, help="Run one scheduler pass.")
@click.option("--watch", "watch", is_flag=True, help="Keep reconciling until stopped.")
def router_run_command(run_once: bool, watch: bool) -> None:
    """Run one package or continuously reconcile the project board."""
    if run_once == watch:
        _fail("select exactly one of --once or --watch", 2)
    context = _load_context()
    try:
        from kanbus.router_execution import run_router_once, run_router_watch

        if run_once:
            result = run_router_once(context)
            click.echo(
                "Issue Router run completed: "
                f"started={result.started} completed={result.completed} "
                f"review={result.review} failed={result.failed} "
                f"deferred={result.deferred}"
            )
            if result.error is not None:
                _fail(result.error, 1)
            return
        run_router_watch(context)
    except IssueRouterError as error:
        _fail(str(error), 1)
    except KeyboardInterrupt:
        return


@router_group.command("status")
def router_status_command() -> None:
    """Show scheduler state, active package count, and sorted route holds."""
    context = _load_context()
    from kanbus.router_execution import count_active_router_runs

    state = context.control
    scheduler_status = "running" if state.running else "stopped"
    scheduling_status = "paused" if state.paused else "active"
    held_routes = ",".join(sorted(state.held_routes)) or "none"
    click.echo(
        "\n".join(
            [
                f"Issue Router: {scheduler_status}",
                f"Scheduling: {scheduling_status}",
                f"Active runs: {count_active_router_runs(context.project_dir)}",
                f"Held routes: {held_routes}",
            ]
        )
    )


@router_group.command("pause")
def router_pause_command() -> None:
    """Pause new router starts and persist the control event."""
    context = _load_context()
    write_router_control(
        context.root, context.control.model_copy(update={"paused": True})
    )
    _record_control(context.project_dir, "router_paused")
    click.echo("Issue Router paused.")


@router_group.command("resume")
def router_resume_command() -> None:
    """Resume scheduling without changing route holds."""
    context = _load_context()
    write_router_control(
        context.root, context.control.model_copy(update={"paused": False})
    )
    _record_control(context.project_dir, "router_resumed")
    click.echo("Issue Router resumed.")


@router_group.command("hold")
@click.option("--class", "agent_class")
@click.option("--provider-profile")
def router_hold_command(agent_class: str | None, provider_profile: str | None) -> None:
    """Hold new starts for exactly one configured route."""
    context = _load_context()
    target = _route_selector(context, agent_class, provider_profile)
    holds = sorted(set([*context.control.held_routes, target]))
    write_router_control(
        context.root, context.control.model_copy(update={"held_routes": holds})
    )
    _record_control(context.project_dir, "route_held", {"target": target})
    click.echo(f"Held route {target}.")


@router_group.command("unhold")
@click.option("--class", "agent_class")
@click.option("--provider-profile")
def router_unhold_command(
    agent_class: str | None, provider_profile: str | None
) -> None:
    """Release a hold for exactly one configured route."""
    context = _load_context()
    target = _route_selector(context, agent_class, provider_profile)
    holds = sorted(route for route in context.control.held_routes if route != target)
    write_router_control(
        context.root, context.control.model_copy(update={"held_routes": holds})
    )
    _record_control(context.project_dir, "route_unheld", {"target": target})
    click.echo(f"Released hold for route {target}.")


@router_group.command("cancel")
@click.argument("issue_id")
def router_cancel_command(issue_id: str) -> None:
    """Request cancellation for an active package and preserve its checkpoint."""
    context = _load_context()
    from kanbus.router_execution import cancel_router_package

    try:
        checkpoint = cancel_router_package(context, issue_id)
    except IssueRouterError as error:
        _fail(str(error), 1)
    suffix = f"; checkpoint {checkpoint} preserved" if checkpoint else ""
    click.echo(f"Cancelled router package {issue_id}{suffix}.")


@router_group.command("stop")
def router_stop_command() -> None:
    """Stop future scheduler starts after the current package finishes."""
    context = _load_context()
    if not context.control.running:
        click.echo("Issue Router is not running.")
        return
    state = context.control.model_copy(update={"stop_requested": True})
    if count_active_runs(context.project_dir) == 0:
        state = state.model_copy(update={"running": False})
    write_router_control(context.root, state)
    _record_control(context.project_dir, "router_stop_requested")
    click.echo("Issue Router stop requested.")


def _load_context() -> RouterContext:
    try:
        source_root = Path.cwd()
        # Validate configuration without listing issues: issue listing writes
        # a local index cache, which must never be merged into router state.
        configuration = load_project_configuration(get_configuration_path(source_root))
        if configuration.router is None:
            raise IssueRouterError("issue router is not configured")
        from kanbus.router_state import router_state_root

        context = load_router_context(router_state_root(source_root))
        return replace(context, source_root=source_root)
    except (ConfigurationError, IssueRouterError, ProjectMarkerError) as error:
        message = str(error)
        _fail(message, 2 if message == "issue router is not configured" else 1)


def _route_selector(
    context: RouterContext,
    agent_class: str | None,
    provider_profile: str | None,
) -> str:
    if bool(agent_class) == bool(provider_profile):
        _fail("select exactly one of --class or --provider-profile", 2)
    if agent_class is not None:
        if agent_class not in context.router.classes:
            _fail(f'unknown agent class "{agent_class}"', 2)
        return f"class:{agent_class}"
    assert provider_profile is not None
    if provider_profile not in context.router.providers:
        _fail(f'unknown provider profile "{provider_profile}"', 2)
    return f"provider-profile:{provider_profile}"


def _record_control(
    project_dir: Path,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> None:
    record_router_event(
        project_dir,
        package_id="control",
        event_type=event_type,
        payload=payload or {},
    )
    publish_router_state(project_dir)


def count_active_runs(project_dir: Path) -> int:
    from kanbus.router_execution import count_active_router_runs

    return count_active_router_runs(project_dir)


def _fail(message: str, exit_code: int) -> NoReturn:
    click.echo(f"error: {message}", err=True)
    raise click.exceptions.Exit(exit_code)


__all__ = ["router_group"]
