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
