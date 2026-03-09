"""File edit operations mirroring the Anthropic text editor tool.

Provides view, str_replace, create, and insert commands with strict single-match
replacement semantics for agent compatibility.
"""

from __future__ import annotations

from pathlib import Path


class TextEditorError(RuntimeError):
    """Raised when a text editor operation fails."""


def edit_view(root: Path, path: Path, view_range: tuple[int, int] | None = None) -> str:
    """View file contents or directory listing.

    :param root: Repository root (current working directory for relative paths).
    :type root: Path
    :param path: File or directory path (relative to root).
    :type path: Path
    :param view_range: Optional (start, end) line numbers (1-indexed; -1 for end).
    :type view_range: tuple[int, int] | None
    :return: File contents with optional line numbers, or directory listing.
    :rtype: str
    :raises TextEditorError: If path does not exist or is outside root.
    """
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TextEditorError("path escapes repository root")
    if not resolved.exists():
        raise TextEditorError("file or directory not found")
    if resolved.is_dir():
        entries = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        return "\n".join(p.name + ("/" if p.is_dir() else "") for p in entries)
    content = resolved.read_text(encoding="utf-8")
    lines = content.splitlines()
    if view_range is not None:
        start_one, end_one = view_range
        start_idx = max(0, start_one - 1) if start_one >= 1 else 0
        end_idx = len(lines) if end_one == -1 else min(len(lines), end_one)
        lines = lines[start_idx:end_idx]
        line_start = start_idx + 1
    else:
        line_start = 1
    return "\n".join(f"{line_start + i}: {line}" for i, line in enumerate(lines))


def edit_str_replace(root: Path, path: Path, old_str: str, new_str: str) -> str:
    """Replace exactly one occurrence of old_str with new_str.

    :param root: Repository root.
    :type root: Path
    :param path: File path (relative to root).
    :type path: Path
    :param old_str: Exact text to replace.
    :type old_str: str
    :param new_str: Replacement text.
    :type new_str: str
    :return: Success message.
    :rtype: str
    :raises TextEditorError: If file not found, 0 matches, or multiple matches.
    """
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TextEditorError("path escapes repository root")
    if not resolved.exists() or not resolved.is_file():
        raise TextEditorError("file not found")
    content = resolved.read_text(encoding="utf-8")
    count = content.count(old_str)
    if count == 0:
        raise TextEditorError("no match found for replacement")
    if count > 1:
        raise TextEditorError(f"found {count} matches for replacement text; provide more context for a unique match")
    new_content = content.replace(old_str, new_str, 1)
    resolved.write_text(new_content, encoding="utf-8")
    return "Successfully replaced text at exactly one location."


def edit_create(root: Path, path: Path, file_text: str) -> str:
    """Create a new file with the given content.

    :param root: Repository root.
    :type root: Path
    :param path: File path (relative to root).
    :type path: Path
    :param file_text: Content to write.
    :type file_text: str
    :return: Success message.
    :rtype: str
    :raises TextEditorError: If file already exists or path escapes root.
    """
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TextEditorError("path escapes repository root")
    if resolved.exists():
        raise TextEditorError("file already exists")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(file_text, encoding="utf-8")
    return "Successfully created file."


def edit_insert(root: Path, path: Path, insert_line: int, insert_text: str) -> str:
    """Insert text after the given line number.

    insert_line 0 means insert at the beginning. Line numbers are 1-indexed.

    :param root: Repository root.
    :type root: Path
    :param path: File path (relative to root).
    :type path: Path
    :param insert_line: Line number after which to insert (0 = beginning).
    :type insert_line: int
    :param insert_text: Text to insert.
    :type insert_text: str
    :return: Success message.
    :rtype: str
    :raises TextEditorError: If file not found or insert_line is invalid.
    """
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TextEditorError("path escapes repository root")
    if not resolved.exists() or not resolved.is_file():
        raise TextEditorError("file not found")
    lines = resolved.read_text(encoding="utf-8").splitlines()
    if insert_line < 0:
        raise TextEditorError("insert_line must be non-negative")
    if insert_line > len(lines):
        raise TextEditorError("insert_line exceeds file length")
    idx = insert_line
    new_lines = lines[:idx] + insert_text.splitlines() + lines[idx:]
    resolved.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    return "Successfully inserted text."
