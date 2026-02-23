"""Rich text quality signals for CLI output.

Detects and repairs common malformations in issue descriptions and comments
submitted through the CLI, and emits actionable warnings and suggestions.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field


_MARKDOWN_PATTERNS = [
    re.compile(r"^#{1,6}\s", re.MULTILINE),
    re.compile(r"\*\*[^*]+\*\*"),
    re.compile(r"\*[^*]+\*"),
    re.compile(r"__[^_]+__"),
    re.compile(r"_[^_]+_"),
    re.compile(r"^```", re.MULTILINE),
    re.compile(r"`[^`]+`"),
    re.compile(r"^>", re.MULTILINE),
    re.compile(r"^\s*[-*+]\s", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s", re.MULTILINE),
    re.compile(r"^---$", re.MULTILINE),
    re.compile(r"\[.+\]\(.+\)"),
]

_DIAGRAM_FENCE_PATTERN = re.compile(
    r"^```\s*(mermaid|plantuml|d2)\s*$", re.MULTILINE | re.IGNORECASE
)

_LITERAL_NEWLINE_PATTERN = re.compile(r"\\n")

_SUPPORTED_DIAGRAM_LANGUAGES = ("mermaid", "plantuml", "d2")


@dataclass
class TextQualityResult:
    """Result of applying quality signals to a text value.

    :param text: The (possibly repaired) text after processing.
    :type text: str
    :param warnings: Warning messages describing automatic transformations.
    :type warnings: list[str]
    :param suggestions: Non-blocking suggestion messages.
    :type suggestions: list[str]
    :param escape_sequences_repaired: True if literal \\n sequences were replaced.
    :type escape_sequences_repaired: bool
    """

    text: str
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    escape_sequences_repaired: bool = False


def repair_escape_sequences(text: str) -> tuple[str, bool]:
    """Replace literal backslash-n sequences with real newline characters.

    :param text: Input text that may contain literal ``\\n`` sequences.
    :type text: str
    :return: Tuple of (repaired text, whether any replacements were made).
    :rtype: tuple[str, bool]
    """
    if _LITERAL_NEWLINE_PATTERN.search(text):
        return _LITERAL_NEWLINE_PATTERN.sub("\n", text), True
    return text, False


def has_markdown_formatting(text: str) -> bool:
    """Return True if the text contains at least one Markdown element.

    :param text: Text to inspect.
    :type text: str
    :return: True if any Markdown formatting is detected.
    :rtype: bool
    """
    return any(pattern.search(text) for pattern in _MARKDOWN_PATTERNS)


def has_diagram_block(text: str) -> bool:
    """Return True if the text contains at least one diagram fenced code block.

    :param text: Text to inspect.
    :type text: str
    :return: True if a mermaid, plantuml, or d2 block is found.
    :rtype: bool
    """
    return bool(_DIAGRAM_FENCE_PATTERN.search(text))


def apply_text_quality_signals(text: str) -> TextQualityResult:
    """Apply all quality signals to the given text.

    Repairs literal escape sequences, then checks for missing Markdown
    formatting and missing diagram blocks, collecting warnings and suggestions.

    :param text: Raw text from the CLI argument.
    :type text: str
    :return: Quality result with repaired text, warnings, and suggestions.
    :rtype: TextQualityResult
    """
    repaired_text, sequences_were_repaired = repair_escape_sequences(text)

    warnings: list[str] = []
    suggestions: list[str] = []

    if sequences_were_repaired:
        warnings.append(
            "WARNING: Literal \\n escape sequences were detected and replaced with real "
            "newlines.\n"
            "  To pass multi-line text correctly, use a heredoc or $'...\\n...' syntax:\n"
            "    kbs create \"Title\" --description $'First line\\nSecond line'\n"
            '    kbs create "Title" --description "$(cat <<\'EOF\'\\nFirst line\\n'
            'Second line\\nEOF\\n)"'
        )

    if not has_markdown_formatting(repaired_text):
        suggestions.append(
            "SUGGESTION: Markdown formatting is supported in descriptions and comments.\n"
            "  Use headings, bold, code blocks, and lists when they improve readability."
        )

    if not has_diagram_block(repaired_text):
        suggestions.append(
            "SUGGESTION: Diagrams can be embedded using fenced code blocks.\n"
            "  Supported: mermaid, plantuml, d2. Use these to visualize flows or structures."
        )

    return TextQualityResult(
        text=repaired_text,
        warnings=warnings,
        suggestions=suggestions,
        escape_sequences_repaired=sequences_were_repaired,
    )


def emit_signals(
    result: TextQualityResult,
    context: str,
    issue_id: str | None = None,
    comment_id: str | None = None,
    is_update: bool = False,
) -> None:
    """Print quality signal messages to stderr.

    Emits warnings first, then suggestions, and finally a follow-up command
    hint if any suggestions were generated.

    :param result: The quality result to emit signals from.
    :type result: TextQualityResult
    :param context: Human-readable label for what was processed (e.g. "description").
    :type context: str
    :param issue_id: Issue identifier for follow-up command hints.
    :type issue_id: str | None
    :param comment_id: Comment identifier for comment-update hints.
    :type comment_id: str | None
    :param is_update: Whether this is an update operation (affects hint wording).
    :type is_update: bool
    """
    for warning in result.warnings:
        print(warning, file=sys.stderr)

    if result.suggestions:
        for suggestion in result.suggestions:
            print(suggestion, file=sys.stderr)

        if issue_id:
            _emit_follow_up_hint(
                context=context,
                issue_id=issue_id,
                comment_id=comment_id,
                is_update=is_update,
            )


def _emit_follow_up_hint(
    context: str,
    issue_id: str,
    comment_id: str | None,
    is_update: bool,
) -> None:
    """Emit a single ready-to-run follow-up command hint to stderr.

    :param context: Human-readable label for what was processed.
    :type context: str
    :param issue_id: Issue identifier.
    :type issue_id: str
    :param comment_id: Comment identifier, if applicable.
    :type comment_id: str | None
    :param is_update: Whether this is an update operation.
    :type is_update: bool
    """
    if comment_id:
        hint = (
            f"  -> To update this comment: "
            f'kbs comment update {issue_id} {comment_id} "<your improved comment here>"'
        )
    else:
        hint = (
            f"  -> To update the {context}: "
            f'kbs update {issue_id} --description "<your improved description here>"'
        )
    print(hint, file=sys.stderr)
