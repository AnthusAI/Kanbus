"""
File system helpers for initialization.
"""

from __future__ import annotations

import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
import yaml

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.project_management_template import (
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE,
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
)
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.project import (
    ProjectMarkerError,
    ensure_project_local_directory,
    get_configuration_path,
)


class InitializationError(RuntimeError):
    """Raised when project initialization fails."""


@dataclass
class RepairPlan:
    project_dir: Path
    missing_project_dir: bool
    missing_issues_dir: bool
    missing_events_dir: bool


def ensure_git_repository(root: Path) -> None:
    """Ensure the provided path is inside a git repository.

    :param root: Directory to check for a git repository.
    :type root: Path
    :raises InitializationError: If the path is not a git repository.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise InitializationError("not a git repository")


def initialize_project(root: Path, create_local: bool = False) -> None:
    """Initialize the Kanbus project directory structure.

    :param root: Repository root path.
    :type root: Path
    :param create_local: Whether to create a project-local directory.
    :type create_local: bool
    :raises InitializationError: If the project is already initialized.
    """
    project_dir = root / "project"
    if project_dir.exists():
        raise InitializationError("already initialized")

    issues_dir = project_dir / "issues"
    events_dir = project_dir / "events"

    project_dir.mkdir(parents=True, exist_ok=False)
    issues_dir.mkdir(parents=True)
    events_dir.mkdir(parents=True)
    config_path = root / ".kanbus.yml"
    if not config_path.exists():
        config_path.write_text(
            yaml.safe_dump(DEFAULT_CONFIGURATION, sort_keys=False),
            encoding="utf-8",
        )
    _write_project_guard_files_if_missing(project_dir)
    _write_tool_block_files(root)
    _ensure_gitignore_entry(root, "project/.overlay/")
    template_path = root / DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME
    if not template_path.exists():
        template_path.write_text(
            DEFAULT_PROJECT_MANAGEMENT_TEMPLATE,
            encoding="utf-8",
        )
    if create_local:
        ensure_project_local_directory(project_dir)


def _ensure_gitignore_entry(root: Path, entry: str) -> None:
    gitignore_path = root / ".gitignore"
    existing = ""
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in existing.splitlines() if line.strip()]
    if entry in lines:
        return
    lines.append(entry)
    gitignore_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_guard_files_in_subdir(subdir: Path, folder_name: str) -> None:
    """Write AGENTS.md and DO_NOT_EDIT into a guarded subdir (e.g. issues/ or events/)."""
    agents_path = subdir / "AGENTS.md"
    agents_path.write_text(
        "\n".join(
            [
                "# DO NOT EDIT HERE",
                "",
                f"Do not read or write in this folder ({folder_name}/). Use Kanbus commands instead.",
                "Do not inspect issue JSON with tools like cat or jq.",
                "",
                "See ../../AGENTS.md and ../../CONTRIBUTING_AGENT.md for required process.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    do_not_edit = subdir / "DO_NOT_EDIT"
    do_not_edit.write_text(
        "\n".join(
            [
                f"DO NOT EDIT THIS FOLDER ({folder_name}/)",
                "This folder is guarded by The Way.",
                "All changes must go through Kanbus (see ../../AGENTS.md and ../../CONTRIBUTING_AGENT.md).",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_project_guard_files(project_dir: Path) -> None:
    issues_dir = project_dir / "issues"
    events_dir = project_dir / "events"
    if issues_dir.exists():
        _write_guard_files_in_subdir(issues_dir, "issues")
    if events_dir.exists():
        _write_guard_files_in_subdir(events_dir, "events")
    root_agents_path = project_dir / "AGENTS.md"
    root_agents_path.write_text(
        "\n".join(
            [
                "# Project directory",
                "",
                "Do not edit issues/ or events/ directly; use Kanbus for issues and events.",
                "You may edit wiki/ (e.g. Markdown) directly.",
                "",
                "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_project_guard_files_if_missing(project_dir: Path) -> None:
    issues_dir = project_dir / "issues"
    events_dir = project_dir / "events"
    for subdir, folder_name in [(issues_dir, "issues"), (events_dir, "events")]:
        if not subdir.exists():
            continue
        agents_path = subdir / "AGENTS.md"
        do_not_edit = subdir / "DO_NOT_EDIT"
        if not agents_path.exists() or not do_not_edit.exists():
            _write_guard_files_in_subdir(subdir, folder_name)
    root_agents_path = project_dir / "AGENTS.md"
    if not root_agents_path.exists():
        root_agents_path.write_text(
            "\n".join(
                [
                    "# Project directory",
                    "",
                    "Do not edit issues/ or events/ directly; use Kanbus for issues and events.",
                    "You may edit wiki/ (e.g. Markdown) directly.",
                    "",
                    "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )


def _write_tool_block_files(root: Path) -> None:
    cursorignore = root / ".cursorignore"
    if not cursorignore.exists():
        cursorignore.write_text("project/issues/\nproject/events/\n", encoding="utf-8")

    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    claude_settings = claude_dir / "settings.json"
    if not claude_settings.exists():
        claude_settings.write_text(
            json.dumps(
                {
                    "permissions": {
                        "deny": [
                            "Read(./project/issues/**)",
                            "Edit(./project/issues/**)",
                            "Read(./project/events/**)",
                            "Edit(./project/events/**)",
                        ]
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    vscode_dir = root / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    vscode_settings = vscode_dir / "settings.json"
    if not vscode_settings.exists():
        vscode_settings.write_text(
            json.dumps(
                {
                    "files.exclude": {
                        "**/project/issues/**": True,
                        "**/project/events/**": True,
                    },
                    "files.watcherExclude": {
                        "**/project/issues/**": True,
                        "**/project/events/**": True,
                    },
                    "search.exclude": {
                        "**/project/issues/**": True,
                        "**/project/events/**": True,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def detect_repairable_project_issues(
    root: Path, *, allow_uninitialized: bool
) -> RepairPlan | None:
    try:
        config_path = get_configuration_path(root)
    except ProjectMarkerError as error:
        if allow_uninitialized:
            return None
        raise error
    except ConfigurationError as error:
        raise error

    configuration = load_project_configuration(config_path)
    project_dir = config_path.parent / configuration.project_directory
    try:
        project_dir_stat = project_dir.stat()
    except FileNotFoundError:
        project_dir_stat = None
    missing_project_dir = project_dir_stat is None

    missing_issues_dir = False
    missing_events_dir = False
    if not missing_project_dir:
        try:
            (project_dir / "issues").stat()
        except FileNotFoundError:
            missing_issues_dir = True
        try:
            (project_dir / "events").stat()
        except FileNotFoundError:
            missing_events_dir = True

    if missing_project_dir or missing_issues_dir or missing_events_dir:
        return RepairPlan(
            project_dir=project_dir,
            missing_project_dir=missing_project_dir,
            missing_issues_dir=missing_issues_dir,
            missing_events_dir=missing_events_dir,
        )
    return None


def repair_project_structure(root: Path, plan: RepairPlan) -> None:
    if plan.missing_project_dir:
        plan.project_dir.mkdir(parents=True, exist_ok=True)
    if plan.missing_issues_dir:
        (plan.project_dir / "issues").mkdir(parents=True, exist_ok=True)
    if plan.missing_events_dir:
        (plan.project_dir / "events").mkdir(parents=True, exist_ok=True)
    if plan.project_dir.exists():
        _write_project_guard_files_if_missing(plan.project_dir)

    vscode_dir = root / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    vscode_settings = vscode_dir / "settings.json"
    if not vscode_settings.exists():
        vscode_settings.write_text(
            json.dumps(
                {
                    "files.exclude": {
                        "**/project/issues/**": True,
                        "**/project/events/**": True,
                    },
                    "files.watcherExclude": {
                        "**/project/issues/**": True,
                        "**/project/events/**": True,
                    },
                    "search.exclude": {
                        "**/project/issues/**": True,
                        "**/project/events/**": True,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
