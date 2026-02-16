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
    ensure_git_repository,
    initialize_project,
)
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
    """Kanbus command line interface."""
    resolved, forced = _resolve_beads_mode(context, beads_mode)
    context.obj = {"beads_mode": resolved, "beads_mode_forced": forced}


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

    # Parse set_labels if provided
    parsed_set_labels = None
    if set_labels:
        parsed_set_labels = [label.strip() for label in set_labels.split(",")]

    if beads_mode:
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
        )
    except IssueUpdateError as error:
        raise click.ClickException(str(error)) from error

    formatted_identifier = format_issue_key(identifier, project_context=False)
    click.echo(f"Updated {formatted_identifier}")


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
@click.pass_context
def comment(
    context: click.Context,
    identifier: str,
    text: Optional[str],
    body_file: Optional[click.File],
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
        else:
            add_comment(
                root=root,
                identifier=identifier,
                author=get_current_user(),
                text=comment_text,
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
    no_local: bool,
    local_only: bool,
    limit: int,
    porcelain: bool,
) -> None:
    """List issues in the current project."""
    root = Path.cwd()
    beads_mode = bool(context.obj.get("beads_mode")) if context.obj else False
    beads_forced = bool(context.obj.get("beads_mode_forced")) if context.obj else False
    try:
        issues = list_issues(
            root,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            label=label,
            sort=sort,
            search=search,
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

    project_context = (
        beads_forced
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


@cli.command("dep", context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False})
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


if __name__ == "__main__":
    cli()
