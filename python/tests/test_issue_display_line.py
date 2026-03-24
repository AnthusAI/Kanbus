from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from kanbus import issue_display, issue_line, wiki
from kanbus.models import (
    CategoryDefinition,
    DependencyLink,
    IssueComment,
    StatusDefinition,
)

from test_helpers import build_issue, build_project_configuration


def _comment(
    text: str, author: str = "dev", comment_id: str | None = None
) -> IssueComment:
    return IssueComment.model_validate(
        {
            "id": comment_id,
            "author": author,
            "text": text,
            "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
        }
    )


def test_issue_display_color_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        issue_display.click,
        "get_current_context",
        lambda silent=True: SimpleNamespace(color=True),
    )
    assert issue_display._should_use_color() is True

    monkeypatch.setattr(
        issue_display.click, "get_current_context", lambda silent=True: None
    )
    monkeypatch.setattr(issue_display.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert issue_display._should_use_color() is True

    monkeypatch.setenv("NO_COLOR", "1")
    assert issue_display._should_use_color() is False

    monkeypatch.setattr(
        issue_display.click, "style", lambda text, fg=None: f"[{fg}]{text}"
    )
    assert issue_display._dim("ID:", use_color=False) == "ID:"
    assert issue_display._dim("ID:", use_color=True) == "[bright_black]ID:"
    assert issue_display._normalize_color("red") == "red"
    assert issue_display._normalize_color("not-a-color") is None
    assert issue_display._paint("x", "red", use_color=False) == "x"
    assert issue_display._paint("x", "bad", use_color=True) == "x"
    assert issue_display._paint("x", "red", use_color=True) == "[red]x"


def test_render_description_and_comments_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1", title="T", status="open")
    issue.description = "{{ desc }}"
    issue.comments = [_comment("{{ c1 }}"), _comment("{{ c2 }}")]
    monkeypatch.setattr(
        wiki, "render_template_string", lambda value, _issues: f"R:{value}"
    )

    description, comments = issue_display._render_description_and_comments(
        issue, [issue]
    )

    assert description == "R:{{ desc }}"
    assert comments == ["R:{{ c1 }}", "R:{{ c2 }}"]


def test_render_description_and_comments_wiki_error_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1", title="T", status="open")
    issue.description = "raw description"
    issue.comments = [_comment("raw comment")]

    def fail(_value: str, _issues: list[object]) -> str:
        raise wiki.WikiError("boom")

    monkeypatch.setattr(wiki, "render_template_string", fail)

    description, comments = issue_display._render_description_and_comments(
        issue, [issue]
    )
    assert description == "raw description"
    assert comments == ["raw comment"]


def test_render_description_and_comments_empty_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1")
    issue.description = ""
    issue.comments = [_comment("comment text")]
    monkeypatch.setattr(
        wiki, "render_template_string", lambda value, _issues: f"R:{value}"
    )
    description, comments = issue_display._render_description_and_comments(
        issue, [issue]
    )
    assert description == ""
    assert comments == ["R:comment text"]


def test_format_issue_for_display_sections_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = build_project_configuration()
    configuration.type_colors["task"] = "green"
    configuration.categories = [
        CategoryDefinition.model_validate({"name": "To do", "color": "magenta"})
    ]
    configuration.statuses = [
        StatusDefinition.model_validate(
            {"key": "open", "name": "Open", "category": "To do"}
        )
    ]
    configuration.priorities[2].color = "bright_blue"

    issue = build_issue("kanbus-1", title="My Title", status="open", issue_type="task")
    issue.description = "desc"
    issue.dependencies = [
        DependencyLink.model_validate({"target": "kanbus-2", "type": "blocked-by"})
    ]
    issue.comments = [
        _comment("first", comment_id="abcdef123456"),
        SimpleNamespace(id=None, author="", text="second"),
    ]

    monkeypatch.setattr(
        issue_display, "format_issue_key", lambda identifier, _ctx: f"FMT:{identifier}"
    )
    monkeypatch.setattr(
        issue_display,
        "_render_description_and_comments",
        lambda _issue, _all: ("rendered desc", ["rc1", "rc2"]),
    )

    rendered = issue_display.format_issue_for_display(
        issue,
        configuration=configuration,
        use_color=False,
        project_context=True,
        all_issues=[issue],
    )

    assert "ID: FMT:kanbus-1" in rendered
    assert "Title: My Title" in rendered
    assert "Description:" in rendered
    assert "rendered desc" in rendered
    assert "Dependencies:" in rendered
    assert "blocked-by: kanbus-2" in rendered
    assert "Comments:" in rendered
    assert "[abcdef] dev: rc1" in rendered
    assert "unknown: rc2" in rendered


def test_format_issue_for_display_with_colorized_muted_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-9", parent=None, labels=[])
    issue.assignee = None
    monkeypatch.setattr(
        issue_display, "format_issue_key", lambda identifier, _ctx: identifier
    )
    monkeypatch.setattr(
        issue_display.click, "style", lambda text, fg=None: f"[{fg}]{text}"
    )

    rendered = issue_display.format_issue_for_display(issue, use_color=True)
    assert "[bright_black]-" in rendered


def test_format_issue_for_display_uses_explicit_status_color() -> None:
    configuration = build_project_configuration()
    configuration.categories = [
        CategoryDefinition.model_validate({"name": "To do", "color": "blue"})
    ]
    configuration.statuses = [
        StatusDefinition.model_validate(
            {"key": "open", "name": "Open", "category": "To do", "color": "red"}
        )
    ]
    issue = build_issue("kanbus-1", status="open")
    rendered = issue_display.format_issue_for_display(
        issue, configuration=configuration, use_color=False
    )
    assert "Status: open" in rendered


def test_issue_line_color_resolution_helpers() -> None:
    configuration = build_project_configuration()
    configuration.categories = [
        CategoryDefinition.model_validate({"name": "To do", "color": "red"})
    ]
    configuration.statuses = [
        StatusDefinition.model_validate(
            {"key": "open", "name": "Open", "category": "To do"}
        )
    ]
    configuration.statuses[0].color = "red"

    assert issue_line._normalize_cli_color("gray") == "bright_black"
    assert issue_line._normalize_cli_color("grey") == "bright_black"
    assert issue_line._normalize_cli_color("not-a-color") is None

    assert issue_line._resolve_status_color("open", configuration) == "red"
    assert issue_line._resolve_status_color("missing", configuration) == "white"
    configuration.statuses[0].color = None
    configuration.categories[0].color = "cyan"
    assert issue_line._resolve_status_color("open", configuration) == "cyan"

    configuration.priorities[2].color = "magenta"
    assert issue_line._resolve_priority_color(2, configuration) == "magenta"
    assert issue_line._resolve_priority_color(4, None) == "white"

    configuration.type_colors["task"] = "green"
    assert issue_line._resolve_type_color("task", configuration) == "green"
    assert issue_line._resolve_type_color("unknown", None) == "white"


def test_issue_line_safe_color_and_widths(monkeypatch: pytest.MonkeyPatch) -> None:
    assert issue_line._safe_color(lambda t, fg=None: f"[{fg}]{t}", "x", None) == "x"
    assert (
        issue_line._safe_color(lambda t, fg=None: f"[{fg}]{t}", "x", "red") == "[red]x"
    )

    one = build_issue("kanbus-1", issue_type="task", status="open")
    two = build_issue(
        "kanbus-22", issue_type="bug", status="in_progress", parent="kanbus-1"
    )
    widths = issue_line.compute_widths([one, two])
    assert widths["identifier"] >= len("kanbus-22")
    assert widths["status"] >= len("in_progress")

    monkeypatch.setattr(
        issue_line,
        "format_issue_key",
        lambda identifier, project_context=False: (
            identifier.replace("kanbus-", "k-") if project_context else identifier
        ),
    )
    formatted = issue_line.format_issue_line(one, porcelain=True, project_context=True)
    assert " | " in formatted
    assert "k-1" in formatted


def test_issue_line_format_non_porcelain_with_color_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1", issue_type="task", status="open", parent=None)
    issue.custom["project_path"] = "alpha/project"
    configuration = build_project_configuration()
    configuration.type_colors["task"] = "green"
    configuration.priorities[2].color = "blue"
    configuration.categories = [
        CategoryDefinition.model_validate({"name": "To do", "color": "cyan"})
    ]
    configuration.statuses = [
        StatusDefinition.model_validate(
            {"key": "open", "name": "Open", "category": "To do"}
        )
    ]
    configuration.statuses[0].color = "cyan"

    monkeypatch.setattr(issue_line.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        issue_line,
        "format_issue_key",
        lambda identifier, project_context=False: identifier,
    )

    line = issue_line.format_issue_line(
        issue,
        porcelain=False,
        colorizer=lambda text, fg=None: f"[{fg}]{text}",
        widths={"type": 1, "identifier": 8, "parent": 1, "status": 4, "priority": 2},
        configuration=configuration,
        use_color=None,
    )

    assert line.startswith("alpha/project ")
    assert "[green]T" in line
    assert "[cyan]open" in line
    assert "[blue]P2" in line


def test_issue_line_no_color_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    issue = build_issue("kanbus-1", issue_type="task", status="open")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(issue_line.sys.stdout, "isatty", lambda: True)

    line = issue_line.format_issue_line(issue, porcelain=False, use_color=None)
    assert "[" not in line
