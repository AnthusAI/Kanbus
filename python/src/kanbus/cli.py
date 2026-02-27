"""Kanbus CLI entry point."""

from __future__ import annotations

import json
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
from kanbus.issue_delete import IssueDeleteError, delete_issue
from kanbus.beads_write import (
    BeadsDeleteError,
    BeadsWriteError,
    create_beads_issue,
    delete_beads_issue,
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
from kanbus.migration import MigrationError, load_beads_issue, migrate_from_beads
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
from kanbus.wiki import WikiError, WikiRenderRequest, render_wiki_page
from kanbus.console_snapshot import ConsoleSnapshotError, build_console_snapshot
from kanbus.console_ui_state import fetch_console_ui_state
from kanbus.notification_publisher import publish_notification
from kanbus.project import ProjectMarkerError, get_configuration_path
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.agents_management import _ensure_project_guard_files, ensure_agents_file


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


@click.group()
@click.version_option(__version__, prog_name="kanbus")
@click.option("--beads", "beads_mode", is_flag=True, default=False)
@click.pass_context
def cli(context: click.Context, beads_mode: bool) -> None:
    """Kanbus issue tracker CLI.

    \b
    Quick start:
      kbs list                           list all issues
      kbs create "Fix bug" --type bug    create an issue
      kbs update <id> --status done      update an issue
      kbs comment <id> "Note"            add a comment
      kbs close <id>                     close an issue

    \b
    Issue types:  initiative > epic > story / task / bug > sub-task
    Statuses:     open  in_progress  blocked  done  closed
    Priorities:   0=critical  1=high  2=medium(default)  3=low  4=trivial
    """
    resolved, forced = _resolve_beads_mode(context, beads_mode)
    context.obj = {"beads_mode": resolved, "beads_mode_forced": forced}
    _maybe_prompt_project_repair(context)


def _should_check_project_structure(context: click.Context) -> bool:
    if context.invoked_subcommand is None:
        return False
    return context.invoked_subcommand not in {"init", "setup", "repair"}


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
        if local_issue:
            raise click.ClickException("beads mode does not support local issues")
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
        return

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
            pass

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
        return

    click.echo(
        format_issue_for_display(
            issue,
            configuration=configuration,
            project_context=False,
        )
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
def update(
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
    if click.get_current_context().obj:
        beads_mode = bool(click.get_current_context().obj.get("beads_mode"))

    # Check if beads_compatibility is enabled in config
    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
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

    if beads_mode:
        if parent is not None:
            raise click.ClickException("parent update not supported in beads mode")
        try:
            update_beads_issue(
                root,
                identifier,
                status=status,
                title=title.strip() if title else None,
                description=description.strip() if description else None,
                priority=priority,
                assignee=assignee,
                add_labels=list(add_labels) if add_labels else None,
                remove_labels=list(remove_labels) if remove_labels else None,
                set_labels=parsed_set_labels,
            )
        except BeadsWriteError as error:
            raise click.ClickException(str(error)) from error
        formatted_identifier = format_issue_key(identifier, project_context=False)
        click.echo(f"Updated {formatted_identifier}")
        if update_quality_result:
            emit_signals(
                update_quality_result,
                "description",
                issue_id=identifier,
                is_update=True,
            )
        return

    # Regular Kanbus mode
    try:
        final_assignee = assignee or (get_current_user() if claim else None)
        update_issue(
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


@cli.command("close")
@click.argument("identifier")
def close(identifier: str) -> None:
    """Close an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    try:
        close_issue(root, identifier)
    except IssueCloseError as error:
        raise click.ClickException(str(error)) from error
    formatted_identifier = format_issue_key(identifier, project_context=False)
    click.echo(f"Closed {formatted_identifier}")


@cli.command("delete")
@click.argument("identifier")
def delete(identifier: str) -> None:
    """Delete an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    beads_mode = bool(click.get_current_context().obj.get("beads_mode"))

    # Check if beads_compatibility is enabled in config
    if not beads_mode:
        try:
            config = load_project_configuration(get_configuration_path(root))
            if config.beads_compatibility:
                beads_mode = True
        except (ConfigurationError, ProjectMarkerError):
            pass

    if beads_mode:
        try:
            delete_beads_issue(root, identifier)
        except BeadsDeleteError as error:
            raise click.ClickException(str(error)) from error
    else:
        try:
            delete_issue(root, identifier)
        except IssueDeleteError as error:
            raise click.ClickException(str(error)) from error
    formatted_identifier = format_issue_key(identifier, project_context=False)
    click.echo(f"Deleted {formatted_identifier}")


@cli.command("promote")
@click.argument("identifier")
def promote(identifier: str) -> None:
    """Promote a local issue to the shared project.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    try:
        promote_issue(root, identifier)
    except IssueTransferError as error:
        raise click.ClickException(str(error)) from error


@cli.command("localize")
@click.argument("identifier")
def localize(identifier: str) -> None:
    """Move a shared issue into project-local.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    try:
        localize_issue(root, identifier)
    except IssueTransferError as error:
        raise click.ClickException(str(error)) from error


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
        if beads_mode
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


def _issue_sort_timestamp(issue: IssueData) -> float:
    """Return a sortable UTC timestamp (seconds) for an issue."""

    timestamp = issue.closed_at or issue.updated_at or issue.created_at
    return timestamp.timestamp()


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
    from kanbus.issue_lookup import IssueLookupError, load_issue_from_project

    root = Path.cwd()
    try:
        result = load_issue_from_project(root, identifier)
        issue_id = result.issue.identifier
    except IssueLookupError as error:
        raise click.ClickException(str(error)) from error
    event: dict = {
        "type": "issue_focused",
        "issue_id": issue_id,
    }
    if comment:
        event["comment_id"] = comment
    publish_notification(root, event)
    if comment:
        click.echo(f"Focused on issue {issue_id} (comment {comment})")
    else:
        click.echo(f"Focused on issue {issue_id}")


@console.command("unfocus")
def console_unfocus() -> None:
    """Clear the current focus filter in the console."""
    root = Path.cwd()
    publish_notification(
        root, {"type": "ui_control", "action": {"action": "clear_focus"}}
    )
    click.echo("Cleared focus filter")


@console.command("view")
@click.argument("mode", type=click.Choice(["initiatives", "epics", "issues"]))
def console_view(mode: str) -> None:
    """Switch the console to a different view mode."""
    root = Path.cwd()
    publish_notification(
        root,
        {"type": "ui_control", "action": {"action": "set_view_mode", "mode": mode}},
    )
    click.echo(f"Switched to {mode} view")


@console.command("search")
@click.argument("query", required=False, default=None)
@click.option("--clear", is_flag=True, help="Clear the active search query.")
def console_search(query: Optional[str], clear: bool) -> None:
    """Set or clear the search query in the console."""
    root = Path.cwd()
    if clear:
        search_query = ""
    elif query:
        search_query = query
    else:
        raise click.UsageError("Provide a query or use --clear.")
    publish_notification(
        root,
        {
            "type": "ui_control",
            "action": {"action": "set_search", "query": search_query},
        },
    )
    if clear or not search_query:
        click.echo("Cleared search query")
    else:
        click.echo(f"Set search query to: {search_query}")


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
            pass

    if is_remove:
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
    else:
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


@cli.command("ready")
@click.option("--no-local", is_flag=True, default=False)
@click.option("--local-only", is_flag=True, default=False)
@click.pass_context
def ready(context: click.Context, no_local: bool, local_only: bool) -> None:
    """List issues that are ready (not blocked)."""
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
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
def migrate() -> None:
    """Migrate Beads issues into Kanbus.

    :raises click.ClickException: If migration fails.
    """
    root = Path.cwd()
    try:
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
