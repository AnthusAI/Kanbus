from __future__ import annotations

import pytest

from kanbus import rich_text_signals


@pytest.mark.parametrize(
    "text",
    [
        "# Heading",
        "**bold**",
        "*italic*",
        "_em_",
        "```\ncode\n```",
        "`inline`",
        "> quote",
        "- list",
        "1. ordered",
        "---",
        "[link](https://example.com)",
    ],
)
def test_has_markdown_formatting_patterns(text: str) -> None:
    assert rich_text_signals.has_markdown_formatting(text) is True


def test_has_markdown_formatting_false_for_plain_text() -> None:
    assert rich_text_signals.has_markdown_formatting("plain text") is False


@pytest.mark.parametrize("language", ["mermaid", "plantuml", "d2", "Mermaid"])
def test_has_diagram_block_detects_supported_languages(language: str) -> None:
    text = f"```{language}\nA -> B\n```"
    assert rich_text_signals.has_diagram_block(text) is True


def test_has_diagram_block_false_without_supported_fence() -> None:
    assert rich_text_signals.has_diagram_block("```python\nprint(1)\n```") is False


def test_repair_escape_sequences_repairs_literal_newline_sequences() -> None:
    repaired, changed = rich_text_signals.repair_escape_sequences("one\\ntwo")
    assert changed is True
    assert repaired == "one\ntwo"


def test_repair_escape_sequences_returns_original_when_no_change() -> None:
    repaired, changed = rich_text_signals.repair_escape_sequences("one\ntwo")
    assert changed is False
    assert repaired == "one\ntwo"


def test_apply_text_quality_signals_repairs_and_emits_suggestions() -> None:
    result = rich_text_signals.apply_text_quality_signals("line1\\nline2")
    assert result.escape_sequences_repaired is True
    assert result.text == "line1\nline2"
    assert len(result.warnings) == 1
    assert "Literal \\n escape sequences" in result.warnings[0]
    assert len(result.suggestions) == 2


def test_apply_text_quality_signals_skips_suggestions_when_markdown_and_diagram_present() -> (
    None
):
    text = "# H\n```mermaid\nA-->B\n```"
    result = rich_text_signals.apply_text_quality_signals(text)
    assert result.escape_sequences_repaired is False
    assert result.warnings == []
    assert result.suggestions == []


def test_emit_signals_prints_warnings_suggestions_and_comment_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = rich_text_signals.TextQualityResult(
        text="t",
        warnings=["w1"],
        suggestions=["s1", "s2"],
    )

    lines: list[str] = []
    monkeypatch.setattr(
        rich_text_signals.click, "echo", lambda msg, err=True: lines.append(msg)
    )

    rich_text_signals.emit_signals(
        result,
        context="description",
        issue_id="kanbus-1",
        comment_id="c1",
        is_update=True,
    )

    assert lines[0] == "w1"
    assert "s1" in lines[1]
    assert "s2" in lines[2]
    assert "kbs comment update kanbus-1 c1" in lines[3]


def test_emit_signals_without_suggestions_has_no_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = rich_text_signals.TextQualityResult(
        text="t", warnings=["w"], suggestions=[]
    )
    lines: list[str] = []
    monkeypatch.setattr(
        rich_text_signals.click, "echo", lambda msg, err=True: lines.append(msg)
    )

    rich_text_signals.emit_signals(result, context="description", issue_id="kanbus-1")

    assert lines == ["w"]


def test_emit_follow_up_hint_uses_description_update_when_no_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines: list[str] = []
    monkeypatch.setattr(
        rich_text_signals.click, "echo", lambda msg, err=True: lines.append(msg)
    )

    rich_text_signals._emit_follow_up_hint(
        context="description",
        issue_id="kanbus-2",
        comment_id=None,
        is_update=False,
    )

    assert lines == [
        '  -> To update the description: kbs update kanbus-2 --description "<your improved description here>"'
    ]
