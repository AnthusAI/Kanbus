"""Taskulus CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import click

from taskulus import __version__
from taskulus.file_io import (
    InitializationError,
    ensure_git_repository,
    initialize_project,
)
from taskulus.issue_creation import IssueCreationError, create_issue
from taskulus.issue_close import IssueCloseError, close_issue
from taskulus.issue_comment import IssueCommentError, add_comment
from taskulus.issue_delete import IssueDeleteError, delete_issue
from taskulus.issue_display import format_issue_for_display
from taskulus.issue_lookup import IssueLookupError, load_issue_from_project
from taskulus.issue_update import IssueUpdateError, update_issue
from taskulus.issue_listing import IssueListingError, list_issues
from taskulus.queries import QueryError
from taskulus.daemon_client import DaemonClientError, request_shutdown, request_status
from taskulus.users import get_current_user
from taskulus.migration import MigrationError, migrate_from_beads
from taskulus.doctor import DoctorError, run_doctor
from taskulus.dependencies import (
    DependencyError,
    add_dependency,
    list_ready_issues,
    remove_dependency,
)


@click.group()
@click.version_option(__version__, prog_name="tsk")
def cli() -> None:
    """Taskulus command line interface."""


@cli.command("init")
@click.option("--dir", "project_dir", default="project", show_default=True)
def init(project_dir: str) -> None:
    """Initialize a Taskulus project in the current repository.

    :param project_dir: Project directory name.
    :type project_dir: str
    """
    root = Path.cwd()
    try:
        ensure_git_repository(root)
        initialize_project(root, project_dir)
    except InitializationError as error:
        raise click.ClickException(str(error)) from error


@cli.command("create")
@click.argument("title", nargs=-1)
@click.option("--type", "issue_type")
@click.option("--priority", type=int)
@click.option("--assignee")
@click.option("--parent")
@click.option("--label", "labels", multiple=True)
@click.option("--description", default="")
def create(
    title: tuple[str, ...],
    issue_type: str | None,
    priority: int | None,
    assignee: str | None,
    parent: str | None,
    labels: tuple[str, ...],
    description: str,
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
    """
    title_text = " ".join(title).strip()
    description_text = description.strip()
    if not title_text:
        raise click.ClickException("title is required")

    root = Path.cwd()
    try:
        issue = create_issue(
            root=root,
            title=title_text,
            issue_type=issue_type,
            priority=priority,
            assignee=assignee,
            parent=parent,
            labels=labels,
            description=description_text,
        )
    except IssueCreationError as error:
        raise click.ClickException(str(error)) from error

    click.echo(issue.identifier)


@cli.command("show")
@click.argument("identifier")
@click.option("--json", "as_json", is_flag=True)
def show(identifier: str, as_json: bool) -> None:
    """Show details for an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :param as_json: Emit JSON output when set.
    :type as_json: bool
    """
    root = Path.cwd()
    try:
        lookup = load_issue_from_project(root, identifier)
    except IssueLookupError as error:
        raise click.ClickException(str(error)) from error

    if as_json:
        payload = lookup.issue.model_dump(by_alias=True, mode="json")
        click.echo(json.dumps(payload, indent=2, sort_keys=False))
        return

    click.echo(format_issue_for_display(lookup.issue))


@cli.command("update")
@click.argument("identifier")
@click.option("--title")
@click.option("--description")
@click.option("--status")
def update(
    identifier: str,
    title: str | None,
    description: str | None,
    status: str | None,
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
    """
    root = Path.cwd()
    try:
        update_issue(
            root=root,
            identifier=identifier,
            title=title.strip() if title else None,
            description=description.strip() if description else None,
            status=status,
        )
    except IssueUpdateError as error:
        raise click.ClickException(str(error)) from error


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


@cli.command("delete")
@click.argument("identifier")
def delete(identifier: str) -> None:
    """Delete an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path.cwd()
    try:
        delete_issue(root, identifier)
    except IssueDeleteError as error:
        raise click.ClickException(str(error)) from error


@cli.command("comment")
@click.argument("identifier")
@click.argument("text")
def comment(identifier: str, text: str) -> None:
    """Add a comment to an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :param text: Comment text.
    :type text: str
    """
    root = Path.cwd()
    try:
        add_comment(
            root=root,
            identifier=identifier,
            author=get_current_user(),
            text=text,
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
def list_command(
    status: str | None,
    issue_type: str | None,
    assignee: str | None,
    label: str | None,
    sort: str | None,
    search: str | None,
) -> None:
    """List issues in the current project."""
    root = Path.cwd()
    try:
        issues = list_issues(
            root,
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            label=label,
            sort=sort,
            search=search,
        )
    except (IssueListingError, QueryError) as error:
        raise click.ClickException(str(error)) from error

    for issue in issues:
        click.echo(f"{issue.identifier} {issue.title}")


@cli.group("dep")
def dep() -> None:
    """Manage issue dependencies."""


@dep.command("add")
@click.argument("identifier")
@click.option("--blocked-by")
@click.option("--relates-to")
def dep_add(identifier: str, blocked_by: str | None, relates_to: str | None) -> None:
    """Add a dependency to an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :param blocked_by: Blocked-by dependency target.
    :type blocked_by: str | None
    :param relates_to: Relates-to dependency target.
    :type relates_to: str | None
    :raises click.ClickException: If dependency addition fails.
    """
    target_id = blocked_by or relates_to
    dependency_type = "blocked-by" if blocked_by else "relates-to"
    if target_id is None:
        raise click.ClickException("dependency target is required")
    root = Path.cwd()
    try:
        add_dependency(root, identifier, target_id, dependency_type)
    except DependencyError as error:
        raise click.ClickException(str(error)) from error


@dep.command("remove")
@click.argument("identifier")
@click.option("--blocked-by")
@click.option("--relates-to")
def dep_remove(
    identifier: str, blocked_by: str | None, relates_to: str | None
) -> None:
    """Remove a dependency from an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :param blocked_by: Blocked-by dependency target.
    :type blocked_by: str | None
    :param relates_to: Relates-to dependency target.
    :type relates_to: str | None
    :raises click.ClickException: If dependency removal fails.
    """
    target_id = blocked_by or relates_to
    dependency_type = "blocked-by" if blocked_by else "relates-to"
    if target_id is None:
        raise click.ClickException("dependency target is required")
    root = Path.cwd()
    try:
        remove_dependency(root, identifier, target_id, dependency_type)
    except DependencyError as error:
        raise click.ClickException(str(error)) from error


@cli.command("ready")
def ready() -> None:
    """List issues that are ready (not blocked)."""
    root = Path.cwd()
    try:
        issues = list_ready_issues(root)
    except DependencyError as error:
        raise click.ClickException(str(error)) from error
    for issue in issues:
        click.echo(issue.identifier)


@cli.command("doctor")
def doctor() -> None:
    """Run environment diagnostics for Taskulus."""
    root = Path.cwd()
    try:
        result = run_doctor(root)
    except DoctorError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"ok {result.project_dir}")


@cli.command("migrate")
def migrate() -> None:
    """Migrate Beads issues into Taskulus.

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
    except DaemonClientError as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(result, indent=2, sort_keys=False))


@cli.command("daemon-stop")
def daemon_stop() -> None:
    """Stop the daemon process."""
    root = Path.cwd()
    try:
        result = request_shutdown(root)
    except DaemonClientError as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(result, indent=2, sort_keys=False))


if __name__ == "__main__":
    cli()
