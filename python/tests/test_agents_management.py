from __future__ import annotations

from pathlib import Path

import click
import pytest

from kanbus import agents_management as agents
from kanbus.config_loader import ConfigurationError
from kanbus.models import PriorityDefinition, StatusDefinition
from kanbus.project import ProjectMarkerError

from test_helpers import build_project_configuration


def _config():
    cfg = build_project_configuration().model_copy(
        update={
            "project_key": "KB",
            "project_management_template": None,
            "transition_labels": {
                "default": {
                    "open": {"in_progress": "start", "closed": "close"},
                    "in_progress": {"open": "reopen", "closed": "finish"},
                    "closed": {"open": "reopen"},
                }
            },
            "statuses": [
                StatusDefinition(key="open", name="Open", category="To do"),
                StatusDefinition(
                    key="in_progress", name="In progress", category="In progress"
                ),
                StatusDefinition(key="closed", name="Closed", category="Done"),
                StatusDefinition(key="blocked", name="Blocked", category="In progress"),
            ],
            "priorities": {
                0: PriorityDefinition(name="critical"),
                2: PriorityDefinition(name="medium"),
            },
            "default_priority": 2,
            "hierarchy": ["initiative", "epic", "task"],
            "types": ["bug", "story", "chore"],
        }
    )
    return cfg


def test_ensure_agents_file_creates_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents, "build_project_management_text", lambda _root: "PM")
    calls: list[str] = []
    monkeypatch.setattr(agents, "_write_project_guard_files", lambda _p: calls.append("guard"))
    monkeypatch.setattr(agents, "_write_tool_block_files", lambda _p: calls.append("tools"))

    changed = agents.ensure_agents_file(tmp_path, force=False)
    assert changed is True
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / agents.PROJECT_MANAGEMENT_FILENAME).read_text(encoding="utf-8") == "PM"
    assert calls == []


def test_ensure_agents_file_existing_with_match_no_force_and_decline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("# Agent Instructions\n\n## Kanbus\nold\n", encoding="utf-8")

    monkeypatch.setattr(agents, "build_project_management_text", lambda _root: "PM")
    monkeypatch.setattr(agents, "_confirm_overwrite", lambda: False)

    calls: list[str] = []
    monkeypatch.setattr(agents, "_write_project_guard_files", lambda _p: calls.append("guard"))
    monkeypatch.setattr(agents, "_write_tool_block_files", lambda _p: calls.append("tools"))

    changed = agents.ensure_agents_file(tmp_path, force=False)
    assert changed is False
    assert calls == ["guard", "tools"]


def test_ensure_agents_file_existing_with_match_force_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("# Agent Instructions\n\n## Kanbus\nold\n", encoding="utf-8")

    monkeypatch.setattr(agents, "build_project_management_text", lambda _root: "PM")
    monkeypatch.setattr(agents, "_write_project_guard_files", lambda _p: None)
    monkeypatch.setattr(agents, "_write_tool_block_files", lambda _p: None)

    changed = agents.ensure_agents_file(tmp_path, force=True)
    assert changed is True
    text = agents_path.read_text(encoding="utf-8")
    assert agents.KANBUS_SECTION_HEADER in text
    assert "old" not in text


def test_ensure_agents_file_existing_without_match_inserts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("# Agent Instructions\n\n## Other\ntext\n", encoding="utf-8")

    monkeypatch.setattr(agents, "build_project_management_text", lambda _root: "PM")
    monkeypatch.setattr(agents, "_write_project_guard_files", lambda _p: None)
    monkeypatch.setattr(agents, "_write_tool_block_files", lambda _p: None)

    changed = agents.ensure_agents_file(tmp_path, force=False)
    assert changed is True
    assert agents.KANBUS_SECTION_HEADER in agents_path.read_text(encoding="utf-8")


def test_ensure_project_management_file_honors_force(tmp_path: Path) -> None:
    p = tmp_path / agents.PROJECT_MANAGEMENT_FILENAME
    p.write_text("old", encoding="utf-8")

    agents._ensure_project_management_file(tmp_path, force=False, instructions_text="new")
    assert p.read_text(encoding="utf-8") == "old"

    agents._ensure_project_management_file(tmp_path, force=True, instructions_text="new")
    assert p.read_text(encoding="utf-8") == "new"


def test_build_project_management_text_default_custom_and_template_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config()
    monkeypatch.setattr(agents, "_load_configuration_for_instructions", lambda _root: cfg)

    rendered = agents.build_project_management_text(tmp_path)
    assert "KB" in rendered

    custom_template = tmp_path / "custom-template.md"
    custom_template.write_text("Project {{ project_key }}", encoding="utf-8")
    cfg_custom = cfg.model_copy(update={"project_management_template": str(custom_template)})
    monkeypatch.setattr(agents, "_load_configuration_for_instructions", lambda _root: cfg_custom)
    rendered_custom = agents.build_project_management_text(tmp_path)
    assert rendered_custom == "Project KB"

    bad_template = tmp_path / "bad.md"
    bad_template.write_text("{% for x in %}", encoding="utf-8")
    cfg_bad = cfg.model_copy(update={"project_management_template": str(bad_template)})
    monkeypatch.setattr(agents, "_load_configuration_for_instructions", lambda _root: cfg_bad)
    with pytest.raises(click.ClickException):
        agents.build_project_management_text(tmp_path)


def test_load_configuration_for_instructions_wraps_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agents,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing")),
    )
    with pytest.raises(click.ClickException, match="missing"):
        agents._load_configuration_for_instructions(tmp_path)

    monkeypatch.setattr(agents, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        agents,
        "load_project_configuration",
        lambda _path: (_ for _ in ()).throw(ConfigurationError("bad")),
    )
    with pytest.raises(click.ClickException, match="bad"):
        agents._load_configuration_for_instructions(tmp_path)


def test_resolve_project_management_template_path_paths(
    tmp_path: Path,
) -> None:
    cfg = _config()

    assert agents._resolve_project_management_template_path(tmp_path, cfg) is None

    conventional = tmp_path / agents.DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME
    conventional.write_text("x", encoding="utf-8")
    assert agents._resolve_project_management_template_path(tmp_path, cfg) == conventional

    custom = tmp_path / "custom.md"
    custom.write_text("x", encoding="utf-8")
    cfg_custom = cfg.model_copy(update={"project_management_template": "custom.md"})
    assert agents._resolve_project_management_template_path(tmp_path, cfg_custom) == custom

    cfg_missing = cfg.model_copy(update={"project_management_template": "missing.md"})
    with pytest.raises(click.ClickException, match="template not found"):
        agents._resolve_project_management_template_path(tmp_path, cfg_missing)


def test_context_and_example_builders() -> None:
    cfg = _config()

    workflow_context = agents._build_workflow_context(cfg)
    assert workflow_context
    assert workflow_context[0]["name"] == "default"

    priorities = agents._build_priority_context(cfg.priorities)
    assert priorities[0]["value"] == 0

    examples = agents._build_command_examples(cfg)
    assert any("kanbus create" in line for line in examples)
    assert any("kanbus close" in line for line in examples)

    semantic = agents._build_semantic_release_mapping(["bug", "story", "chore", "other"])
    assert semantic[0]["category"] == "fix"
    assert semantic[1]["category"] == "feat"

    statuses = agents._collect_statuses(cfg.workflows["default"])
    assert "open" in statuses
    assert agents._select_status_example("open", cfg.workflows["default"]) in statuses

    no_transition_workflow = {"x": []}
    assert agents._select_status_example("x", no_transition_workflow) == "x"

    ctx = agents._build_project_management_context(cfg)
    assert ctx["project_key"] == "KB"
    assert ctx["default_priority_name"] == "medium"


def test_header_section_utilities_and_replace_insert_paths() -> None:
    lines = ["# Header", "", "## A", "a", "## B", "b", "### C", "c"]
    end = agents._find_section_end(lines, 3, 2)
    assert end == 4

    matches = [agents.SectionMatch(start=2, end=4, level=2), agents.SectionMatch(start=4, end=8, level=2)]
    assert agents._is_in_sections(2, matches) is True
    assert agents._is_in_sections(1, matches) is False

    replaced = agents._replace_sections(lines, matches, matches[0], ["## X", "new"])
    assert "## X" in replaced

    replaced_no_insert = agents._replace_sections(lines, [], agents.SectionMatch(0, 0, 1), ["## X"])
    assert replaced_no_insert.endswith("## X\n")

    inserted = agents._insert_kanbus_section(["plain"], ["## K"])
    assert inserted.startswith("## K")


def test_confirm_overwrite_tty_and_abort_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANBUS_NON_INTERACTIVE", raising=False)
    monkeypatch.delenv("KANBUS_FORCE_INTERACTIVE", raising=False)

    class _NoTty:
        def isatty(self):
            return False

    monkeypatch.setattr(agents.click, "get_text_stream", lambda _name: _NoTty())
    with pytest.raises(click.ClickException, match="Re-run with --force"):
        agents._confirm_overwrite()

    class _Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(agents.click, "get_text_stream", lambda _name: _Tty())
    monkeypatch.setattr(
        agents.click,
        "confirm",
        lambda _prompt, default: (_ for _ in ()).throw(click.Abort()),
    )
    with pytest.raises(click.ClickException, match="Re-run with --force"):
        agents._confirm_overwrite()
