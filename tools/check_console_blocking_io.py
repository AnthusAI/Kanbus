#!/usr/bin/env python3
"""
Forbid blocking I/O inside async code of the Rust console server.

The console server (``rust/src/bin/console_local.rs``) and its shared backend
(``rust/src/console_backend.rs``) run on a tokio runtime. A synchronous file,
process, sleep, or kanbus-library call made directly from an async function or
async block stalls a runtime worker thread. Such work must run inside
``tokio::task::spawn_blocking`` (or use ``tokio::fs`` / ``tokio::process``).

This tool masks comments and string literals, locates every ``async fn`` body
and ``async`` block outside ``#[cfg(test)]`` modules, removes the ranges that
are ``spawn_blocking(...)`` arguments or nested non-async ``fn`` items, and
reports any remaining blocking call.

A line may opt out with a ``blocking-io-allow: <reason>`` comment on the same
or the preceding line.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

DEFAULT_TARGET_FILES: Tuple[str, ...] = (
    "rust/src/bin/console_local.rs",
    "rust/src/console_backend.rs",
)

ALLOW_MARKER = "blocking-io-allow:"

BLOCKING_WRAPPER_NAMES = ("spawn_blocking", "run_blocking", "wiki_response")

STARTUP_FUNCTION_NAMES = ("main",)

KANBUS_BLOCKING_FUNCTIONS = (
    "load_issue_events",
    "read_shared_router_events",
    "issue_awaiting_agent_reply",
    "load_state",
    "save_state",
    "validate_tenant_state_path",
    "add_comment",
    "update_issue",
    "change_issue_assignment",
    "generate_standup_report",
    "detect_repairable_project_issues",
    "repair_project_structure",
    "get_current_user",
    "run_gossip_bridge",
    "load_console_issues",
    "load_issues_from_dir",
    "load_issues_with_virtual_projects",
    "list_pages",
    "render_page",
    "resolve_repo_root",
    "locate_existing_tenant_root",
)

BLOCKING_CALL_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (description, re.compile(pattern))
    for description, pattern in (
        ("std::fs call", r"\bfs::\w+\s*\("),
        ("File open or create", r"\bFile::(?:open|create|options)\s*\("),
        ("OpenOptions", r"\bOpenOptions::new\s*\("),
        (
            "synchronous filesystem metadata",
            r"\.(?:canonicalize|is_dir|is_file|exists|try_exists|metadata"
            r"|symlink_metadata|read_dir)\s*\(\s*\)",
        ),
        ("read_to_string", r"\bread_to_string\s*\("),
        ("std::process::Command", r"\bCommand::new\s*\("),
        ("process wait", r"\.(?:wait|wait_with_output)\s*\(\s*\)"),
        ("thread::sleep", r"\bthread::sleep\s*\("),
        ("blocking reqwest", r"\breqwest::blocking\b"),
        ("std mutex lock", r"\.lock\s*\(\s*\)(?!\s*\.await)"),
        (
            "synchronous kanbus library call",
            r"\b(?:" + "|".join(KANBUS_BLOCKING_FUNCTIONS) + r")\s*\(",
        ),
        (
            "synchronous store method",
            r"\.\s*(?:build_snapshot\w*|load_config|load_issues\w*)\s*\(",
        ),
    )
)


class Violation(NamedTuple):
    """
    One blocking call found in async code.

    :param path: Source file containing the call.
    :type path: str
    :param line: One-based line number.
    :type line: int
    :param description: Human-readable category of the blocking call.
    :type description: str
    :param text: Source line text, stripped.
    :type text: str
    """

    path: str
    line: int
    description: str
    text: str


def mask_comments_and_strings(source: str) -> str:
    """
    Replace comments, string literals, and char literals with spaces.

    Newlines and total length are preserved so offsets map to the original.

    :param source: Rust source text.
    :type source: str
    :return: Masked text of identical length.
    :rtype: str
    """
    output = list(source)
    length = len(source)
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, min(end, length)):
            if output[position] != "\n":
                output[position] = " "

    while index < length:
        character = source[index]
        raw_match = re.match(r'b?r(#*)"', source[index : index + 16])
        if source.startswith("//", index):
            end = source.find("\n", index)
            end = length if end == -1 else end
            blank(index, end)
            index = end
        elif source.startswith("/*", index):
            depth = 1
            end = index + 2
            while end < length and depth:
                if source.startswith("/*", end):
                    depth += 1
                    end += 2
                elif source.startswith("*/", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            blank(index, end)
            index = end
        elif raw_match and (index == 0 or not source[index - 1].isalnum()):
            terminator = '"' + raw_match.group(1)
            end = source.find(terminator, index + raw_match.end())
            end = length if end == -1 else end + len(terminator)
            blank(index, end)
            index = end
        elif character == '"':
            end = index + 1
            while end < length and source[end] != '"':
                end += 2 if source[end] == "\\" else 1
            blank(index, end + 1)
            index = end + 1
        elif character == "'":
            char_match = re.match(r"'(?:\\[^']*|[^\\'])'", source[index : index + 16])
            if char_match:
                blank(index, index + char_match.end())
                index += char_match.end()
            else:
                index += 1
        else:
            index += 1
    return "".join(output)


def find_matching_delimiter(
    masked: str, open_index: int, opener: str, closer: str
) -> int:
    """
    Return the index of the delimiter closing the one at ``open_index``.

    :param masked: Masked source text.
    :type masked: str
    :param open_index: Index of the opening delimiter.
    :type open_index: int
    :param opener: Opening delimiter character.
    :type opener: str
    :param closer: Closing delimiter character.
    :type closer: str
    :return: Index of the matching closing delimiter.
    :rtype: int
    :raises ValueError: If delimiters are unbalanced.
    """
    depth = 0
    for position in range(open_index, len(masked)):
        if masked[position] == opener:
            depth += 1
        elif masked[position] == closer:
            depth -= 1
            if depth == 0:
                return position
    raise ValueError(f"unbalanced {opener}{closer} starting at offset {open_index}")


def find_test_module_start(masked: str) -> int:
    """
    Return the offset where the ``#[cfg(test)]`` module begins.

    :param masked: Masked source text.
    :type masked: str
    :return: Offset of the test module, or the text length when absent.
    :rtype: int
    """
    match = re.search(r"#\[cfg\(test\)\]\s*mod\s+\w+\s*\{", masked)
    return match.start() if match else len(masked)


def find_body_open_brace(masked: str, start: int) -> Optional[int]:
    """
    Find the ``{`` that opens a function body starting the scan at ``start``.

    :param masked: Masked source text.
    :type masked: str
    :param start: Offset to begin scanning.
    :type start: int
    :return: Offset of the opening brace, or None for declarations without a body.
    :rtype: Optional[int]
    """
    depth = 0
    for position in range(start, len(masked)):
        character = masked[position]
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and character == ";":
            return None
        elif depth == 0 and character == "{":
            return position
    return None


def collect_async_ranges(masked: str, limit: int) -> List[Tuple[int, int]]:
    """
    Collect body ranges of async functions and async blocks before ``limit``.

    :param masked: Masked source text.
    :type masked: str
    :param limit: Offset after which code is ignored (test module).
    :type limit: int
    :return: Half-open ``(start, end)`` ranges of async bodies.
    :rtype: List[Tuple[int, int]]
    """
    ranges: List[Tuple[int, int]] = []
    for match in re.finditer(r"\basync\s+fn\s+(\w+)", masked):
        if match.start() >= limit:
            break
        if match.group(1) in STARTUP_FUNCTION_NAMES:
            continue
        open_index = find_body_open_brace(masked, match.end())
        if open_index is not None:
            end = find_matching_delimiter(masked, open_index, "{", "}") + 1
            ranges.append((open_index, end))
    for match in re.finditer(r"\basync\s+(?:move\s+)?\{", masked):
        if match.start() >= limit:
            break
        open_index = match.end() - 1
        end = find_matching_delimiter(masked, open_index, "{", "}") + 1
        ranges.append((open_index, end))
    return ranges


def collect_exempt_ranges(masked: str, limit: int) -> List[Tuple[int, int]]:
    """
    Collect ranges where blocking calls are allowed inside async bodies.

    These are ``spawn_blocking(...)`` argument lists and nested non-async
    ``fn`` item bodies.

    :param masked: Masked source text.
    :type masked: str
    :param limit: Offset after which code is ignored (test module).
    :type limit: int
    :return: Half-open exempt ranges.
    :rtype: List[Tuple[int, int]]
    """
    ranges: List[Tuple[int, int]] = []
    wrapper_pattern = r"\b(?:" + "|".join(BLOCKING_WRAPPER_NAMES) + r")\s*\("
    for match in re.finditer(wrapper_pattern, masked):
        if match.start() >= limit:
            break
        open_index = match.end() - 1
        end = find_matching_delimiter(masked, open_index, "(", ")") + 1
        ranges.append((open_index, end))
    return ranges


def collect_synchronous_functions(
    masked: str, limit: int
) -> List[Tuple[str, int, int]]:
    """
    Collect synchronous function bodies before ``limit``.

    :param masked: Masked source text.
    :type masked: str
    :param limit: Offset after which code is ignored (test module).
    :type limit: int
    :return: ``(name, body_start, body_end)`` for each synchronous function.
    :rtype: List[Tuple[str, int, int]]
    """
    functions: List[Tuple[str, int, int]] = []
    for match in re.finditer(r"(?<!async )\bfn\s+(\w+)", masked):
        if match.start() >= limit:
            break
        open_index = find_body_open_brace(masked, match.end())
        if open_index is not None:
            end = find_matching_delimiter(masked, open_index, "{", "}") + 1
            functions.append((match.group(1), open_index, end))
    return functions


def find_blocking_functions(
    masked: str,
    limit: int,
    functions: Sequence[Tuple[str, int, int]],
    exempt_ranges: Sequence[Tuple[int, int]],
) -> set:
    """
    Find synchronous functions that block, directly or through callees.

    :param masked: Masked source text.
    :type masked: str
    :param limit: Offset after which code is ignored (test module).
    :type limit: int
    :param functions: Synchronous function bodies.
    :type functions: Sequence[Tuple[str, int, int]]
    :param exempt_ranges: Ranges where blocking is allowed.
    :type exempt_ranges: Sequence[Tuple[int, int]]
    :return: Names of blocking synchronous functions.
    :rtype: set
    """
    direct_offsets = [
        match.start()
        for _, pattern in BLOCKING_CALL_PATTERNS
        for match in pattern.finditer(masked, 0, limit)
        if not is_covered(match.start(), exempt_ranges)
    ]
    blocking = {
        name
        for name, start, end in functions
        if any(start <= offset < end for offset in direct_offsets)
    }
    changed = True
    while changed:
        changed = False
        for name, start, end in functions:
            if name in blocking:
                continue
            body = masked[start:end]
            for callee in blocking:
                for match in re.finditer(r"\b" + callee + r"\s*\(", body):
                    if not is_covered(start + match.start(), exempt_ranges):
                        blocking.add(name)
                        changed = True
                        break
                if name in blocking:
                    break
    return blocking


def is_covered(offset: int, ranges: Sequence[Tuple[int, int]]) -> bool:
    """
    Return whether ``offset`` lies inside any range.

    :param offset: Source offset.
    :type offset: int
    :param ranges: Half-open ranges.
    :type ranges: Sequence[Tuple[int, int]]
    :return: True when covered.
    :rtype: bool
    """
    return any(start <= offset < end for start, end in ranges)


def check_source(path: str, source: str) -> List[Violation]:
    """
    Find blocking calls in async code of one Rust source text.

    :param path: Display path for reporting.
    :type path: str
    :param source: Rust source text.
    :type source: str
    :return: Violations in source order.
    :rtype: List[Violation]
    """
    masked = mask_comments_and_strings(source)
    limit = find_test_module_start(masked)
    async_ranges = collect_async_ranges(masked, limit)
    exempt_ranges = collect_exempt_ranges(masked, limit)
    functions = collect_synchronous_functions(masked, limit)
    blocking_functions = find_blocking_functions(
        masked, limit, functions, exempt_ranges
    )
    original_lines = source.splitlines()
    violations: List[Violation] = []
    seen = set()
    call_patterns = list(BLOCKING_CALL_PATTERNS)
    if blocking_functions:
        call_patterns.append(
            (
                "call to blocking helper function",
                re.compile(
                    r"(?<!fn )\b(?:" + "|".join(sorted(blocking_functions)) + r")\s*\("
                ),
            )
        )
    for description, pattern in call_patterns:
        for match in pattern.finditer(masked, 0, limit):
            offset = match.start()
            if not is_covered(offset, async_ranges):
                continue
            if is_covered(offset, exempt_ranges):
                continue
            line = masked.count("\n", 0, offset) + 1
            if (line, description) in seen:
                continue
            nearby = original_lines[max(line - 2, 0) : line]
            if any(ALLOW_MARKER in text for text in nearby):
                continue
            seen.add((line, description))
            violations.append(
                Violation(path, line, description, original_lines[line - 1].strip())
            )
    return sorted(violations, key=lambda item: (item.line, item.description))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Run the check over the console server sources.

    :param argv: Optional argument list; defaults to ``sys.argv[1:]``.
    :type argv: Optional[Sequence[str]]
    :return: Process exit code, 0 when clean and 1 when violations exist.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Rust files to check (default: the console server sources).",
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Repository root used to resolve default paths.",
    )
    arguments = parser.parse_args(argv)
    root = Path(arguments.root)
    targets = arguments.paths or [str(root / name) for name in DEFAULT_TARGET_FILES]
    violations: List[Violation] = []
    for target in targets:
        text = Path(target).read_text(encoding="utf-8")
        violations.extend(check_source(target, text))
    for violation in violations:
        print(
            f"{violation.path}:{violation.line}: {violation.description} "
            f"in async code outside spawn_blocking: {violation.text}"
        )
    if violations:
        print(
            f"{len(violations)} blocking call(s) found; wrap in "
            "tokio::task::spawn_blocking or use tokio::fs / tokio::process.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
