from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kanbus import content_validation
from kanbus.content_validation import CodeBlock, ContentValidationError


def test_extract_code_blocks_handles_multiple_and_unclosed_fences() -> None:
    text = (
        "before\n"
        "```json\n"
        '{"a": 1}\n'
        "```\n"
        "middle\n"
        "```yaml\n"
        "a: 1\n"
        "```\n"
        "```python\n"
        "print('x')\n"
    )
    blocks = content_validation.extract_code_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].language == "json"
    assert blocks[0].content == '{"a": 1}'
    assert blocks[0].start_line == 2
    assert blocks[1].language == "yaml"


def test_validate_code_blocks_dispatches_supported_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        content_validation,
        "_validate_json",
        lambda b: calls.append(("json", b.language)),
    )
    monkeypatch.setattr(
        content_validation,
        "_validate_yaml",
        lambda b: calls.append(("yaml", b.language)),
    )
    monkeypatch.setattr(
        content_validation,
        "_validate_gherkin",
        lambda b: calls.append(("gherkin", b.language)),
    )
    monkeypatch.setattr(
        content_validation,
        "_validate_external",
        lambda b, tool: calls.append((tool, b.language)),
    )

    text = "\n".join(
        [
            "```json",
            "{}",
            "```",
            "```yaml",
            "a: 1",
            "```",
            "```yml",
            "a: 2",
            "```",
            "```gherkin",
            "Feature: F",
            "Scenario: S",
            "```",
            "```feature",
            "Feature: F",
            "Scenario: S",
            "```",
            "```mermaid",
            "graph TD; A-->B;",
            "```",
            "```plantuml",
            "@startuml",
            "A->B",
            "@enduml",
            "```",
            "```d2",
            "A -> B",
            "```",
            "```python",
            "print(1)",
            "```",
        ]
    )

    content_validation.validate_code_blocks(text)

    assert ("json", "json") in calls
    assert ("yaml", "yaml") in calls
    assert ("yaml", "yml") in calls
    assert ("gherkin", "gherkin") in calls
    assert ("gherkin", "feature") in calls
    assert ("mmdc", "mermaid") in calls
    assert ("plantuml", "plantuml") in calls
    assert ("d2", "d2") in calls
    assert all(language != "python" for _, language in calls)


def test_validate_json_and_yaml_raise_content_validation_error() -> None:
    with pytest.raises(ContentValidationError, match="invalid json"):
        content_validation._validate_json(CodeBlock("json", "{", 7))

    with pytest.raises(ContentValidationError, match="invalid yaml"):
        content_validation._validate_yaml(CodeBlock("yaml", "a: [", 9))


def test_validate_gherkin_errors_for_empty_missing_feature_and_missing_scenario() -> (
    None
):
    with pytest.raises(ContentValidationError, match="empty content"):
        content_validation._validate_gherkin(CodeBlock("gherkin", "   ", 3))

    with pytest.raises(ContentValidationError, match="expected Feature keyword"):
        content_validation._validate_gherkin(CodeBlock("gherkin", "Scenario: only", 4))

    with pytest.raises(ContentValidationError, match="expected at least one Scenario"):
        content_validation._validate_gherkin(CodeBlock("gherkin", "Feature: X", 5))

    content_validation._validate_gherkin(
        CodeBlock("gherkin", "Feature: X\nScenario Outline: Y", 6)
    )


def test_validate_external_prints_install_hint_when_tool_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(content_validation.shutil, "which", lambda _tool: None)

    content_validation._validate_external(CodeBlock("mermaid", "graph TD", 11), "mmdc")
    stderr = capsys.readouterr().err
    assert "not validated (mmdc not installed)" in stderr


def test_validate_external_runs_tool_and_handles_error_timeout_and_unknown_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        content_validation.shutil, "which", lambda _tool: "/usr/bin/fake"
    )

    seen_args: list[list[str]] = []

    def fake_run(args: list[str], capture_output: bool, text: bool, timeout: int):
        seen_args.append(args)
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(content_validation.subprocess, "run", fake_run)

    content_validation._validate_external(CodeBlock("mermaid", "graph TD", 1), "mmdc")
    assert seen_args[0][0] == "mmdc"

    def fail_run(args: list[str], capture_output: bool, text: bool, timeout: int):
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="bad syntax"
        )

    monkeypatch.setattr(content_validation.subprocess, "run", fail_run)
    with pytest.raises(ContentValidationError, match="invalid plantuml"):
        content_validation._validate_external(
            CodeBlock("plantuml", "@startuml", 2), "plantuml"
        )

    def timeout_run(args: list[str], capture_output: bool, text: bool, timeout: int):
        raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)

    monkeypatch.setattr(content_validation.subprocess, "run", timeout_run)
    content_validation._validate_external(CodeBlock("d2", "A->B", 3), "d2")

    # Unknown tool should return without raising.
    content_validation._validate_external(CodeBlock("x", "body", 4), "unknown")
