"""Kanbus CLI entry point."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

from kanbus import __version__
from kanbus.file_io import (
    InitializationError,
    detect_repairable_project_issues,
    ensure_git_repository,
    initialize_project,
    repair_project_structure,
)
from kanbus.content_validation import ContentValidationError, validate_code_blocks
from kanbus.rich_text_signals import apply_text_quality_signals, emit_signals
from kanbus.issue_creation import IssueCreationError, create_issue
from kanbus.issue_close import IssueCloseError, close_issue
from kanbus.issue_comment import IssueCommentError, add_comment
from kanbus.issue_delete import (
    IssueDeleteError,
    delete_issue,
    get_descendant_identifiers,
)
from kanbus.beads_write import (
    BeadsDeleteError,
    BeadsWriteError,
    create_beads_issue,
    delete_beads_issue,
    get_beads_descendant_identifiers,
    update_beads_issue,
)
from kanbus.issue_display import format_issue_for_display
from kanbus.models import IssueData
from kanbus.ids import format_issue_key
from kanbus.issue_line import compute_widths, format_issue_line
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.issue_update import IssueUpdateError, update_issue
from kanbus.issue_transfer import IssueTransferError, localize_issue, promote_issue
from kanbus.issue_listing import IssueListingError, list_issues
from kanbus.queries import QueryError
from kanbus.daemon_client import DaemonClientError, request_shutdown, request_status
from kanbus.users import get_current_user
from kanbus.migration import (
    MigrationError,
    load_beads_issue,
    load_beads_issues,
    migrate_from_beads,
    migrate_from_beads_into_project,
)
from kanbus.doctor import DoctorError, run_doctor
from kanbus.maintenance import (
    ProjectStatsError,
    ProjectValidationError,
    collect_project_stats,
    validate_project,
)
from kanbus.dependencies import (
    DependencyError,
    add_dependency,
    list_ready_issues,
    remove_dependency,
)
from kanbus.dependency_tree import (
    DependencyTreeError,
    build_dependency_tree,
    render_dependency_tree,
)
from kanbus.wiki import (
    WikiError,
    WikiRenderRequest,
    list_wiki_pages,
    render_wiki_page,
)
from kanbus.text_editor import (
    TextEditorError,
    edit_view,
    edit_str_replace,
    edit_create,
    edit_insert,
)
from kanbus.console_snapshot import ConsoleSnapshotError, build_console_snapshot
from kanbus.console_ui_state import fetch_console_ui_state
from kanbus.project import ProjectMarkerError, get_configuration_path
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.agents_management import _ensure_project_guard_files, ensure_agents_file
from kanbus.gossip import GossipError, run_gossip_broker, run_gossip_watch
from kanbus.overlay import (
    gc_overlay_for_projects,
    install_overlay_hooks,
    reconcile_overlay_for_projects,
)
from kanbus.hooks import (
    HookEvent,
    HookExecutionError,
    HookPhase,
    list_hooks,
    run_lifecycle_hooks,
    serialize_issue,
    validate_hooks,
)


def _deprecated_console_control(command: str) -> click.ClickException:
    return click.ClickException(
        f"`kanbus console {command}` is deprecated. UI control commands are being migrated to the pub/sub convention and are temporarily unavailable."
    )


def _deprecated_create_focus() -> click.ClickException:
    return click.ClickException(
        "`kanbus create --focus` is deprecated. UI control commands are being migrated to the pub/sub convention and are temporarily unavailable."
    )


def _resolve_beads_mode(context: click.Context, beads_mode: bool) -> tuple[bool, bool]:
    source = context.get_parameter_source("beads_mode")
    if source == click.core.ParameterSource.COMMANDLINE and beads_mode:
        return True, True
    try:
        configuration = load_project_configuration(get_configuration_path(Path.cwd()))
    except ProjectMarkerError:
        return False, False
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error
    return configuration.beads_compatibility, False


def _resolve_beads_root(cwd: Path) -> Path:
    """Resolve the repository root for Beads-mode operations.

    When beads compatibility is enabled, the data lives under `.beads/` at the
    repository root. Users may run `kanbus` from a subdirectory (e.g. `python/`);
    in that case, Beads mode should still work by walking upward.
    """
    try:
        marker = get_configuration_path(cwd)
        return marker.parent
    except (ProjectMarkerError, ConfigurationError):
        pass

    current: Optional[Path] = cwd
    while current is not None:
        if (current / ".beads").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return cwd


@click.group()
@click.version_option(__version__, prog_name="kanbus")
@click.option("--beads", "beads_mode", is_flag=True, default=False)
@click.option("--no-guidance", is_flag=True, default=False)
@click.option("--no-hooks", is_flag=True, default=False)
@click.pass_context
def cli(
    context: click.Context, beads_mode: bool, no_guidance: bool, no_hooks: bool
) -> None:
    """Kanbus issue tracker CLI.

    \b
    Quick start:
      kbs list                           list all issues
      kbs create "Fix bug" --type bug    create an issue
      kbs update <id> --status done      update an issue
      kbs move <id> epic                 change issue type
      kbs comment <id> "Note"            add a comment
      kbs close <id>                     close an issue

    \b
    Issue types:  initiative > epic > story / task / bug > sub-task
    Statuses:     open  in_progress  blocked  done  closed
    Priorities:   0=critical  1=high  2=medium(default)  3=low  4=trivial
    """
    resolved, forced = _resolve_beads_mode(context, beads_mode)
    context.obj = {
        "beads_mode": resolved,
        "beads_mode_forced": forced,
        "no_guidance": no_guidance,
        "no_hooks": no_hooks,
    }
    _maybe_prompt_project_repair(context)


def _should_check_project_structure(context: click.Context) -> bool:
    if context.invoked_subcommand is None:
        return False
    return context.invoked_subcommand not in {"init", "setup", "repair", "edit"}


def _delete_terminal_is_interactive() -> bool:
    if os.getenv("KANBUS_FORCE_INTERACTIVE") == "1":
        return True
    return bool(
        getattr(sys.stdin, "isatty", None)
        and sys.stdin.isatty()
        and getattr(sys.stdout, "isatty", None)
        and sys.stdout.isatty()
    )


def _maybe_prompt_project_repair(context: click.Context) -> None:
    if not _should_check_project_structure(context):
        return
    root = Path.cwd()
    try:
        plan = detect_repairable_project_issues(root, allow_uninitialized=True)
    except PermissionError:
        return
    if plan is None:
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return
    missing = []
    if plan.missing_project_dir:
        missing.append("project/")
    if plan.missing_issues_dir:
        missing.append("project/issues")
    if plan.missing_events_dir:
        missing.append("project/events")
    prompt = (
        f"Project structure incomplete (missing: {', '.join(missing)}). Repair now?"
    )
    if click.confirm(prompt, default=False):
        repair_project_structure(root, plan)
        click.echo("Project structure repaired.", err=True)


@cli.group("setup")
def setup() -> None:
    """Setup utilities for Kanbus."""


@setup.command("agents")
@click.option("--force", is_flag=True, default=False)
def setup_agents(force: bool) -> None:
    """Ensure AGENTS.md contains Kanbus instructions.

    :param force: Overwrite existing Kanbus section without prompting.
    :type force: bool
    """
    root = Path.cwd()
    ensure_agents_file(root, force)
    _ensure_project_guard_files(root)


@cli.command("init")
@click.option("--local", "create_local", is_flag=True, default=False)
def init(create_local: bool) -> None:
    """Initialize a Kanbus project in the current repository.

    :param create_local: Whether to create a project-local directory.
    :type create_local: bool
    """
    root = Path.cwd()
    try:
        ensure_git_repository(root)
        initialize_project(root, create_local)
    except InitializationError as error:
        raise click.ClickException(str(error)) from error
    _maybe_run_setup_agents(root)


def _maybe_run_setup_agents(root: Path) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return
    if click.confirm('Run "kanbus setup agents" now?', default=False):
        ensure_agents_file(root, force=False)


@cli.command("repair")
@click.option("--yes", is_flag=True, default=False)
def repair(yes: bool) -> None:
    """Repair a broken project structure."""
    root = Path.cwd()
    try:
        plan = detect_repairable_project_issues(root, allow_uninitialized=False)
    except ProjectMarkerError as error:
        raise click.ClickException(str(error)) from error
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error

    if plan is None:
        click.echo("Project structure is already healthy.")
        return

    if not yes:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise click.ClickException(
                "project structure requires repair (re-run with --yes)"
            )
        missing = []
        if plan.missing_project_dir:
            missing.append("project/")
        if plan.missing_issues_dir:
            missing.append("project/issues")
        if plan.missing_events_dir:
            missing.append("project/events")
        prompt = (
            f"Project structure incomplete (missing: {', '.join(missing)}). Repair now?"
        )
        if not click.confirm(prompt, default=False):
            click.echo("Repair cancelled.")
            return

    repair_project_structure(root, plan)
    click.echo("Project structure repaired.")


@cli.command("create")
@click.argument("title", nargs=-1)
@click.option("--type", "issue_type")
@click.option("--priority", type=int)
@click.option("--assignee")
@click.option("--parent")
@click.option("--label", "labels", multiple=True)
@click.option("--description", default="")
@click.option("--local", "local_issue", is_flag=True, default=False)
@click.option(
    "--focus",
    "focus_issue",
    is_flag=True,
    default=False,
    help="Deprecated. UI control commands are temporarily unavailable.",
)
@click.option("--no-validate", "no_validate", is_flag=True, default=False)
@click.pass_context
def create(
    context: click.Context,
    title: tuple[str, ...],
    issue_type: str | None,
    priority: int | None,
    assignee: str | None,
    parent: str | None,
    labels: tuple[str, ...],
    description: str,
    local_issue: bool,
    focus_issue: bool,
    no_validate: bool,
) -> None:
    """Create a new issue in the current project.

    \b
    Examples:
      kbs create "Plan the roadmap" --type initiative
      kbs create "Release v1" --type epic --parent <initiative-id>
      kbs create "Implement login" --type task --parent <epic-id>
      kbs create "Fix crash on launch" --type bug --priority 0 --parent <epic-id>

    :param title: Issue title words.
    :type title: tuple[str, ...]
    :param issue_type: Issue type override.
    :type issue_type: str | None
    :param priority: Issue priority override.
    :type priority: int | None
    :param assignee: Issue assignee.
    :type assignee: str | None
    :param parent: Parent issue identifier.
    :type parent: str | None
    :param labels: Issue labels.
    :type labels: tuple[str, ...]
    :param description: Issue description.
    :type description: str
    :param local_issue: Whether to create the issue in project-local.
    :type local_issue: bool
    """
    title_text = " ".join(title).strip()
    description_text = description.strip()
    if not title_text:
        raise click.ClickException("title is required")
    if focus_issue:
        raise _deprecated_create_focus()

    quality_result = None
    if description_text:
        quality_result = apply_text_quality_signals(description_text)
        description_text = quality_result.text

    if not no_validate and description_text:
        try:
            validate_code_blocks(description_text)
        except ContentValidationError as error:
            raise click.ClickException(str(error)) from error

    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    if beads_mode:
        root = _resolve_beads_root(root)
        if local_issue:
            raise click.ClickException("beads mode does not support local issues")
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_CREATE,
            operation={
                "title": title_text,
                "issue_type": issue_type,
                "priority": priority,
                "assignee": assignee,
                "parent": parent,
                "labels": list(labels),
                "description": description_text,
                "local": False,
            },
            root=root,
            beads_mode=True,
        )
        try:
            issue = create_beads_issue(
                root=root,
                title=title_text,
                issue_type=issue_type,
                priority=priority,
                assignee=assignee,
                parent=parent,
                description=description_text,
            )
        except BeadsWriteError as error:
            raise click.ClickException(str(error)) from error
        click.echo(
            format_issue_for_display(
                issue,
                configuration=None,
                project_context=False,
            )
        )
        if quality_result:
            emit_signals(quality_result, "description", issue_id=issue.identifier)
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.AFTER,
            event=HookEvent.ISSUE_CREATE,
            operation={"issue": serialize_issue(issue)},
            root=root,
            beads_mode=True,
        )
        return

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CREATE,
        operation={
            "title": title_text,
            "issue_type": issue_type,
            "priority": priority,
            "assignee": assignee,
            "parent": parent,
            "labels": list(labels),
            "description": description_text,
            "local": local_issue,
        },
        root=root,
        beads_mode=False,
    )
    try:
        result = create_issue(
            root=root,
            title=title_text,
            issue_type=issue_type,
            priority=priority,
            assignee=assignee,
            parent=parent,
            labels=labels,
            description=description_text,
            local=local_issue,
            validate=not no_validate,
        )
    except IssueCreationError as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        format_issue_for_display(
            result.issue,
            configuration=result.configuration,
            project_context=False,
        )
    )
    if quality_result:
        emit_signals(quality_result, "description", issue_id=result.issue.identifier)
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_CREATE,
        operation={"issue": serialize_issue(result.issue)},
        issues_for_policy=[result.issue],
        root=root,
        beads_mode=False,
    )


@cli.command("show")
@click.argument("identifier")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def show(context: click.Context, identifier: str, as_json: bool) -> None:
    """Show details for an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :param as_json: Emit JSON output when set.
    :type as_json: bool
    """
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False

    # Check if beads_compatibility is enabled in config
    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            # Treat unreadable/missing project config as standard Kanbus mode.
            pass

    if beads_mode:
        root = _resolve_beads_root(root)

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_SHOW,
        operation={"identifier": identifier, "as_json": as_json},
        root=root,
        beads_mode=beads_mode,
    )

    if beads_mode:
        try:
            issue = load_beads_issue(root, identifier)
        except MigrationError as error:
            raise click.ClickException(str(error)) from error
        configuration = None
    else:
        try:
            lookup = load_issue_from_project(root, identifier)
        except IssueLookupError as error:
            raise click.ClickException(str(error)) from error
        issue = lookup.issue
        configuration = load_project_configuration(get_configuration_path(root))

    if as_json:
        payload = issue.model_dump(by_alias=True, mode="json")
        click.echo(json.dumps(payload, indent=2, sort_keys=False))
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.AFTER,
            event=HookEvent.ISSUE_SHOW,
            operation={"identifier": identifier, "as_json": True, "issue": payload},
            issues_for_policy=[issue],
            root=root,
            beads_mode=beads_mode,
        )
        return

    all_issues = None
    if not beads_mode:
        try:
            from kanbus.console_snapshot import get_issues_for_root

            all_issues = list(get_issues_for_root(root))
        except Exception:
            pass

    click.echo(
        format_issue_for_display(
            issue,
            configuration=configuration,
            project_context=False,
            all_issues=all_issues,
        )
    )
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_SHOW,
        operation={
            "identifier": identifier,
            "as_json": False,
            "issue": serialize_issue(issue),
        },
        issues_for_policy=[issue],
        root=root,
        beads_mode=beads_mode,
    )


@cli.command("update")
@click.argument("identifier")
@click.option("--title")
@click.option("--description")
@click.option("--status")
@click.option("--priority", type=int)
@click.option("--assignee")
@click.option("--parent")
@click.option("--add-label", "add_labels", multiple=True)
@click.option("--remove-label", "remove_labels", multiple=True)
@click.option("--set-labels", "set_labels")
@click.option("--claim", is_flag=True, default=False)
@click.option("--no-validate", "no_validate", is_flag=True, default=False)
@click.pass_context
def update(
    context: click.Context,
    identifier: str,
    title: str | None,
    description: str | None,
    status: str | None,
    priority: int | None,
    assignee: str | None,
    parent: str | None,
    add_labels: tuple[str, ...],
    remove_labels: tuple[str, ...],
    set_labels: str | None,
    claim: bool,
    no_validate: bool,
) -> None:
    """Update an existing issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :param title: Updated title.
    :type title: str | None
    :param description: Updated description.
    :type description: str | None
    :param status: Updated status.
    :type status: str | None
    :param priority: Updated priority.
    :type priority: int | None
    :param assignee: Updated assignee.
    :type assignee: str | None
    :param parent: Updated parent identifier.
    :type parent: str | None
    :param claim: Whether to claim the issue.
    :type claim: bool
    """
    root = Path.cwd()
    beads_mode = False
    if context.obj:
        beads_mode = bool(context.obj.get("beads_mode"))

    # Check if beads_compatibility is enabled in config
    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            # Treat unreadable/missing project config as standard Kanbus mode.
            pass

    update_quality_result = None
    if description:
        description_text_stripped = description.strip()
        if description_text_stripped:
            update_quality_result = apply_text_quality_signals(
                description_text_stripped
            )
            description = update_quality_result.text

    if not no_validate and description:
        try:
            validate_code_blocks(description)
        except ContentValidationError as error:
            raise click.ClickException(str(error)) from error

    # Parse set_labels if provided
    parsed_set_labels = None
    if set_labels:
        parsed_set_labels = [label.strip() for label in set_labels.split(",")]

    final_assignee = assignee or (get_current_user() if claim else None)

    if beads_mode:
        root = _resolve_beads_root(root)
        if parent is not None:
            raise click.ClickException("parent update not supported in beads mode")
        before_issue = load_beads_issue(root, identifier)
        proposed_issue = before_issue.model_copy(deep=True)
        if status is not None:
            proposed_issue.status = status
        if title:
            proposed_issue.title = title.strip()
        if description:
            proposed_issue.description = description.strip()
        if priority is not None:
            proposed_issue.priority = priority
        if final_assignee is not None:
            proposed_issue.assignee = final_assignee
        if parsed_set_labels is not None:
            proposed_issue.labels = list(parsed_set_labels)
        if add_labels:
            for label in add_labels:
                if label not in proposed_issue.labels:
                    proposed_issue.labels.append(label)
        if remove_labels:
            proposed_issue.labels = [
                label for label in proposed_issue.labels if label not in remove_labels
            ]

        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_UPDATE,
            operation={
                "identifier": identifier,
                "changes": {
                    "title": title.strip() if title else None,
                    "description": description.strip() if description else None,
                    "status": status,
                    "priority": priority,
                    "assignee": final_assignee,
                    "parent": None,
                    "add_labels": list(add_labels),
                    "remove_labels": list(remove_labels),
                    "set_labels": parsed_set_labels,
                },
                "before_issue": serialize_issue(before_issue),
                "proposed_issue": serialize_issue(proposed_issue),
            },
            root=root,
            beads_mode=True,
        )

        if not no_validate:
            from kanbus.policy_context import (
                PolicyContext,
                PolicyOperation,
                StatusTransition,
            )
            from kanbus.policy_evaluator import evaluate_policies
            from kanbus.policy_loader import load_policies
            from kanbus.project import load_project_directory
            from kanbus.workflows import (
                validate_status_transition,
                validate_status_value,
            )

            project_dir: Path | None = None
            configuration = None
            try:
                project_dir = load_project_directory(root)
                configuration = load_project_configuration(
                    get_configuration_path(project_dir)
                )
            except (ProjectMarkerError, ConfigurationError):
                # Beads mode can operate without an initialized Kanbus project.
                project_dir = None
                configuration = None

            if configuration and proposed_issue.status != before_issue.status:
                validate_status_value(
                    configuration, proposed_issue.issue_type, proposed_issue.status
                )
                validate_status_transition(
                    configuration,
                    proposed_issue.issue_type,
                    before_issue.status,
                    proposed_issue.status,
                )

            policies_dir = project_dir / "policies" if project_dir else None
            if policies_dir and policies_dir.is_dir() and configuration:
                policy_documents = load_policies(policies_dir)
                if policy_documents:
                    all_issues = load_beads_issues(root)
                    for index, existing_issue in enumerate(all_issues):
                        if existing_issue.identifier == proposed_issue.identifier:
                            all_issues[index] = proposed_issue
                            break
                    context = PolicyContext(
                        current_issue=before_issue,
                        proposed_issue=proposed_issue,
                        transition=(
                            StatusTransition(
                                from_status=before_issue.status,
                                to_status=proposed_issue.status,
                            )
                            if proposed_issue.status != before_issue.status
                            else None
                        ),
                        operation=PolicyOperation.UPDATE,
                        project_configuration=configuration,
                        all_issues=all_issues,
                    )
                    evaluate_policies(context, policy_documents)

        try:
            update_beads_issue(
                root,
                identifier,
                status=status,
                title=title.strip() if title else None,
                description=description.strip() if description else None,
                priority=priority,
                assignee=final_assignee,
                add_labels=list(add_labels) if add_labels else None,
                remove_labels=list(remove_labels) if remove_labels else None,
                set_labels=parsed_set_labels,
            )
        except BeadsWriteError as error:
            raise click.ClickException(str(error)) from error
        updated_issue = load_beads_issue(root, identifier)
        formatted_identifier = format_issue_key(identifier, project_context=False)
        click.echo(f"Updated {formatted_identifier}")
        if update_quality_result:
            emit_signals(
                update_quality_result,
                "description",
                issue_id=identifier,
                is_update=True,
            )
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.AFTER,
            event=HookEvent.ISSUE_UPDATE,
            operation={
                "identifier": identifier,
                "issue": serialize_issue(updated_issue),
            },
            root=root,
            beads_mode=True,
        )
        return

    # Regular Kanbus mode
    before_issue_snapshot: IssueData | None = None
    try:
        before_issue_snapshot = load_issue_from_project(root, identifier).issue
    except IssueLookupError:
        before_issue_snapshot = None

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_UPDATE,
        operation={
            "identifier": identifier,
            "changes": {
                "title": title.strip() if title else None,
                "description": description.strip() if description else None,
                "status": status,
                "priority": priority,
                "assignee": final_assignee,
                "parent": parent,
                "add_labels": list(add_labels),
                "remove_labels": list(remove_labels),
                "set_labels": parsed_set_labels,
            },
            "before_issue": serialize_issue(before_issue_snapshot),
        },
        root=root,
        beads_mode=False,
    )
    try:
        updated_issue = update_issue(
            root=root,
            identifier=identifier,
            title=title.strip() if title else None,
            description=description.strip() if description else None,
            status=status,
            assignee=final_assignee,
            claim=claim,
            validate=not no_validate,
            priority=priority,
            add_labels=list(add_labels) if add_labels else None,
            remove_labels=list(remove_labels) if remove_labels else None,
            set_labels=parsed_set_labels,
            parent=parent,
        )
    except IssueUpdateError as error:
        raise click.ClickException(str(error)) from error

    formatted_identifier = format_issue_key(identifier, project_context=False)
    click.echo(f"Updated {formatted_identifier}")
    if update_quality_result:
        emit_signals(
            update_quality_result, "description", issue_id=identifier, is_update=True
        )
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_UPDATE,
        operation={
            "identifier": identifier,
            "issue": serialize_issue(updated_issue),
        },
        issues_for_policy=[updated_issue],
        root=root,
        beads_mode=False,
    )


@cli.group("bulk")
def bulk() -> None:
    """Bulk issue operations."""


@bulk.command("update")
@click.option("--id", "ids", multiple=True)
@click.option("--where-type", "where_type")
@click.option("--where-status", "where_status")
@click.option("--set-status", "set_status")
@click.option("--set-assignee", "set_assignee")
@click.option("--no-validate", "no_validate", is_flag=True, default=False)
@click.pass_context
def bulk_update(
    context: click.Context,
    ids: tuple[str, ...],
    where_type: str | None,
    where_status: str | None,
    set_status: str | None,
    set_assignee: str | None,
    no_validate: bool,
) -> None:
    """Update multiple issues selected by IDs and/or filters."""
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    if beads_mode:
        raise click.ClickException("bulk update is not supported in beads mode")
    if not ids and where_type is None and where_status is None:
        raise click.ClickException(
            "bulk update requires at least one selector (--id, --where-type, or --where-status)"
        )
    if set_status is None and set_assignee is None:
        raise click.ClickException(
            "bulk update requires at least one setter (--set-status or --set-assignee)"
        )

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_UPDATE,
        operation={
            "bulk": True,
            "selectors": {
                "ids": list(ids),
                "where_type": where_type,
                "where_status": where_status,
            },
            "changes": {
                "status": set_status,
                "assignee": set_assignee,
            },
        },
        root=root,
        beads_mode=False,
    )

    updated: list[IssueData] = []
    seen: set[str] = set()

    for identifier in ids:
        try:
            issue = update_issue(
                root=root,
                identifier=identifier,
                title=None,
                description=None,
                status=set_status,
                assignee=set_assignee,
                claim=False,
                validate=not no_validate,
                priority=None,
                add_labels=None,
                remove_labels=None,
                set_labels=None,
                parent=None,
            )
        except IssueUpdateError as error:
            raise click.ClickException(str(error)) from error
        if issue.identifier not in seen:
            seen.add(issue.identifier)
            updated.append(issue)

    if where_type is not None or where_status is not None:
        try:
            matching = list_issues(
                root=root,
                status=where_status,
                issue_type=where_type,
            )
        except IssueListingError as error:
            raise click.ClickException(str(error)) from error
        for issue in matching:
            if issue.identifier in seen:
                continue
            try:
                updated_issue = update_issue(
                    root=root,
                    identifier=issue.identifier,
                    title=None,
                    description=None,
                    status=set_status,
                    assignee=set_assignee,
                    claim=False,
                    validate=not no_validate,
                    priority=None,
                    add_labels=None,
                    remove_labels=None,
                    set_labels=None,
                    parent=None,
                )
            except IssueUpdateError as error:
                raise click.ClickException(str(error)) from error
            seen.add(updated_issue.identifier)
            updated.append(updated_issue)

    click.echo(f"Updated {len(updated)} issue(s)")
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_UPDATE,
        operation={
            "bulk": True,
            "issue_ids": [issue.identifier for issue in updated],
            "count": len(updated),
        },
        issues_for_policy=updated,
        root=root,
        beads_mode=False,
    )


@cli.command("close")
@click.argument("identifier")
@click.pass_context
def close(context: click.Context, identifier: str) -> None:
    """Close an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    if beads_mode:
        root = _resolve_beads_root(root)

    before_issue = None
    if beads_mode:
        try:
            before_issue = load_beads_issue(root, identifier)
        except MigrationError:
            before_issue = None
    else:
        try:
            before_issue = load_issue_from_project(root, identifier).issue
        except IssueLookupError:
            before_issue = None

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CLOSE,
        operation={
            "identifier": identifier,
            "before_issue": serialize_issue(before_issue),
        },
        root=root,
        beads_mode=beads_mode,
    )

    try:
        if beads_mode:
            update_beads_issue(root, identifier, status="closed")
            issue = load_beads_issue(root, identifier)
        else:
            issue = close_issue(root, identifier)
    except (IssueCloseError, BeadsWriteError, MigrationError) as error:
        raise click.ClickException(str(error)) from error
    formatted_identifier = format_issue_key(identifier, project_context=False)
    click.echo(f"Closed {formatted_identifier}")
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_CLOSE,
        operation={"identifier": identifier, "issue": serialize_issue(issue)},
        issues_for_policy=[issue],
        root=root,
        beads_mode=beads_mode,
    )


@cli.command("move")
@click.argument("identifier")
@click.argument("issue_type")
@click.option("--status")
@click.option("--no-validate", "no_validate", is_flag=True, default=False)
@click.pass_context
def move(
    context: click.Context,
    identifier: str,
    issue_type: str,
    status: str | None,
    no_validate: bool,
) -> None:
    """Move an issue to a different issue type."""
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False

    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            # Treat unreadable/missing project config as standard Kanbus mode.
            pass

    if beads_mode:
        raise click.ClickException("move is not supported in beads mode")

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_UPDATE,
        operation={
            "identifier": identifier,
            "changes": {"issue_type": issue_type, "status": status},
        },
        root=root,
        beads_mode=False,
    )
    try:
        updated_issue = update_issue(
            root=root,
            identifier=identifier,
            title=None,
            description=None,
            status=status,
            assignee=None,
            claim=False,
            validate=not no_validate,
            priority=None,
            add_labels=None,
            remove_labels=None,
            set_labels=None,
            parent=None,
            issue_type=issue_type,
        )
    except IssueUpdateError as error:
        raise click.ClickException(str(error)) from error

    formatted_identifier = format_issue_key(identifier, project_context=False)
    click.echo(f"Moved {formatted_identifier} to type {updated_issue.issue_type}")
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_UPDATE,
        operation={"identifier": identifier, "issue": serialize_issue(updated_issue)},
        issues_for_policy=[updated_issue],
        root=root,
        beads_mode=False,
    )


@cli.command("delete")
@click.argument("identifier")
@click.option("--yes", "yes_flag", is_flag=True, default=False)
@click.option("--recursive", is_flag=True, default=False)
@click.pass_context
def delete(
    context: click.Context, identifier: str, yes_flag: bool, recursive: bool
) -> None:
    """Delete an issue and its event history.

    Prompts for confirmation unless --yes is given. With --recursive, also
    prompts to delete descendant issues.

    :param context: Click context.
    :type context: click.Context
    :param identifier: Issue identifier.
    :type identifier: str
    :param yes_flag: Skip confirmation prompts.
    :type yes_flag: bool
    :param recursive: Allow deleting descendants after confirmation.
    :type recursive: bool
    """
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode"))
    issue_for_guidance: IssueData | None = None
    issue_for_hooks: IssueData | None = None

    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            pass

    if not beads_mode:
        try:
            lookup = load_issue_from_project(root, identifier)
            issue_for_guidance = lookup.issue
            issue_for_hooks = lookup.issue
        except IssueLookupError:
            issue_for_guidance = None
            issue_for_hooks = None

    if beads_mode:
        root = _resolve_beads_root(root)
        try:
            issue_for_hooks = load_beads_issue(root, identifier)
        except MigrationError:
            issue_for_hooks = None
        if not yes_flag:
            if not _delete_terminal_is_interactive():
                raise click.ClickException(
                    "delete requires confirmation (re-run with --yes)"
                )
            if not click.confirm(
                f'Delete "{identifier}" and its event history?', default=False
            ):
                click.echo("Delete cancelled.")
                return
        beads_recursive = recursive
        if recursive and not yes_flag:
            beads_descendants = get_beads_descendant_identifiers(root, identifier)
            if beads_descendants:
                formatted_desc = ", ".join(beads_descendants)
                if len(beads_descendants) > 5:
                    formatted_desc = (
                        ", ".join(beads_descendants[:5])
                        + f" and {len(beads_descendants) - 5} more"
                    )
                if not click.confirm(
                    f"Also delete {len(beads_descendants)} descendant(s): {formatted_desc}?",
                    default=False,
                ):
                    beads_recursive = False
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_DELETE,
            operation={
                "identifier": identifier,
                "recursive": beads_recursive,
                "before_issue": serialize_issue(issue_for_hooks),
            },
            root=root,
            beads_mode=True,
        )
        try:
            delete_beads_issue(root, identifier, recursive=beads_recursive)
        except BeadsDeleteError as error:
            raise click.ClickException(str(error)) from error
        formatted_identifier = format_issue_key(identifier, project_context=False)
        click.echo(f"Deleted {formatted_identifier}")
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.AFTER,
            event=HookEvent.ISSUE_DELETE,
            operation={
                "identifier": identifier,
                "recursive": beads_recursive,
                "before_issue": serialize_issue(issue_for_hooks),
            },
            root=root,
            beads_mode=True,
        )
        return

    if not yes_flag:
        if not _delete_terminal_is_interactive():
            raise click.ClickException(
                "delete requires confirmation (re-run with --yes)"
            )
        if not click.confirm(
            f'Delete "{identifier}" and its event history?', default=False
        ):
            click.echo("Delete cancelled.")
            return

    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise click.ClickException(str(error)) from error

    descendants: list[str] = []
    if recursive:
        descendants = get_descendant_identifiers(lookup.project_dir, identifier)
    if descendants and not yes_flag:
        formatted_desc = ", ".join(descendants)
        if len(descendants) > 5:
            formatted_desc = (
                ", ".join(descendants[:5]) + f" and {len(descendants) - 5} more"
            )
        if not click.confirm(
            f"Also delete {len(descendants)} descendant(s): {formatted_desc}?",
            default=False,
        ):
            descendants = []

    to_delete = descendants + [identifier]
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_DELETE,
        operation={
            "identifier": identifier,
            "recursive": recursive,
            "deleted_ids": list(to_delete),
            "before_issue": serialize_issue(issue_for_hooks),
        },
        root=root,
        beads_mode=False,
    )
    for issue_id in to_delete:
        try:
            delete_issue(root, issue_id)
        except IssueDeleteError as error:
            raise click.ClickException(str(error)) from error
        formatted_identifier = format_issue_key(issue_id, project_context=False)
        click.echo(f"Deleted {formatted_identifier}")

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_DELETE,
        operation={
            "identifier": identifier,
            "recursive": recursive,
            "deleted_ids": list(to_delete),
            "before_issue": serialize_issue(issue_for_hooks),
        },
        issues_for_policy=(
            [issue_for_guidance] if issue_for_guidance is not None else []
        ),
        root=root,
        beads_mode=False,
    )


@cli.command("promote")
@click.argument("identifier")
@click.pass_context
def promote(context: click.Context, identifier: str) -> None:
    """Promote a local issue to the shared project.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    before_issue = None
    try:
        before_issue = load_issue_from_project(root, identifier).issue
    except IssueLookupError:
        before_issue = None

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_PROMOTE,
        operation={
            "identifier": identifier,
            "before_issue": serialize_issue(before_issue),
        },
        root=root,
        beads_mode=False,
    )
    try:
        promote_issue(root, identifier)
    except IssueTransferError as error:
        raise click.ClickException(str(error)) from error
    after_issue = None
    try:
        after_issue = load_issue_from_project(root, identifier).issue
    except IssueLookupError:
        after_issue = None
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_PROMOTE,
        operation={"identifier": identifier, "issue": serialize_issue(after_issue)},
        root=root,
        beads_mode=False,
    )


@cli.command("localize")
@click.argument("identifier")
@click.pass_context
def localize(context: click.Context, identifier: str) -> None:
    """Move a shared issue into project-local.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    before_issue = None
    try:
        before_issue = load_issue_from_project(root, identifier).issue
    except IssueLookupError:
        before_issue = None

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_LOCALIZE,
        operation={
            "identifier": identifier,
            "before_issue": serialize_issue(before_issue),
        },
        root=root,
        beads_mode=False,
    )
    try:
        localize_issue(root, identifier)
    except IssueTransferError as error:
        raise click.ClickException(str(error)) from error
    after_issue = None
    try:
        after_issue = load_issue_from_project(root, identifier).issue
    except IssueLookupError:
        after_issue = None
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_LOCALIZE,
        operation={"identifier": identifier, "issue": serialize_issue(after_issue)},
        root=root,
        beads_mode=False,
    )


@cli.command("comment")
@click.argument("identifier")
@click.argument("text", required=False)
@click.option("--body-file", type=click.File("r"), default=None)
@click.option("--no-validate", "no_validate", is_flag=True, default=False)
@click.pass_context
def comment(
    context: click.Context,
    identifier: str,
    text: Optional[str],
    body_file: Optional[click.File],
    no_validate: bool = False,
) -> None:
    """Add a comment to an issue.

    :param context: Click context.
    :type context: click.Context
    :param identifier: Issue identifier.
    :type identifier: str
    :param text: Comment text (or use --body-file for multi-line).
    :type text: Optional[str]
    :param body_file: File to read comment text from (use '-' for stdin).
    :type body_file: Optional[click.File]
    :param no_validate: Bypass validation checks.
    :type no_validate: bool
    """
    root = Path.cwd()
    beads_mode = context.obj.get("beads_mode", False)

    # Check if beads_compatibility is enabled in config
    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            # Treat unreadable/missing project config as standard Kanbus mode.
            pass

    # Handle body-file input
    comment_text = text or ""
    if body_file is not None:
        comment_text = body_file.read()

    if not comment_text:
        raise click.ClickException("Comment text required")

    comment_quality_result = apply_text_quality_signals(comment_text)
    comment_text = comment_quality_result.text

    if not no_validate:
        try:
            validate_code_blocks(comment_text)
        except ContentValidationError as error:
            raise click.ClickException(str(error)) from error

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_COMMENT,
        operation={
            "identifier": identifier,
            "comment_text": comment_text,
            "comment_length": len(comment_text),
        },
        root=root,
        beads_mode=beads_mode,
    )

    result_comment = None
    try:
        if beads_mode:
            from kanbus.beads_write import add_beads_comment, BeadsWriteError

            try:
                add_beads_comment(
                    root=root,
                    identifier=identifier,
                    author=get_current_user(),
                    text=comment_text,
                )
            except BeadsWriteError as error:
                raise click.ClickException(str(error)) from error
            emit_signals(comment_quality_result, "comment", issue_id=identifier)
        else:
            result_comment = add_comment(
                root=root,
                identifier=identifier,
                author=get_current_user(),
                text=comment_text,
            )
            emit_signals(
                comment_quality_result,
                "comment",
                issue_id=identifier,
                comment_id=result_comment.comment.id,
            )
    except IssueCommentError as error:
        raise click.ClickException(str(error)) from error

    after_issue = None
    if beads_mode:
        try:
            after_issue = load_beads_issue(root, identifier)
        except MigrationError:
            after_issue = None
    elif result_comment is not None:
        after_issue = result_comment.issue

    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_COMMENT,
        operation={
            "identifier": identifier,
            "issue": serialize_issue(after_issue),
            "comment_id": (
                result_comment.comment.id
                if result_comment is not None and result_comment.comment.id is not None
                else None
            ),
        },
        root=root,
        beads_mode=beads_mode,
    )


@cli.command("list")
@click.option("--status")
@click.option("--type", "issue_type")
@click.option("--assignee")
@click.option("--label")
@click.option("--sort")
@click.option("--search")
@click.option("--project", "projects", multiple=True, help="Filter by project label.")
@click.option("--no-local", is_flag=True, default=False)
@click.option("--local-only", is_flag=True, default=False)
@click.option(
    "--limit",
    type=int,
    default=50,
    show_default=True,
    help="Maximum issues to display (0 for no limit). Matches Beads default.",
)
@click.option(
    "--porcelain",
    is_flag=True,
    default=False,
    help="Plain, non-colorized output for machine parsing.",
)
@click.option(
    "--full-ids",
    "full_ids",
    is_flag=True,
    default=False,
    help="Show full issue keys even in single-project context.",
)
@click.pass_context
def list_command(
    context: click.Context,
    status: str | None,
    issue_type: str | None,
    assignee: str | None,
    label: str | None,
    sort: str | None,
    search: str | None,
    projects: tuple[str, ...],
    no_local: bool,
    local_only: bool,
    limit: int,
    porcelain: bool,
    full_ids: bool,
) -> None:
    """List issues in the current project.

    \b
    Examples:
      kbs list
      kbs list --type epic
      kbs list --status open
      kbs list --type task --status in_progress
      kbs issues / kbs epics / kbs tasks / kbs bugs   shorthand aliases
    """
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    if beads_mode:
        root = _resolve_beads_root(root)
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_LIST,
        operation={
            "status": status,
            "issue_type": issue_type,
            "assignee": assignee,
            "label": label,
            "sort": sort,
            "search": search,
            "projects": list(projects),
            "no_local": no_local,
            "local_only": local_only,
            "limit": limit,
            "porcelain": porcelain,
            "full_ids": full_ids,
        },
        root=root,
        beads_mode=beads_mode,
    )
    try:
        issues = list_issues(
            root,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            label=label,
            sort=sort,
            search=search,
            project_filter=list(projects),
            include_local=not no_local,
            local_only=local_only,
            beads_mode=beads_mode,
        )
    except (IssueListingError, QueryError) as error:
        raise click.ClickException(str(error)) from error

    if beads_mode:
        issues = sorted(
            issues,
            key=lambda issue: (
                issue.priority,
                -_issue_sort_timestamp(issue),
                issue.identifier,
            ),
        )
    if limit > 0:
        issues = issues[:limit]

    configuration = None
    if not beads_mode:
        try:
            configuration = load_project_configuration(get_configuration_path(root))
        except ProjectMarkerError:
            configuration = None
        except ConfigurationError as error:
            raise click.ClickException(str(error)) from error

    # In Beads mode, always show full IDs (project_context=False)
    # In regular mode, use project_context if all issues are from same project
    project_context = (
        False
        if beads_mode or full_ids
        else not any(issue.custom.get("project_path") for issue in issues)
    )
    widths = (
        None if porcelain else compute_widths(issues, project_context=project_context)
    )
    for issue in issues:
        line = format_issue_line(
            issue,
            porcelain=porcelain,
            widths=widths,
            project_context=project_context,
            configuration=configuration,
        )
        click.echo(line)
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_LIST,
        operation={
            "status": status,
            "issue_type": issue_type,
            "assignee": assignee,
            "label": label,
            "sort": sort,
            "search": search,
            "projects": list(projects),
            "no_local": no_local,
            "local_only": local_only,
            "issue_ids": [issue.identifier for issue in issues],
        },
        issues_for_policy=issues,
        root=root,
        beads_mode=beads_mode,
    )


def _issue_sort_timestamp(issue: IssueData) -> float:
    """Return a sortable UTC timestamp (seconds) for an issue."""

    timestamp = issue.closed_at or issue.updated_at or issue.created_at
    return timestamp.timestamp()


def _run_lifecycle_hooks_for_context(
    context: click.Context,
    *,
    phase: HookPhase,
    event: HookEvent,
    operation: dict[str, object] | None = None,
    issues_for_policy: list[IssueData] | None = None,
    root: Path | None = None,
    beads_mode: bool | None = None,
) -> None:
    """Run lifecycle hooks with context-aware global controls."""
    if not context.obj:
        return
    try:
        run_lifecycle_hooks(
            root=root or Path.cwd(),
            phase=phase,
            event=event,
            actor=get_current_user(),
            beads_mode=(
                bool(context.obj.get("beads_mode", False))
                if beads_mode is None
                else beads_mode
            ),
            operation=operation or {},
            issues_for_policy=issues_for_policy,
            no_hooks=bool(context.obj.get("no_hooks", False)),
            no_guidance=bool(context.obj.get("no_guidance", False)),
        )
    except HookExecutionError as error:
        raise click.ClickException(str(error)) from error


@cli.group("hooks")
def hooks_group() -> None:
    """Inspect and validate lifecycle hook configuration."""


@hooks_group.command("list")
def hooks_list_command() -> None:
    """List configured hooks and built-in providers."""
    root = Path.cwd()
    rows = list_hooks(root)
    if not rows:
        click.echo("No hooks configured.")
        return

    for row in rows:
        timeout = row["timeout_ms"] if row["timeout_ms"] is not None else "default"
        click.echo(
            f"[{row['source']}] {row['phase']} {row['event']} {row['id']}\n"
            f"  command: {row['command']}\n"
            f"  blocking: {row['blocking']} timeout_ms: {timeout}"
        )


@hooks_group.command("validate")
def hooks_validate_command() -> None:
    """Validate hook commands, IDs, and event bindings."""
    root = Path.cwd()
    issues = validate_hooks(root)
    if issues:
        lines = [f"Found {len(issues)} hook validation issue(s):"]
        lines.extend([f"- {issue}" for issue in issues])
        raise click.ClickException("\n".join(lines))
    click.echo("Hook configuration is valid.")


@cli.group("wiki")
def wiki() -> None:
    """Manage wiki pages."""


@wiki.command("render")
@click.argument("page")
def render_wiki(page: str) -> None:
    """Render a wiki page.

    :param page: Wiki page path.
    :type page: str
    """
    root = Path.cwd()
    request = WikiRenderRequest(root=root, page_path=Path(page))
    try:
        output = render_wiki_page(request)
    except WikiError as error:
        raise click.ClickException(str(error)) from error
    click.echo(output)


@wiki.command("list")
def wiki_list() -> None:
    """List wiki pages."""
    root = Path.cwd()
    try:
        pages = list_wiki_pages(root)
    except WikiError as error:
        raise click.ClickException(str(error)) from error
    for path in pages:
        click.echo(path)


@cli.group("edit")
def edit_group() -> None:
    """File edit commands mirroring the Anthropic text editor tool."""


@edit_group.command("view")
@click.argument("path", type=click.Path())
@click.option(
    "--view-range",
    nargs=2,
    type=int,
    default=None,
    help="Start and end line numbers (1-indexed; -1 for end).",
)
def edit_view_cmd(path: str, view_range: tuple[int, int] | None) -> None:
    """View file contents or list directory."""
    root = Path.cwd()
    path_obj = Path(path)
    try:
        output = edit_view(root, path_obj, view_range)
    except TextEditorError as error:
        raise click.ClickException(str(error)) from error
    click.echo(output)


@edit_group.command("str-replace")
@click.argument("path", type=click.Path())
@click.option("--old-str", required=True)
@click.option("--new-str", required=True)
def edit_str_replace_cmd(path: str, old_str: str, new_str: str) -> None:
    """Replace exact text in file (must match exactly one location)."""
    root = Path.cwd()
    path_obj = Path(path)
    try:
        output = edit_str_replace(root, path_obj, old_str, new_str)
    except TextEditorError as error:
        raise click.ClickException(str(error)) from error
    click.echo(output)


@edit_group.command("create")
@click.argument("path", type=click.Path())
@click.option("--file-text", required=True)
def edit_create_cmd(path: str, file_text: str) -> None:
    """Create a new file with the given content."""
    root = Path.cwd()
    path_obj = Path(path)
    try:
        output = edit_create(root, path_obj, file_text)
    except TextEditorError as error:
        raise click.ClickException(str(error)) from error
    click.echo(output)


@edit_group.command("insert")
@click.argument("path", type=click.Path())
@click.option("--insert-line", type=int, required=True)
@click.option("--insert-text", required=True)
def edit_insert_cmd(path: str, insert_line: int, insert_text: str) -> None:
    """Insert text after the given line number (0 = beginning)."""
    root = Path.cwd()
    path_obj = Path(path)
    try:
        output = edit_insert(root, path_obj, insert_line, insert_text)
    except TextEditorError as error:
        raise click.ClickException(str(error)) from error
    click.echo(output)


@cli.group("policy")
def policy() -> None:
    """Policy management commands."""


@policy.command("check")
@click.argument("identifier")
def policy_check(identifier: str) -> None:
    """Check policies against an issue.

    :param identifier: Issue identifier to check policies against.
    :type identifier: str
    """
    from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
    from kanbus.policy_loader import load_policies
    from kanbus.policy_evaluator import (
        evaluate_policies_with_options,
        PolicyEvaluationOptions,
    )
    from kanbus.policy_context import PolicyContext, PolicyOperation
    from kanbus.issue_listing import load_issues_from_directory
    from kanbus.config_loader import load_project_configuration
    from kanbus.project import get_configuration_path

    root = Path.cwd()
    try:
        lookup = load_issue_from_project(root, identifier)
        configuration = load_project_configuration(
            get_configuration_path(lookup.project_dir)
        )
        policies_dir = lookup.project_dir / "policies"

        if not policies_dir.is_dir():
            click.echo("No policies directory found")
            return

        policy_documents = load_policies(policies_dir)
        if not policy_documents:
            click.echo("No policy files found")
            return

        issues_dir = lookup.project_dir / "issues"
        all_issues = load_issues_from_directory(issues_dir)
        context = PolicyContext(
            current_issue=lookup.issue,
            proposed_issue=lookup.issue,
            transition=None,
            operation=PolicyOperation.UPDATE,
            project_configuration=configuration,
            all_issues=all_issues,
        )

        violations = evaluate_policies_with_options(
            context,
            policy_documents,
            PolicyEvaluationOptions(collect_all_violations=True),
        )

        if violations:
            error_msg = [f"Found {len(violations)} policy violation(s):"]
            for i, v in enumerate(violations):
                error_msg.append(f"\n{i + 1}. {v}")
            raise click.ClickException("\n".join(error_msg))

        click.echo(f"All policies passed for {identifier}")
    except IssueLookupError as error:
        raise click.ClickException(str(error)) from error
    except Exception as error:
        raise click.ClickException(str(error)) from error


@policy.command("guide")
@click.argument("identifier")
def policy_guide(identifier: str) -> None:
    """Run policy guidance against an issue without enforcing blocks."""
    from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
    from kanbus.policy_context import PolicyOperation
    from kanbus.policy_guidance import (
        collect_guidance_for_issue,
        sorted_deduped_guidance_items,
    )

    root = Path.cwd()
    try:
        lookup = load_issue_from_project(root, identifier)
        report = collect_guidance_for_issue(
            root=lookup.project_dir,
            issue=lookup.issue,
            operation=PolicyOperation.VIEW,
        )
    except IssueLookupError as error:
        raise click.ClickException(str(error)) from error
    except Exception as error:
        raise click.ClickException(str(error)) from error

    if report.violations:
        lines = [
            f"Found {len(report.violations)} policy validation issue(s) while generating guidance:"
        ]
        for index, violation in enumerate(report.violations, start=1):
            lines.append(f"\n{index}. {violation}")
        raise click.ClickException("\n".join(lines))

    items = sorted_deduped_guidance_items(report.guidance_items)
    if not items:
        click.echo(f"No guidance for {identifier}")
        return

    for item in items:
        prefix = (
            "GUIDANCE WARNING"
            if item.severity.value == "warning"
            else "GUIDANCE SUGGESTION"
        )
        click.echo(f"{prefix}: {item.message}", err=True)
        for explanation in item.explanations:
            click.echo(f"  Explanation: {explanation}", err=True)


@policy.command("list")
def policy_list() -> None:
    """List all loaded policy files."""
    from kanbus.project import load_project_directory
    from kanbus.policy_loader import load_policies

    root = Path.cwd()
    try:
        project_dir = load_project_directory(root)
        policies_dir = project_dir / "policies"

        if not policies_dir.is_dir():
            click.echo("No policies directory found")
            return

        policy_documents = load_policies(policies_dir)
        if not policy_documents:
            click.echo("No policy files found")
            return

        for filename, document in policy_documents:
            click.echo(f"{filename}")
            if document.feature:
                click.echo(f"  Feature: {document.feature.name}")
                for child in document.feature.children:
                    scenario = getattr(child, "scenario", None)
                    if scenario:
                        click.echo(f"    Scenario: {scenario.name}")
                        continue
                    rule = getattr(child, "rule", None)
                    if not rule:
                        continue
                    for rule_child in getattr(rule, "children", []):
                        nested = getattr(rule_child, "scenario", None)
                        if not nested:
                            continue
                        click.echo(f"    Rule: {rule.name} / {nested.name}")
    except Exception as error:
        raise click.ClickException(str(error)) from error


@policy.command("steps")
@click.option("--category", help="Filter by category (given, when, then).")
@click.option("--search", help="Filter by search term.")
def policy_steps(category: str | None, search: str | None) -> None:
    """List available policy steps.

    :param category: Filter by category.
    :type category: str | None
    :param search: Filter by search term.
    :type search: str | None
    """
    from kanbus.policy_evaluator import _get_step_registry

    registry = _get_step_registry()
    output = []

    for step in registry.steps:
        if category:
            if category.lower() != step.category.value.lower():
                continue
        if search:
            search_lower = search.lower()
            if (
                search_lower not in step.description.lower()
                and search_lower not in step.usage_pattern.lower()
            ):
                continue
        output.append(
            f"{step.category.value} - {step.description}\n  Pattern: {step.usage_pattern}"
        )

    if not output:
        click.echo("No matching steps found")
    else:
        click.echo("\n".join(output))


@policy.command("validate")
def policy_validate() -> None:
    """Validate all policy files for syntax errors."""
    from datetime import datetime, timezone

    from kanbus.models import IssueData
    from kanbus.policy_context import PolicyContext, PolicyOperation
    from kanbus.policy_evaluator import validate_policy_documents
    from kanbus.project import load_project_directory
    from kanbus.policy_loader import load_policies

    root = Path.cwd()
    try:
        project_dir = load_project_directory(root)
        policies_dir = project_dir / "policies"

        if not policies_dir.is_dir():
            click.echo("No policies directory found")
            return

        policy_documents = load_policies(policies_dir)
        if not policy_documents:
            click.echo("No policy files found")
            return

        configuration = load_project_configuration(get_configuration_path(project_dir))
        now = datetime.now(timezone.utc)
        validation_issue = IssueData(
            id="kanbus-policy-validate",
            title="Policy Validation Context",
            description="",
            type="task",
            status=configuration.initial_status,
            priority=configuration.default_priority,
            assignee=None,
            creator=None,
            parent=None,
            labels=[],
            dependencies=[],
            comments=[],
            created_at=now,
            updated_at=now,
            closed_at=None,
            custom={},
        )
        validation_context = PolicyContext(
            current_issue=validation_issue,
            proposed_issue=validation_issue,
            transition=None,
            operation=PolicyOperation.UPDATE,
            project_configuration=configuration,
            all_issues=[],
        )
        validation_violations = validate_policy_documents(
            validation_context,
            policy_documents,
        )
        if validation_violations:
            lines = [f"Found {len(validation_violations)} policy validation issue(s):"]
            for index, violation in enumerate(validation_violations, start=1):
                lines.append(f"\n{index}. {violation}")
            raise click.ClickException("\n".join(lines))

        click.echo(f"All {len(policy_documents)} policy files are valid")
    except Exception as error:
        raise click.ClickException(str(error)) from error


@cli.group("console")
def console() -> None:
    """Console-related utilities."""


@console.command("snapshot")
def console_snapshot() -> None:
    """Emit a JSON snapshot for the console."""
    root = Path.cwd()
    try:
        snapshot = build_console_snapshot(root)
    except ConsoleSnapshotError as error:
        raise click.ClickException(str(error)) from error
    payload = json.dumps(snapshot, indent=2, sort_keys=False)
    click.echo(payload)


@console.command("focus")
@click.argument("identifier")
@click.option("--comment", default=None, help="Comment ID to scroll to.")
def console_focus(identifier: str, comment: Optional[str]) -> None:
    """Focus on an issue and its descendants in the console."""
    raise _deprecated_console_control("focus")


@console.command("unfocus")
def console_unfocus() -> None:
    """Clear the current focus filter in the console."""
    raise _deprecated_console_control("unfocus")


@console.command("view")
@click.argument("mode", type=click.Choice(["initiatives", "epics", "issues"]))
def console_view(mode: str) -> None:
    """Switch the console to a different view mode."""
    raise _deprecated_console_control("view")


@console.command("search")
@click.argument("query", required=False, default=None)
@click.option("--clear", is_flag=True, help="Clear the active search query.")
def console_search(query: Optional[str], clear: bool) -> None:
    """Set or clear the search query in the console."""
    raise _deprecated_console_control("search")


@console.command("maximize")
def console_maximize() -> None:
    """Deprecated console command."""
    raise _deprecated_console_control("maximize")


@console.command("restore")
def console_restore() -> None:
    """Deprecated console command."""
    raise _deprecated_console_control("restore")


@console.command("close-detail")
def console_close_detail() -> None:
    """Deprecated console command."""
    raise _deprecated_console_control("close-detail")


@console.command("toggle-settings")
def console_toggle_settings() -> None:
    """Deprecated console command."""
    raise _deprecated_console_control("toggle-settings")


@console.command("reload")
def console_reload() -> None:
    """Deprecated console command."""
    raise _deprecated_console_control("reload")


@console.command("set-setting")
@click.argument("key")
@click.argument("value")
def console_set_setting(key: str, value: str) -> None:
    """Deprecated console command."""
    _ = (key, value)
    raise _deprecated_console_control("set-setting")


@console.command("collapse")
@click.argument("column")
def console_collapse(column: str) -> None:
    """Deprecated console command."""
    _ = column
    raise _deprecated_console_control("collapse")


@console.command("collapse-column")
@click.argument("column")
def console_collapse_column(column: str) -> None:
    """Deprecated console command."""
    _ = column
    raise _deprecated_console_control("collapse-column")


@console.command("expand")
@click.argument("column")
def console_expand(column: str) -> None:
    """Deprecated console command."""
    _ = column
    raise _deprecated_console_control("expand")


@console.command("expand-column")
@click.argument("column")
def console_expand_column(column: str) -> None:
    """Deprecated console command."""
    _ = column
    raise _deprecated_console_control("expand-column")


@console.command("select")
@click.argument("identifier")
def console_select(identifier: str) -> None:
    """Deprecated console command."""
    _ = identifier
    raise _deprecated_console_control("select")


@console.command("status")
def console_status() -> None:
    """Print a human-readable summary of the current console UI state."""
    root = Path.cwd()
    ui_state = fetch_console_ui_state(root)
    if ui_state is None:
        click.echo("Console server is not running.")
        return
    focused = ui_state.get("focused_issue_id") or "none"
    view = ui_state.get("view_mode") or "none"
    search = ui_state.get("search_query") or "none"
    click.echo(f"focus:  {focused}")
    click.echo(f"view:   {view}")
    click.echo(f"search: {search}")


@console.group("get")
def console_get() -> None:
    """Query a specific piece of console UI state."""


@console_get.command("focus")
def console_get_focus() -> None:
    """Print the currently focused issue ID, or 'none'."""
    root = Path.cwd()
    ui_state = fetch_console_ui_state(root)
    if ui_state is None:
        click.echo("Console server is not running.")
        return
    click.echo(ui_state.get("focused_issue_id") or "none")


@console_get.command("view")
def console_get_view() -> None:
    """Print the current view mode, or 'none'."""
    root = Path.cwd()
    ui_state = fetch_console_ui_state(root)
    if ui_state is None:
        click.echo("Console server is not running.")
        return
    click.echo(ui_state.get("view_mode") or "none")


@console_get.command("search")
def console_get_search() -> None:
    """Print the active search query, or 'none'."""
    root = Path.cwd()
    ui_state = fetch_console_ui_state(root)
    if ui_state is None:
        click.echo("Console server is not running.")
        return
    click.echo(ui_state.get("search_query") or "none")


@cli.command("validate")
def validate() -> None:
    """Validate project integrity."""
    root = Path.cwd()
    try:
        validate_project(root)
    except ProjectValidationError as error:
        raise click.ClickException(str(error)) from error


@cli.command("stats")
def stats() -> None:
    """Report project statistics."""
    root = Path.cwd()
    try:
        stats_result = collect_project_stats(root)
    except ProjectStatsError as error:
        raise click.ClickException(str(error)) from error

    lines = [
        f"total issues: {stats_result.total}",
        f"open issues: {stats_result.open_count}",
        f"closed issues: {stats_result.closed_count}",
    ]
    for issue_type in sorted(stats_result.type_counts):
        count = stats_result.type_counts[issue_type]
        lines.append(f"type: {issue_type}: {count}")
    click.echo("\n".join(lines))


@cli.command(
    "dep",
    context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False},
)
@click.argument("args", nargs=-1, required=True)
@click.pass_context
def dep(context: click.Context, args: tuple[str, ...]) -> None:
    """Manage issue dependencies.

    Usage: kanbus dep <identifier> <blocked-by|relates-to> <target>
           kanbus dep <identifier> remove <blocked-by|relates-to> <target>
           kanbus dep tree <identifier> [--depth N] [--format FORMAT]
    """
    if len(args) < 1:
        raise click.ClickException("usage: kanbus dep <identifier> <type> <target>")

    # Check if this is a tree command - handle it separately since it needs options
    if args[0] == "tree":
        # Redirect to separate tree implementation
        if len(args) < 2:
            raise click.ClickException("tree requires an identifier")

        # For tree, we need to parse options differently
        # Just pass through to the tree handler with a simple parse
        tree_args = list(args[1:])
        tree_identifier = tree_args[0] if tree_args else None
        if not tree_identifier:
            raise click.ClickException("tree requires an identifier")

        # Simple option parsing
        depth = None
        output_format = "text"
        i = 1
        while i < len(tree_args):
            if tree_args[i] == "--depth" and i + 1 < len(tree_args):
                try:
                    depth = int(tree_args[i + 1])
                except ValueError:
                    raise click.ClickException("depth must be a number")
                i += 2
            elif tree_args[i] == "--format" and i + 1 < len(tree_args):
                output_format = tree_args[i + 1]
                i += 2
            else:
                i += 1

        root = Path.cwd()
        try:
            tree = build_dependency_tree(root, tree_identifier, depth)
            output = render_dependency_tree(tree, output_format)
        except DependencyTreeError as error:
            raise click.ClickException(str(error)) from error
        click.echo(output)
        return

    if len(args) < 2:
        raise click.ClickException("usage: kanbus dep <identifier> <type> <target>")

    identifier = args[0]

    # Check if this is a remove operation
    if len(args) > 1 and args[1] == "remove":
        if len(args) < 4:
            raise click.ClickException("dependency target is required")
        dep_type = args[2]
        target = args[3]
        is_remove = True
    else:
        if len(args) < 3:
            raise click.ClickException("dependency target is required")
        dep_type = args[1]
        target = args[2]
        is_remove = False

    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False

    # Check if beads_compatibility is enabled in config
    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            # Treat unreadable/missing project config as standard Kanbus mode.
            pass

    if is_remove:
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_DEPENDENCY,
            operation={
                "action": "remove",
                "identifier": identifier,
                "dependency_type": dep_type,
                "target": target,
            },
            root=root,
            beads_mode=beads_mode,
        )
        if beads_mode:
            try:
                from kanbus.beads_write import remove_beads_dependency

                remove_beads_dependency(root, identifier, target, dep_type)
            except BeadsWriteError as error:
                raise click.ClickException(str(error)) from error
        else:
            try:
                remove_dependency(root, identifier, target, dep_type)
            except DependencyError as error:
                raise click.ClickException(str(error)) from error
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.AFTER,
            event=HookEvent.ISSUE_DEPENDENCY,
            operation={
                "action": "remove",
                "identifier": identifier,
                "dependency_type": dep_type,
                "target": target,
            },
            root=root,
            beads_mode=beads_mode,
        )
    else:
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_DEPENDENCY,
            operation={
                "action": "add",
                "identifier": identifier,
                "dependency_type": dep_type,
                "target": target,
            },
            root=root,
            beads_mode=beads_mode,
        )
        if beads_mode:
            try:
                from kanbus.beads_write import add_beads_dependency

                add_beads_dependency(root, identifier, target, dep_type)
            except BeadsWriteError as error:
                raise click.ClickException(str(error)) from error
        else:
            try:
                add_dependency(root, identifier, target, dep_type)
            except DependencyError as error:
                raise click.ClickException(str(error)) from error
        _run_lifecycle_hooks_for_context(
            context,
            phase=HookPhase.AFTER,
            event=HookEvent.ISSUE_DEPENDENCY,
            operation={
                "action": "add",
                "identifier": identifier,
                "dependency_type": dep_type,
                "target": target,
            },
            root=root,
            beads_mode=beads_mode,
        )


@cli.command("ready")
@click.option("--no-local", is_flag=True, default=False)
@click.option("--local-only", is_flag=True, default=False)
@click.pass_context
def ready(context: click.Context, no_local: bool, local_only: bool) -> None:
    """List issues that are ready (not blocked)."""
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    if beads_mode:
        root = _resolve_beads_root(root)
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_READY,
        operation={"no_local": no_local, "local_only": local_only},
        root=root,
        beads_mode=beads_mode,
    )
    try:
        issues = list_ready_issues(
            root,
            include_local=not no_local,
            local_only=local_only,
            beads_mode=beads_mode,
        )
    except DependencyError as error:
        raise click.ClickException(str(error)) from error
    for issue in issues:
        project_path = issue.custom.get("project_path")
        prefix = f"{project_path} " if project_path else ""
        click.echo(f"{prefix}{issue.identifier}")
    _run_lifecycle_hooks_for_context(
        context,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_READY,
        operation={
            "no_local": no_local,
            "local_only": local_only,
            "issue_ids": [issue.identifier for issue in issues],
        },
        issues_for_policy=issues,
        root=root,
        beads_mode=beads_mode,
    )


@cli.command("doctor")
def doctor() -> None:
    """Run environment diagnostics for Kanbus."""
    root = Path.cwd()
    try:
        result = run_doctor(root)
    except DoctorError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"ok {result.project_dir}")


@cli.command("migrate")
@click.option(
    "--into-existing",
    is_flag=True,
    help=(
        "Import Beads issues into an already initialized project. "
        "Repeatable: re-runs and overwrites matching issue JSON files."
    ),
)
def migrate(into_existing: bool) -> None:
    """Migrate Beads issues into Kanbus.

    :raises click.ClickException: If migration fails.
    """
    root = Path.cwd()
    try:
        if into_existing:
            result = migrate_from_beads_into_project(root)
        else:
            result = migrate_from_beads(root)
    except MigrationError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"migrated {result.issue_count} issues")


@cli.command("daemon-status")
def daemon_status() -> None:
    """Report daemon status."""
    root = Path.cwd()
    try:
        result = request_status(root)
    except ProjectMarkerError as error:
        raise click.ClickException(_format_project_marker_error(error)) from error
    except DaemonClientError as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(result, indent=2, sort_keys=False))


@cli.command("daemon-stop")
def daemon_stop() -> None:
    """Stop the daemon process."""
    root = Path.cwd()
    try:
        result = request_shutdown(root)
    except ProjectMarkerError as error:
        raise click.ClickException(_format_project_marker_error(error)) from error
    except DaemonClientError as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(result, indent=2, sort_keys=False))


@cli.group()
def gossip() -> None:
    """Realtime gossip commands."""


@gossip.command("broker")
@click.option("--socket", "socket_path", type=click.Path(path_type=Path))
def gossip_broker(socket_path: Optional[Path]) -> None:
    """Run a local UDS gossip broker."""
    root = Path.cwd()
    try:
        run_gossip_broker(root, socket_path)
    except GossipError as error:
        raise click.ClickException(str(error)) from error


@gossip.command("watch")
@click.option("--project", "project_label", default=None)
@click.option("--transport", default=None)
@click.option("--broker", default=None)
@click.option("--autostart/--no-autostart", default=None)
@click.option("--keepalive/--no-keepalive", default=None)
@click.option(
    "--print/--no-print",
    "print_envelopes",
    default=False,
    help="Print each received envelope as JSON (NDJSON) to stdout.",
)
def gossip_watch(
    project_label: Optional[str],
    transport: Optional[str],
    broker: Optional[str],
    autostart: Optional[bool],
    keepalive: Optional[bool],
    print_envelopes: bool,
) -> None:
    """Watch gossip notifications and update overlay cache."""
    root = Path.cwd()
    try:
        run_gossip_watch(
            root,
            project_label,
            transport,
            broker,
            autostart,
            keepalive,
            print_envelopes,
        )
    except GossipError as error:
        raise click.ClickException(str(error)) from error


@cli.group()
def overlay() -> None:
    """Overlay cache commands."""


@overlay.command("gc")
@click.option("--project", "project_label", default=None)
@click.option("--all", "all_projects", is_flag=True, default=False)
def overlay_gc(project_label: Optional[str], all_projects: bool) -> None:
    """Sweep overlay cache entries."""
    root = Path.cwd()
    try:
        count = gc_overlay_for_projects(root, project_label, all_projects)
    except (ConfigurationError, ProjectMarkerError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"overlay gc complete ({count} project(s))")


@overlay.command("reconcile")
@click.option("--project", "project_label", default=None)
@click.option("--all", "all_projects", is_flag=True, default=False)
@click.option("--prune", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
def overlay_reconcile(
    project_label: Optional[str],
    all_projects: bool,
    prune: bool,
    dry_run: bool,
) -> None:
    """Reconcile overlay cache entries against canonical issue files."""
    root = Path.cwd()
    try:
        stats = reconcile_overlay_for_projects(
            root,
            project_label=project_label,
            all_projects=all_projects,
            prune=prune,
            dry_run=dry_run,
        )
    except (ConfigurationError, ProjectMarkerError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        "overlay reconcile complete "
        f"(projects={stats.projects}, scanned={stats.issues_scanned}, "
        f"updated={stats.issues_updated}, removed={stats.issues_removed}, "
        f"pruned={stats.fields_pruned})"
    )


@overlay.command("install-hooks")
def overlay_install_hooks() -> None:
    """Install git hooks to run overlay gc after git operations."""
    root = Path.cwd()
    try:
        install_overlay_hooks(root)
    except (ConfigurationError, ProjectMarkerError, OSError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error
    click.echo("overlay hooks installed")


def _format_project_marker_error(error: ProjectMarkerError) -> str:
    message = str(error)
    if message.startswith("multiple projects found"):
        return (
            "multiple projects found. Run this command from a directory containing a "
            "single project/ folder."
        )
    if message == "project not initialized":
        return 'project not initialized. Run "kanbus init" to create a project/ folder.'
    return message


@cli.group()
def snyk() -> None:
    """Snyk vulnerability synchronization commands."""


@snyk.command(name="pull")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be done without writing files.",
)
@click.option(
    "--min-severity",
    default=None,
    help="Override minimum severity (critical, high, medium, low).",
)
@click.option(
    "--org-id",
    default=None,
    help="Override Snyk org ID.",
)
@click.option(
    "--parent-epic",
    default=None,
    help="Override parent epic issue ID to attach bugs to.",
)
@click.pass_context
def snyk_pull(
    context: click.Context,
    dry_run: bool,
    min_severity: Optional[str],
    org_id: Optional[str],
    parent_epic: Optional[str],
) -> None:
    """Pull vulnerabilities from Snyk into Kanbus."""
    from kanbus.snyk_sync import SnykSyncError, pull_from_snyk

    root = Path.cwd()
    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
    except ProjectMarkerError as error:
        raise click.ClickException(_format_project_marker_error(error)) from error
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error

    if configuration.snyk is None:
        raise click.ClickException("no snyk configuration in .kanbus.yml")

    snyk_config = configuration.snyk.model_copy(
        update={
            k: v
            for k, v in {
                "min_severity": min_severity,
                "org_id": org_id,
                "parent_epic": parent_epic,
            }.items()
            if v is not None
        }
    )

    if dry_run:
        click.echo("Dry run — no files will be written.\n")

    try:
        result = pull_from_snyk(root, snyk_config, configuration.project_key, dry_run)
    except SnykSyncError as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        f"pulled {result.pulled} new, updated {result.updated} existing, "
        f"skipped {result.skipped} duplicates"
    )


@cli.group()
def jira() -> None:
    """Jira synchronization commands."""


@jira.command(name="pull")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be done without writing files.",
)
@click.pass_context
def jira_pull(context: click.Context, dry_run: bool) -> None:
    """Pull issues from Jira into Kanbus."""
    from kanbus.jira_sync import JiraSyncError, pull_from_jira

    root = Path.cwd()
    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
    except ProjectMarkerError as error:
        raise click.ClickException(_format_project_marker_error(error)) from error
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error

    if configuration.jira is None:
        raise click.ClickException("no jira configuration in .kanbus.yml")

    if configuration.jira.sync_direction not in ("pull", "both"):
        raise click.ClickException(
            "sync_direction must be 'pull' or 'both' to use jira pull"
        )

    if dry_run:
        click.echo("Dry run — no files will be written.\n")

    try:
        result = pull_from_jira(
            root, configuration.jira, configuration.project_key, dry_run
        )
    except JiraSyncError as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"pulled {result.pulled} new, updated {result.updated} existing")


@cli.group(name="github")
def github_security() -> None:
    """GitHub security synchronization commands."""


@cli.group(name="gh")
def github_security_short() -> None:
    """Alias for GitHub security synchronization commands."""


@github_security.group()
def dependabot() -> None:
    """Dependabot synchronization commands."""


@github_security_short.group(name="dependabot")
def dependabot_short() -> None:
    """Dependabot synchronization commands."""


def _run_github_dependabot_pull(
    context: click.Context,
    dry_run: bool,
    repo: Optional[str],
    min_severity: Optional[str],
    state: Optional[str],
    parent_epic: Optional[str],
) -> None:
    """Pull Dependabot alerts from GitHub into Kanbus."""
    from kanbus.github_security_sync import (
        GithubSecuritySyncError,
        pull_dependabot_from_github,
        pull_dependabot_from_github_beads,
    )
    from kanbus.models import DependabotConfiguration, GithubSecurityConfiguration

    root = Path.cwd()
    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
    except ProjectMarkerError as error:
        raise click.ClickException(_format_project_marker_error(error)) from error
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error

    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    root_for_beads = config_path.parent

    github_security_config = (
        configuration.github_security
        or GithubSecurityConfiguration(
            repo=None,
            dependabot=None,
        )
    )
    dependabot_config = github_security_config.dependabot or DependabotConfiguration()

    if repo is not None:
        github_security_config = github_security_config.model_copy(
            update={"repo": repo}
        )
    if min_severity is not None:
        dependabot_config = dependabot_config.model_copy(
            update={"min_severity": min_severity}
        )
    if state is not None:
        dependabot_config = dependabot_config.model_copy(update={"state": state})
    if parent_epic is not None:
        dependabot_config = dependabot_config.model_copy(
            update={"parent_epic": parent_epic}
        )

    github_security_config = github_security_config.model_copy(
        update={"dependabot": dependabot_config}
    )

    if dry_run:
        click.echo("Dry run — no files will be written.\n")

    try:
        if beads_mode:
            result = pull_dependabot_from_github_beads(
                root_for_beads,
                github_security_config,
                dry_run,
            )
        else:
            result = pull_dependabot_from_github(
                root,
                github_security_config,
                configuration.project_key,
                dry_run,
            )
    except GithubSecuritySyncError as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        f"pulled {result.pulled} new, updated {result.updated} existing, "
        f"skipped {result.skipped} duplicates"
    )


@dependabot.command(name="pull")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be done without writing files.",
)
@click.option(
    "--repo",
    default=None,
    help="Override GitHub repository slug (owner/repo).",
)
@click.option(
    "--min-severity",
    default=None,
    help="Override minimum severity (critical, high, medium, low).",
)
@click.option(
    "--state",
    default=None,
    help="Override Dependabot alert state filter.",
)
@click.option(
    "--parent-epic",
    default=None,
    help="Override parent epic issue ID to attach findings to.",
)
@click.pass_context
def github_dependabot_pull(
    context: click.Context,
    dry_run: bool,
    repo: Optional[str],
    min_severity: Optional[str],
    state: Optional[str],
    parent_epic: Optional[str],
) -> None:
    """Pull Dependabot alerts from GitHub into Kanbus."""
    _run_github_dependabot_pull(
        context,
        dry_run=dry_run,
        repo=repo,
        min_severity=min_severity,
        state=state,
        parent_epic=parent_epic,
    )


@dependabot_short.command(name="pull")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be done without writing files.",
)
@click.option(
    "--repo",
    default=None,
    help="Override GitHub repository slug (owner/repo).",
)
@click.option(
    "--min-severity",
    default=None,
    help="Override minimum severity (critical, high, medium, low).",
)
@click.option(
    "--state",
    default=None,
    help="Override Dependabot alert state filter.",
)
@click.option(
    "--parent-epic",
    default=None,
    help="Override parent epic issue ID to attach findings to.",
)
@click.pass_context
def github_dependabot_pull_short(
    context: click.Context,
    dry_run: bool,
    repo: Optional[str],
    min_severity: Optional[str],
    state: Optional[str],
    parent_epic: Optional[str],
) -> None:
    """Pull Dependabot alerts from GitHub into Kanbus."""
    _run_github_dependabot_pull(
        context,
        dry_run=dry_run,
        repo=repo,
        min_severity=min_severity,
        state=state,
        parent_epic=parent_epic,
    )


@cli.command("issues", hidden=True)
@click.pass_context
def issues_alias(context: click.Context) -> None:
    """Alias for: kbs list"""
    context.invoke(list_command)


@cli.command("epics", hidden=True)
@click.pass_context
def epics_alias(context: click.Context) -> None:
    """Alias for: kbs list --type epic"""
    context.invoke(list_command, issue_type="epic")


@cli.command("tasks", hidden=True)
@click.pass_context
def tasks_alias(context: click.Context) -> None:
    """Alias for: kbs list --type task"""
    context.invoke(list_command, issue_type="task")


@cli.command("stories", hidden=True)
@click.pass_context
def stories_alias(context: click.Context) -> None:
    """Alias for: kbs list --type story"""
    context.invoke(list_command, issue_type="story")


@cli.command("bugs", hidden=True)
@click.pass_context
def bugs_alias(context: click.Context) -> None:
    """Alias for: kbs list --type bug"""
    context.invoke(list_command, issue_type="bug")


if __name__ == "__main__":
    cli()
