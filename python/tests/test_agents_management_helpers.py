from __future__ import annotations

import click

from kanbus import agents_management as agents


def test_parse_header_recognizes_markdown_headers() -> None:
    assert agents._parse_header("## Heading") == (2, "Heading")
    assert agents._parse_header("No heading") is None


def test_find_kanbus_sections_and_replace() -> None:
    lines = [
        "# Agent Instructions",
        "",
        "## Kanbus old section",
        "line a",
        "## Another Kanbus section",
        "line b",
        "## Keep section",
        "line c",
    ]
    matches = agents._find_kanbus_sections(lines)
    assert len(matches) == 2
    replaced = agents._replace_sections(
        lines,
        matches,
        matches[0],
        ["## Project management with Kanbus", "", "Use Kanbus."],
    )
    assert replaced.count("Project management with Kanbus") == 1
    assert "Another Kanbus section" not in replaced
    assert "Keep section" in replaced


def test_insert_kanbus_section_places_after_h1() -> None:
    lines = ["# Agent Instructions", "", "## Existing", "text"]
    inserted = agents._insert_kanbus_section(lines, ["## Project management with Kanbus"])
    assert inserted.startswith("# Agent Instructions")
    assert "## Project management with Kanbus" in inserted


def test_parent_child_rules_cover_empty_and_non_empty_hierarchy() -> None:
    rules = agents._build_parent_child_rules(
        ["initiative", "epic", "task"],
        ["bug", "story"],
    )
    assert any("epic can have parent initiative." in rule for rule in rules)
    assert any("task can have parent epic." in rule for rule in rules)
    assert any("bug, story can have parent initiative, epic." in rule for rule in rules)

    fallback_rules = agents._build_parent_child_rules([], [])
    assert fallback_rules == ["No parent-child relationships are defined."]


def test_find_insert_index_handles_missing_h1() -> None:
    lines = ["## Existing", "text"]
    assert agents._find_insert_index(lines) == 0


def test_join_lines_appends_terminal_newline() -> None:
    assert agents._join_lines(["a", "b"]) == "a\nb\n"


def test_confirm_overwrite_respects_non_interactive(monkeypatch) -> None:
    monkeypatch.setenv("KANBUS_NON_INTERACTIVE", "1")
    try:
        agents._confirm_overwrite()
    except click.ClickException as error:
        assert "Re-run with --force" in str(error)
    else:
        raise AssertionError("expected ClickException")


def test_confirm_overwrite_uses_click_confirm_when_forced_interactive(
    monkeypatch,
) -> None:
    monkeypatch.delenv("KANBUS_NON_INTERACTIVE", raising=False)
    monkeypatch.setenv("KANBUS_FORCE_INTERACTIVE", "1")
    monkeypatch.setattr(agents.click, "confirm", lambda _prompt, default: True)
    assert agents._confirm_overwrite() is True
