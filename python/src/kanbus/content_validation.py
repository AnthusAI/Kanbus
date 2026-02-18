"""Content validation for fenced code blocks in Markdown text."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml


class ContentValidationError(RuntimeError):
    """Raised when code block validation fails."""


@dataclass(frozen=True)
class CodeBlock:
    """A fenced code block extracted from Markdown text."""

    language: str
    content: str
    start_line: int


def extract_code_blocks(text: str) -> list[CodeBlock]:
    """Extract all fenced code blocks from Markdown text.

    Scans for lines matching ````` ```language ````` and collects content
    until the closing ````` ``` ````` fence.

    :param text: Markdown text to scan.
    :type text: str
    :return: List of extracted code blocks.
    :rtype: list[CodeBlock]
    """
    blocks: list[CodeBlock] = []
    in_block = False
    current_language = ""
    current_content: list[str] = []
    start_line = 0

    for index, line in enumerate(text.splitlines()):
        trimmed = line.strip()
        if not in_block:
            if trimmed.startswith("```"):
                language = trimmed[3:].strip()
                in_block = True
                current_language = language
                current_content = []
                start_line = index + 1
        elif trimmed == "```":
            blocks.append(
                CodeBlock(
                    language=current_language,
                    content="\n".join(current_content),
                    start_line=start_line,
                )
            )
            in_block = False
        else:
            current_content.append(line)

    return blocks


def validate_code_blocks(text: str) -> None:
    """Validate all code blocks in the given text.

    :param text: Markdown text containing code blocks.
    :type text: str
    :raises ContentValidationError: If any code block has invalid syntax.
    """
    blocks = extract_code_blocks(text)
    for block in blocks:
        if block.language == "json":
            _validate_json(block)
        elif block.language in ("yaml", "yml"):
            _validate_yaml(block)
        elif block.language in ("gherkin", "feature"):
            _validate_gherkin(block)
        elif block.language == "mermaid":
            _validate_external(block, "mmdc")
        elif block.language == "plantuml":
            _validate_external(block, "plantuml")
        elif block.language == "d2":
            _validate_external(block, "d2")


def _validate_json(block: CodeBlock) -> None:
    try:
        json.loads(block.content)
    except json.JSONDecodeError as error:
        raise ContentValidationError(
            f"invalid json in code block at line {block.start_line}: {error}"
        ) from error


def _validate_yaml(block: CodeBlock) -> None:
    try:
        yaml.safe_load(block.content)
    except yaml.YAMLError as error:
        raise ContentValidationError(
            f"invalid yaml in code block at line {block.start_line}: {error}"
        ) from error


def _validate_gherkin(block: CodeBlock) -> None:
    """Validate Gherkin syntax by checking for Feature and Scenario keywords."""
    trimmed = block.content.strip()
    if not trimmed:
        raise ContentValidationError(
            f"invalid gherkin in code block at line {block.start_line}: empty content"
        )
    has_feature = any(
        line.strip().startswith("Feature:") for line in trimmed.splitlines()
    )
    if not has_feature:
        raise ContentValidationError(
            f"invalid gherkin in code block at line {block.start_line}: "
            "expected Feature keyword"
        )
    has_scenario = any(
        line.strip().startswith("Scenario:")
        or line.strip().startswith("Scenario Outline:")
        for line in trimmed.splitlines()
    )
    if not has_scenario:
        raise ContentValidationError(
            f"invalid gherkin in code block at line {block.start_line}: "
            "expected at least one Scenario"
        )


def _validate_external(block: CodeBlock, tool: str) -> None:
    """Validate using an external CLI tool.

    Skips silently if the tool is not installed.
    """
    if shutil.which(tool) is None:
        # Provide helpful installation suggestion
        install_hints = {
            "mmdc": ("mermaid", "npm install -g @mermaid-js/mermaid-cli"),
            "plantuml": (
                "plantuml",
                "brew install plantuml (macOS) or apt install plantuml (Linux)",
            ),
            "d2": ("d2", "curl -fsSL https://d2lang.com/install.sh | sh -s --"),
        }
        if tool in install_hints:
            language, install_cmd = install_hints[tool]
            print(
                f"Note: {language} code block at line {block.start_line} not validated "
                f"({tool} not installed). Install with: {install_cmd}",
                file=sys.stderr,
            )
        return

    extensions = {"mmdc": "mmd", "plantuml": "puml", "d2": "d2"}
    extension = extensions.get(tool, "txt")

    with tempfile.NamedTemporaryFile(
        suffix=f".{extension}", mode="w", delete=False
    ) as tmp:
        tmp.write(block.content)
        temp_path = tmp.name

    try:
        if tool == "mmdc":
            args = ["mmdc", "-i", temp_path, "-o", "/dev/null"]
        elif tool == "plantuml":
            args = ["plantuml", "-checkonly", temp_path]
        elif tool == "d2":
            args = ["d2", "fmt", temp_path]
        else:
            return

        result = subprocess.run(args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            language_names = {"mmdc": "mermaid", "plantuml": "plantuml", "d2": "d2"}
            language = language_names.get(tool, tool)
            stderr = result.stderr.strip()
            raise ContentValidationError(
                f"invalid {language} in code block at line {block.start_line}: "
                f"{stderr}"
            )
    except subprocess.TimeoutExpired:
        pass  # Skip validation on timeout
    finally:
        Path(temp_path).unlink(missing_ok=True)
