"""
File system helpers for initialization.
"""

from __future__ import annotations

import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import yaml

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.project_management_template import (
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE,
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
)
from kanbus.wiki_templates import (
    DEFAULT_WIKI_INDEX,
    DEFAULT_WIKI_INDEX_FILENAME,
    DEFAULT_WIKI_WHATS_NEXT,
    DEFAULT_WIKI_WHATS_NEXT_FILENAME,
)
from kanbus.config_loader import ConfigurationError
from kanbus.models import ProjectConfiguration
from kanbus.project import (
    ProjectMarkerError,
    ensure_project_local_directory,
    get_configuration_path,
)
from kanbus.project_context import ProjectContext


class InitializationError(RuntimeError):
    """Raised when project initialization fails."""


PROJECT_WIKI_AGENTS_TEXT = "\n".join(
    [
        "# DO NOT EDIT HERE",
        "",
        "Editing anything under project/ directly is hacking the data and is a sin against The Way, except for project/wiki/*.md wiki pages which agents may create and edit directly.",
        "Do not read or write other files in this folder. Use Kanbus commands instead.",
        "",
        "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
    ]
)


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


CONFIGURATION_FIELD_ORDER = (
    "project_directory",
    "virtual_projects",
    "new_issue_project",
    "ignore_paths",
    "console_port",
    "project_key",
    "project_id",
    "name",
    "project_management_template",
    "methodologies",
    "hierarchy",
    "types",
    "workflows",
    "transition_labels",
    "initial_status",
    "priorities",
    "default_priority",
    "assignee",
    "time_zone",
    "statuses",
    "categories",
    "sort_order",
    "type_colors",
    "beads_compatibility",
    "events",
    "wiki_directory",
    "ai",
    "right_now",
    "standup",
    "jira",
    "snyk",
    "realtime",
    "overlay",
    "hooks",
    "github_security",
    "coordination",
    "router",
)
OMITTED_WHEN_UNSET_FIELDS = ("project_id", "name", "methodologies", "router")
RECURSIVELY_KEY_SORTED_FIELDS = ("workflows", "transition_labels", "type_colors")
TOP_LEVEL_KEY_SORTED_FIELDS = ("virtual_projects", "priorities", "sort_order")


def _sort_mapping_keys_recursively(value: object) -> object:
    """Return a copy of nested mappings with every mapping ordered by key."""
    if isinstance(value, dict):
        return {
            key: _sort_mapping_keys_recursively(value[key]) for key in sorted(value)
        }
    return value


def render_initial_configuration_yaml(project_identifier: str) -> str:
    """Render the default ``.kanbus.yml`` exactly as the Rust implementation does.

    Fields follow the declaration order of the Rust configuration struct, map
    fields are ordered by key, and optional fields that are unset and skipped
    during Rust serialization are omitted.

    :param project_identifier: UUID written as ``project_id``.
    :type project_identifier: str
    :return: YAML document text.
    :rtype: str
    """
    configuration = ProjectConfiguration.model_validate(
        {**DEFAULT_CONFIGURATION, "project_id": project_identifier}
    )
    dumped = configuration.model_dump(mode="python")
    ordered = {}
    for field_name in CONFIGURATION_FIELD_ORDER:
        value = dumped[field_name]
        if field_name in OMITTED_WHEN_UNSET_FIELDS and value is None:
            continue
        if field_name in RECURSIVELY_KEY_SORTED_FIELDS:
            value = _sort_mapping_keys_recursively(value)
        elif field_name in TOP_LEVEL_KEY_SORTED_FIELDS:
            value = {key: value[key] for key in sorted(value)}
        ordered[field_name] = value
    return yaml.safe_dump(ordered, sort_keys=False)


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
            render_initial_configuration_yaml(str(uuid4())),
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
    wiki_dir = project_dir / "wiki"
    wiki_dir.mkdir(parents=True)
    (wiki_dir / DEFAULT_WIKI_INDEX_FILENAME).write_text(
        DEFAULT_WIKI_INDEX, encoding="utf-8"
    )
    (wiki_dir / DEFAULT_WIKI_WHATS_NEXT_FILENAME).write_text(
        DEFAULT_WIKI_WHATS_NEXT, encoding="utf-8"
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
                "This folder is managed by Kanbus.",
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
    root_agents_path.write_text(PROJECT_WIKI_AGENTS_TEXT + "\n", encoding="utf-8")


def refresh_project_wiki_agents_file(project_dir: Path) -> None:
    """Write project/AGENTS.md with the wiki edit exception.

    :param project_dir: Absolute path to the project directory.
    :type project_dir: Path
    """
    root_agents_path = project_dir / "AGENTS.md"
    root_agents_path.write_text(PROJECT_WIKI_AGENTS_TEXT + "\n", encoding="utf-8")


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
        root_agents_path.write_text(PROJECT_WIKI_AGENTS_TEXT + "\n", encoding="utf-8")


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

    context = ProjectContext.from_configuration_path(root, config_path)
    return detect_repairable_project_issues_with_context(
        context, allow_uninitialized=allow_uninitialized
    )


def detect_repairable_project_issues_with_context(
    context: ProjectContext | None, *, allow_uninitialized: bool
) -> RepairPlan | None:
    """Detect missing project directories using an already built project context.

    :param context: Project context built at command entry, if a configuration exists.
    :type context: ProjectContext | None
    :param allow_uninitialized: Whether a missing configuration is tolerated.
    :type allow_uninitialized: bool
    :return: A repair plan, or None when the structure is healthy.
    :rtype: RepairPlan | None
    :raises ProjectMarkerError: If no configuration exists and it is not tolerated.
    """
    if context is None:
        if allow_uninitialized:
            return None
        raise ProjectMarkerError("project not initialized")
    configuration = context.configuration
    project_dir = context.repository_root / configuration.project_directory
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
