"""Helpers for managing AGENTS.md Kanbus instructions."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import click
from jinja2 import Environment

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.models import ProjectConfiguration
from kanbus.project import ProjectMarkerError, get_configuration_path
from kanbus.project_management_template import (
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE,
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
)
from kanbus.file_io import _write_project_guard_files, _write_tool_block_files

KANBUS_SECTION_HEADER = "## Project management with Kanbus"
KANBUS_SECTION_LINES = [
    KANBUS_SECTION_HEADER,
    "",
    "Use Kanbus for task management.",
    "Why: Kanbus task management is MANDATORY here; every task must live in Kanbus.",
    "When: Create/update the Kanbus task before coding; close it only after the change lands.",
    "How: See CONTRIBUTING_AGENT.md for the Kanbus workflow, hierarchy, status rules, priorities, command examples, and the sins to avoid. Never inspect project/ or issue JSON directly (including with cat or jq); use Kanbus commands only.",
    "Performance: Prefer kanbusr (Rust) when available; kanbus (Python) is equivalent but slower.",
    "Warning: Editing project/ directly is a sin against The Way. Do not read or write anything in project/; work only through Kanbus.",
    "",
]
KANBUS_SECTION_TEXT = "\n".join(KANBUS_SECTION_LINES)
AGENTS_HEADER_LINES = ["# Agent Instructions", ""]
PROJECT_MANAGEMENT_FILENAME = "CONTRIBUTING_AGENT.md"


@dataclass(frozen=True)
class SectionMatch:
    """Represents a matched Markdown section range."""

    start: int
    end: int
    level: int


def ensure_agents_file(root: Path, force: bool) -> bool:
    """Ensure AGENTS.md exists and contains the Kanbus section.

    :param root: Repository root path.
    :type root: Path
    :param force: Whether to overwrite existing Kanbus section.
    :type force: bool
    :return: True if the file was modified.
    :rtype: bool
    :raises click.ClickException: If overwrite is required but not confirmed.
    """
    instructions_text = build_project_management_text(root)
    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        content = "\n".join(AGENTS_HEADER_LINES + KANBUS_SECTION_LINES)
        agents_path.write_text(content, encoding="utf-8")
        _ensure_project_management_file(root, force, instructions_text)
        return True

    lines = agents_path.read_text(encoding="utf-8").splitlines()
    matches = _find_kanbus_sections(lines)
    if matches:
        if not force:
            if not _confirm_overwrite():
                _ensure_project_management_file(root, force, instructions_text)
                _ensure_project_guard_files(root)
                _ensure_tool_block_files(root)
                return False
        updated = _replace_sections(lines, matches, matches[0], KANBUS_SECTION_LINES)
        agents_path.write_text(updated, encoding="utf-8")
        _ensure_project_management_file(root, force, instructions_text)
        _ensure_project_guard_files(root)
        _ensure_tool_block_files(root)
        return True

    updated_lines = _insert_kanbus_section(lines, KANBUS_SECTION_LINES)
    agents_path.write_text(updated_lines, encoding="utf-8")
    _ensure_project_management_file(root, force, instructions_text)
    _ensure_project_guard_files(root)
    _ensure_tool_block_files(root)
    return True


def _ensure_project_management_file(
    root: Path, force: bool, instructions_text: str
) -> None:
    instructions_path = root / PROJECT_MANAGEMENT_FILENAME
    if instructions_path.exists() and not force:
        return
    instructions_path.write_text(instructions_text, encoding="utf-8")


def _ensure_project_guard_files(root: Path) -> None:
    _write_project_guard_files(root / "project")


def _ensure_tool_block_files(root: Path) -> None:
    _write_tool_block_files(root)


def build_project_management_text(root: Path) -> str:
    """Build CONTRIBUTING_AGENT.md content from configuration.

    :param root: Repository root path.
    :type root: Path
    :return: Rendered project management instructions.
    :rtype: str
    :raises click.ClickException: If configuration is missing or invalid.
    """
    configuration = _load_configuration_for_instructions(root)
    template_path = _resolve_project_management_template_path(root, configuration)
    if template_path is None:
        template_text = DEFAULT_PROJECT_MANAGEMENT_TEMPLATE
    else:
        template_text = template_path.read_text(encoding="utf-8")
    context = _build_project_management_context(configuration)
    environment = Environment(autoescape=False)
    try:
        return environment.from_string(template_text).render(context)
    except Exception as error:
        raise click.ClickException(str(error)) from error


def _load_configuration_for_instructions(root: Path) -> ProjectConfiguration:
    try:
        configuration_path = get_configuration_path(root)
        return load_project_configuration(configuration_path)
    except ProjectMarkerError as error:
        raise click.ClickException(str(error)) from error
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from error


def _resolve_project_management_template_path(
    root: Path, configuration: ProjectConfiguration
) -> Optional[Path]:
    configured = configuration.project_management_template
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = root / configured
        if not path.exists():
            raise click.ClickException(f"project management template not found: {path}")
        return path
    conventional = root / DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME
    if conventional.exists():
        return conventional
    return None


def _build_project_management_context(
    configuration: ProjectConfiguration,
) -> dict[str, object]:
    hierarchy = configuration.hierarchy
    types = configuration.types
    workflows = _build_workflow_context(configuration.workflows)
    priorities = _build_priority_context(configuration.priorities)
    default_priority = configuration.priorities.get(configuration.default_priority)
    default_priority_name = (
        default_priority.name
        if default_priority
        else str(configuration.default_priority)
    )
    return {
        "project_key": configuration.project_key,
        "hierarchy_order": " -> ".join(hierarchy) if hierarchy else "none",
        "non_hierarchical_types": list(types),
        "parent_child_rules": _build_parent_child_rules(hierarchy, types),
        "initial_status": configuration.initial_status,
        "workflows": workflows,
        "priorities": priorities,
        "default_priority_value": configuration.default_priority,
        "default_priority_name": default_priority_name,
        "command_examples": _build_command_examples(configuration),
        "semantic_release_mapping": _build_semantic_release_mapping(types),
        "has_story": any(value.lower() == "story" for value in types),
        "gherkin_example": [
            "Feature:",
            "Scenario:",
            "Given",
            "When",
            "Then",
        ],
    }


def _build_parent_child_rules(hierarchy: List[str], types: List[str]) -> List[str]:
    rules: List[str] = []
    if len(hierarchy) > 1:
        for index in range(1, len(hierarchy)):
            child = hierarchy[index]
            parent = hierarchy[index - 1]
            rules.append(f"{child} can have parent {parent}.")
    if types:
        parents = hierarchy[:-1]
        if parents:
            rules.append(f"{', '.join(types)} can have parent {', '.join(parents)}.")
        else:
            rules.append(f"{', '.join(types)} cannot have parents.")
    if len(hierarchy) <= 1 and not types:
        rules.append("No parent-child relationships are defined.")
    return rules


def _build_workflow_context(
    workflows: dict[str, dict[str, List[str]]],
) -> List[dict[str, object]]:
    context: List[dict[str, object]] = []
    for workflow_name in sorted(workflows):
        workflow = workflows[workflow_name]
        statuses = []
        for status in sorted(workflow):
            transitions = workflow[status]
            statuses.append({"name": status, "transitions": list(transitions)})
        context.append({"name": workflow_name, "statuses": statuses})
    return context


def _build_priority_context(
    priorities: dict[int, object],
) -> List[dict[str, object]]:
    context: List[dict[str, object]] = []
    for value in sorted(priorities):
        definition = priorities[value]
        context.append({"value": value, "name": definition.name})
    return context


def _build_command_examples(configuration: ProjectConfiguration) -> List[str]:
    hierarchy = configuration.hierarchy
    types = configuration.types
    priorities = sorted(configuration.priorities)
    priority_example = priorities[0] if priorities else configuration.default_priority
    workflow_name = (
        "default"
        if "default" in configuration.workflows
        else sorted(configuration.workflows)[0]
    )
    workflow = configuration.workflows[workflow_name]
    status_example = _select_status_example(configuration.initial_status, workflow)
    status_set = _collect_statuses(workflow)
    lines: List[str] = []
    if hierarchy:
        lines.append(f'kanbus create "Plan the roadmap" --type {hierarchy[0]}')
    if len(hierarchy) > 1:
        lines.append(
            f'kanbus create "Release v1" --type {hierarchy[1]} '
            f"--parent <{hierarchy[0]}-id>"
        )
    if len(hierarchy) > 2:
        lines.append(
            f'kanbus create "Implement feature" --type {hierarchy[2]} '
            f"--parent <{hierarchy[1]}-id>"
        )
    if types:
        parent = hierarchy[1] if len(hierarchy) > 1 else None
        parent_fragment = f" --parent <{parent}-id>" if parent else ""
        lines.append(
            f'kanbus create "Fix crash on launch" --type {types[0]} '
            f"--priority {priority_example}{parent_fragment}"
        )
    lines.append(
        f'kanbus update <id> --status {status_example} --assignee "you@example.com"'
    )
    if "blocked" in status_set and status_example != "blocked":
        lines.append("kanbus update <id> --status blocked")
    lines.append('kanbus comment <id> "Progress note"')
    lines.append(f"kanbus list --status {configuration.initial_status}")
    lines.append('kanbus close <id> --comment "Summary of the change"')
    return lines


def _build_semantic_release_mapping(types: List[str]) -> List[dict[str, str]]:
    mapping: List[dict[str, str]] = []
    for issue_type in types:
        lowered = issue_type.lower()
        if "bug" in lowered or "fix" in lowered:
            category = "fix"
        elif "story" in lowered or "feature" in lowered:
            category = "feat"
        elif "chore" in lowered or "maintenance" in lowered:
            category = "chore"
        else:
            category = "chore"
        mapping.append({"type": issue_type, "category": category})
    return mapping


def _collect_statuses(workflow: dict[str, List[str]]) -> set[str]:
    statuses = set(workflow.keys())
    for transitions in workflow.values():
        statuses.update(transitions)
    return statuses


def _select_status_example(initial_status: str, workflow: dict[str, List[str]]) -> str:
    if initial_status in workflow and workflow[initial_status]:
        return workflow[initial_status][0]
    for transitions in workflow.values():
        if transitions:
            return transitions[0]
    return initial_status


def _confirm_overwrite() -> bool:
    if os.getenv("KANBUS_NON_INTERACTIVE") == "1":
        raise click.ClickException(
            "Kanbus section already exists in AGENTS.md. Re-run with --force to overwrite."
        )
    if os.getenv("KANBUS_FORCE_INTERACTIVE") != "1":
        stream = click.get_text_stream("stdin")
        isatty = getattr(stream, "isatty", None)
        if callable(isatty) and not isatty():
            raise click.ClickException(
                "Kanbus section already exists in AGENTS.md. Re-run with --force to overwrite."
            )
    try:
        return click.confirm(
            "Kanbus section already exists in AGENTS.md. Overwrite it?",
            default=False,
        )
    except (click.Abort, EOFError) as error:
        raise click.ClickException(
            "Kanbus section already exists in AGENTS.md. Re-run with --force to overwrite."
        ) from error


def _find_kanbus_sections(lines: List[str]) -> List[SectionMatch]:
    matches: List[SectionMatch] = []
    for index, line in enumerate(lines):
        header = _parse_header(line)
        if not header:
            continue
        level, text = header
        if "kanbus" not in text.lower():
            continue
        end = _find_section_end(lines, index + 1, level)
        matches.append(SectionMatch(start=index, end=end, level=level))
    return matches


def _find_section_end(lines: List[str], start: int, level: int) -> int:
    for index in range(start, len(lines)):
        header = _parse_header(lines[index])
        if not header:
            continue
        next_level, _ = header
        if next_level <= level:
            return index
    return len(lines)


def _parse_header(line: str) -> Optional[Tuple[int, str]]:
    match = re.match(r"^(#{1,6})\s+(.*)$", line.rstrip())
    if not match:
        return None
    level = len(match.group(1))
    text = match.group(2).strip()
    if not text:
        return None
    return level, text


def _replace_sections(
    lines: List[str],
    matches: List[SectionMatch],
    primary: SectionMatch,
    section_lines: List[str],
) -> str:
    updated_lines: List[str] = []
    inserted = False
    for index, line in enumerate(lines):
        if _is_in_sections(index, matches):
            if index == primary.start and not inserted:
                updated_lines.extend(section_lines)
                inserted = True
            continue
        updated_lines.append(line)
    if not inserted:
        updated_lines.extend(section_lines)
    return _join_lines(updated_lines)


def _is_in_sections(index: int, matches: List[SectionMatch]) -> bool:
    return any(match.start <= index < match.end for match in matches)


def _insert_kanbus_section(lines: List[str], section_lines: List[str]) -> str:
    insert_index = _find_insert_index(lines)
    updated = list(lines)
    if (
        insert_index > 0
        and insert_index < len(updated)
        and updated[insert_index].strip()
    ):
        updated.insert(insert_index, "")
        insert_index += 1
    updated[insert_index:insert_index] = section_lines
    return _join_lines(updated)


def _find_insert_index(lines: List[str]) -> int:
    for index, line in enumerate(lines):
        header = _parse_header(line)
        if header and header[0] == 1:
            insert_index = index + 1
            while insert_index < len(lines) and not lines[insert_index].strip():
                insert_index += 1
            return insert_index
    return 0


def _join_lines(lines: List[str]) -> str:
    return "\n".join(lines) + "\n"
