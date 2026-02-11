"""Taskulus CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

from taskulus.file_io import (
    InitializationError,
    ensure_git_repository,
    initialize_project,
)


@click.group()
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


if __name__ == "__main__":
    cli()
