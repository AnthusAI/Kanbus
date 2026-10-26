#!/usr/bin/env python3
"""
Verify parity between shared Gherkin steps and both implementations.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")
STEP_DECORATORS = frozenset({"given", "when", "then", "step"})

RUST_STEP_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*\"(?P<text>(?:\\.|[^\"\\])*)\"\s*\)\]",
    re.DOTALL,
)
RUST_STEP_RAW_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*r#\"(?P<text>.*?)\"#\s*\)\]",
    re.DOTALL,
)
RUST_EXPR_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*expr\s*=\s*\"(?P<text>(?:\\.|[^\"\\])*)\"\s*\)\]",
    re.DOTALL,
)
RUST_EXPR_RAW_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*expr\s*=\s*r#\"(?P<text>.*?)\"#\s*\)\]",
    re.DOTALL,
)
RUST_REGEX_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*regex\s*=\s*\"(?P<text>(?:\\.|[^\"\\])*)\"\s*\)\]",
    re.DOTALL,
)
RUST_REGEX_RAW_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*regex\s*=\s*r#\"(?P<text>.*?)\"#\s*\)\]",
    re.DOTALL,
)


@dataclass(frozen=True)
class StepPattern:
    text: str
    is_regex: bool
    is_cucumber_expression: bool = False
    is_literal: bool = False


@dataclass(frozen=True)
class ParityResults:
    feature_steps: Set[str]
    python_steps: Set[str]
    rust_steps: Set[str]
    python_patterns: Sequence[StepPattern]
    rust_patterns: Sequence[StepPattern]
    python_executed_steps: Optional[Set[str]] = None
    rust_executed_steps: Optional[Set[str]] = None

    def missing_in_python(self) -> Set[str]:
        steps = (
            self.feature_steps
            if self.python_executed_steps is None
            else self.python_executed_steps
        )
        return _find_missing(steps, self.python_patterns)

    def missing_in_rust(self) -> Set[str]:
        steps = (
            self.feature_steps
            if self.rust_executed_steps is None
            else self.rust_executed_steps
        )
        return _find_missing(steps, self.rust_patterns)

    def python_only(self) -> Set[str]:
        return self.python_steps - self.rust_steps

    def rust_only(self) -> Set[str]:
        return self.rust_steps - self.python_steps


PYTHON_EXCLUDED_TAGS = frozenset({"wip", "skip", "slow"})
RUST_EXCLUDED_TAGS = frozenset({"wip", "skip", "slow", "python-parity", "cloud"})


def _extract_tag_names(tag_line: str) -> Set[str]:
    tags = set()
    for tag in tag_line.strip().split():
        if tag.startswith("@"):
            tags.add(tag[1:])
    return tags


def _split_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _expand_outline_step(
    step_text: str, example_header: List[str], example_rows: List[List[str]]
) -> List[str]:
    if not example_rows or "<" not in step_text:
        return [step_text]
    expanded = []
    for row in example_rows:
        text = step_text
        for column, value in zip(example_header, row):
            text = text.replace(f"<{column}>", value)
        expanded.append(text)
    return expanded


@dataclass
class _ScenarioSteps:
    tags: Set[str]
    step_templates: List[str]
    example_header: List[str]
    example_rows: List[List[str]]

    def expanded_steps(self) -> List[str]:
        steps: List[str] = []
        for template in self.step_templates:
            steps.extend(
                _expand_outline_step(template, self.example_header, self.example_rows)
            )
        return steps


def _iter_scenarios(feature_path: Path) -> Iterable[Tuple[Set[str], List[str]]]:
    feature_tags: Set[str] = set()
    pending_tags: Set[str] = set()
    background_steps: List[str] = []
    scenarios: List[_ScenarioSteps] = []
    current: Optional[_ScenarioSteps] = None
    in_background = False
    in_examples = False
    in_docstring = False

    for raw_line in feature_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('"""'):
            in_docstring = not in_docstring
            continue
        if in_docstring or line.startswith("#"):
            continue
        if line.startswith("@"):
            pending_tags |= _extract_tag_names(line)
            continue
        if line.startswith("Feature:"):
            feature_tags = pending_tags
            pending_tags = set()
            continue
        if line.startswith("Background"):
            in_background = True
            in_examples = False
            current = None
            pending_tags = set()
            continue
        if line.startswith("Scenario"):
            in_background = False
            in_examples = False
            current = _ScenarioSteps(
                tags=feature_tags | pending_tags,
                step_templates=[],
                example_header=[],
                example_rows=[],
            )
            pending_tags = set()
            scenarios.append(current)
            continue
        if line.startswith("Examples"):
            in_examples = True
            pending_tags = set()
            continue
        if in_examples and current is not None and line.startswith("|"):
            cells = _split_table_row(line)
            if not current.example_header:
                current.example_header = cells
            else:
                current.example_rows.append(cells)
            continue
        if line.split(maxsplit=1)[0] in STEP_KEYWORDS:
            step_text = line.split(maxsplit=1)[1].strip()
            if in_background:
                background_steps.append(step_text)
            elif current is not None:
                current.step_templates.append(step_text)

    for scenario in scenarios:
        yield scenario.tags, background_steps + scenario.expanded_steps()


def _iter_feature_steps(feature_path: Path) -> Iterable[str]:
    for tags, steps in _iter_scenarios(feature_path):
        if "wip" in tags:
            continue
        yield from steps


def collect_feature_steps(features_root: Path) -> Set[str]:
    """Collect scenario step text from feature files.

    :param features_root: Root directory containing feature files.
    :type features_root: Path
    :return: Set of step strings.
    :rtype: Set[str]
    """
    steps: Set[str] = set()
    for path in features_root.rglob("*.feature"):
        steps.update(_iter_feature_steps(path))
    return steps


def collect_runtime_feature_steps(
    features_root: Path, excluded_tags: frozenset
) -> Set[str]:
    """Collect step text for the scenarios a runtime actually executes.

    :param features_root: Root directory containing feature files.
    :type features_root: Path
    :param excluded_tags: Tags that keep a scenario out of the runtime.
    :type excluded_tags: frozenset
    :return: Set of step strings.
    :rtype: Set[str]
    """
    steps: Set[str] = set()
    for path in features_root.rglob("*.feature"):
        for tags, scenario_steps in _iter_scenarios(path):
            if tags & excluded_tags:
                continue
            steps.update(scenario_steps)
    return steps


def _python_step_literals(source: str) -> Iterable[str]:
    module = ast.parse(source)
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            function = decorator.func
            if not (isinstance(function, ast.Name) and function.id in STEP_DECORATORS):
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                if isinstance(decorator.args[0].value, str):
                    yield decorator.args[0].value


def collect_python_steps(steps_root: Path) -> List[StepPattern]:
    """Collect step patterns from Python step definition files.

    :param steps_root: Root directory containing Python step files.
    :type steps_root: Path
    :return: List of step patterns.
    :rtype: List[StepPattern]
    """
    steps: List[StepPattern] = []
    for path in steps_root.rglob("*.py"):
        for text in _python_step_literals(path.read_text(encoding="utf-8")):
            steps.append(StepPattern(text=text, is_regex=_looks_like_regex(text)))
    return steps


def collect_rust_steps(steps_root: Path) -> List[StepPattern]:
    """Collect step patterns from Rust step definition files.

    :param steps_root: Root directory containing Rust step files.
    :type steps_root: Path
    :return: List of step patterns.
    :rtype: List[StepPattern]
    """
    steps: List[StepPattern] = []
    for path in steps_root.rglob("*.rs"):
        contents = path.read_text(encoding="utf-8")
        for match in RUST_STEP_RAW_PATTERN.finditer(contents):
            text = match.group("text")
            text = _decode_escaped_literal(text)
            steps.append(_rust_literal_pattern(text))
        for match in RUST_STEP_PATTERN.finditer(contents):
            text = match.group("text")
            text = _decode_escaped_literal(text)
            steps.append(_rust_literal_pattern(text))
        for match in RUST_EXPR_RAW_PATTERN.finditer(contents):
            text = match.group("text")
            text = _decode_escaped_literal(text)
            steps.append(_rust_pattern(text))
        for match in RUST_EXPR_PATTERN.finditer(contents):
            text = match.group("text")
            text = _decode_escaped_literal(text)
            steps.append(_rust_pattern(text))
        for match in RUST_REGEX_RAW_PATTERN.finditer(contents):
            text = match.group("text")
            text = _decode_escaped_literal(text)
            steps.append(StepPattern(text=text, is_regex=True))
        for match in RUST_REGEX_PATTERN.finditer(contents):
            text = match.group("text")
            text = _decode_escaped_literal(text)
            steps.append(StepPattern(text=text, is_regex=True))
    return steps


def _rust_literal_pattern(text: str) -> StepPattern:
    """Build a pattern for a plain ``#[given("...")]`` attribute.

    cucumber-rs matches a plain string literal exactly (``^escaped$``), without
    cucumber-expression semantics such as ``/`` alternation.
    """
    if _looks_like_regex(text):
        return _rust_pattern(text)
    return StepPattern(text=text, is_regex=False, is_literal=True)


def _rust_pattern(text: str) -> StepPattern:
    is_regex = _looks_like_regex(text)
    return StepPattern(
        text=text, is_regex=is_regex, is_cucumber_expression=not is_regex
    )


def _looks_like_regex(text: str) -> bool:
    return (
        text.startswith("^")
        or text.endswith("$")
        or "(?P<" in text
        or re.search(r"\(\[\^|\\d|\\s|\(\.[+*]|\.\+\)", text) is not None
    )


def _decode_escaped_literal(text: str) -> str:
    """Decode escaped quotes/newlines while preserving regex backslashes."""
    return (
        text.replace("\\\\", "\\")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )


def normalize_step_text(text: str) -> str:
    """Normalize step text to avoid syntax-only parity mismatches."""
    normalized = text.strip()
    normalized = re.sub(r"\{[^}]+\}", "{param}", normalized)
    normalized = re.sub(r'"{param}"', "{param}", normalized)
    normalized = re.sub(r"'\{param\}'", "{param}", normalized)
    normalized = normalized.replace("{string}", "{param}")
    normalized = normalized.replace("{word}", "{param}")
    normalized = normalized.replace("{int}", "{param}")
    normalized = normalized.replace("{float}", "{param}")
    normalized = normalized.replace("{param:string}", "{param}")
    normalized = normalized.replace("{param:word}", "{param}")
    normalized = normalized.replace("{param:int}", "{param}")
    normalized = normalized.replace("{param:float}", "{param}")
    normalized = normalized.rstrip("$")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


CUCUMBER_PARAMETER_PATTERNS = {
    "string": r"(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",
    "int": r"-?\d+",
    "float": r"-?\d*\.?\d+",
    "word": r"[^\s]+",
    "": r".*",
}


def _cucumber_token_to_regex(token: str) -> str:
    pieces: List[str] = []
    alternatives = _split_unescaped(token, "/")
    for alternative in alternatives:
        pieces.append(_cucumber_fragment_to_regex(alternative))
    if len(pieces) == 1:
        return pieces[0]
    return "(?:" + "|".join(pieces) + ")"


def _split_unescaped(text: str, separator: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    index = 0
    brace_depth = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            current.append(text[index : index + 2])
            index += 2
            continue
        if character == "{":
            brace_depth += 1
        elif character == "}":
            brace_depth -= 1
        if character == separator and brace_depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
        index += 1
    parts.append("".join(current))
    return parts


def _cucumber_fragment_to_regex(fragment: str) -> str:
    regex: List[str] = []
    index = 0
    while index < len(fragment):
        character = fragment[index]
        if character == "\\" and index + 1 < len(fragment):
            regex.append(re.escape(fragment[index + 1]))
            index += 2
            continue
        if character == "{":
            closing = fragment.find("}", index)
            if closing != -1:
                name = fragment[index + 1 : closing]
                regex.append(CUCUMBER_PARAMETER_PATTERNS.get(name, r".+"))
                index = closing + 1
                continue
        if character == "(":
            closing = fragment.find(")", index)
            if closing != -1:
                regex.append("(?:" + re.escape(fragment[index + 1 : closing]) + ")?")
                index = closing + 1
                continue
        regex.append(re.escape(character))
        index += 1
    return "".join(regex)


def _cucumber_expression_to_regex(expression: str) -> re.Pattern[str]:
    tokens = re.split(r"(\s+)", expression)
    regex = "".join(
        token if token.isspace() and token else _cucumber_token_to_regex(token)
        for token in tokens
    )
    return re.compile(regex)


def _behave_parse_expression_to_regex(expression: str) -> re.Pattern[str]:
    pieces = re.split(r"(\{[^}]*\})", expression)
    regex = "".join(
        r".+?" if piece.startswith("{") and piece.endswith("}") else re.escape(piece)
        for piece in pieces
    )
    return re.compile(regex)


def _compile_pattern(pattern: StepPattern) -> re.Pattern[str]:
    if pattern.is_literal:
        return re.compile(re.escape(pattern.text))
    if pattern.is_regex:
        try:
            return re.compile(pattern.text)
        except re.error:
            return re.compile(re.escape(_normalize_step_text(pattern.text)))
    if pattern.is_cucumber_expression:
        return _cucumber_expression_to_regex(pattern.text)
    return _behave_parse_expression_to_regex(pattern.text)


def _normalize_step_text(text: str) -> str:
    return normalize_step_text(text)


def _find_missing(feature_steps: Set[str], patterns: Sequence[StepPattern]) -> Set[str]:
    compiled = [_compile_pattern(pattern) for pattern in patterns]
    missing: Set[str] = set()
    for step in feature_steps:
        if not any(regex.fullmatch(step) for regex in compiled):
            missing.add(step)
    return missing


def _pattern_matched_steps(
    pattern: StepPattern,
    feature_steps: Set[str],
) -> frozenset:
    """Return the set of feature steps that this pattern matches."""
    try:
        regex = _compile_pattern(pattern)
    except re.error:
        return frozenset()
    matched: Set[str] = set()
    for step in feature_steps:
        if regex.fullmatch(step):
            matched.add(step)
    return frozenset(matched)


def _python_only_with_equivalence(
    python_patterns: Sequence[StepPattern],
    rust_patterns: Sequence[StepPattern],
    feature_steps: Set[str],
) -> Set[str]:
    """Python patterns that have no Rust pattern matching the same feature steps."""
    rust_matched: List[frozenset] = [
        _pattern_matched_steps(p, feature_steps) for p in rust_patterns
    ]
    result: Set[str] = set()
    for py_pattern in python_patterns:
        py_matched = _pattern_matched_steps(py_pattern, feature_steps)
        if py_matched and any(py_matched == rm for rm in rust_matched):
            continue
        result.add(_normalize_step_text(py_pattern.text))
    return result


def _rust_only_with_equivalence(
    python_patterns: Sequence[StepPattern],
    rust_patterns: Sequence[StepPattern],
    feature_steps: Set[str],
) -> Set[str]:
    """Rust patterns that have no Python pattern matching the same feature steps."""
    py_matched: List[frozenset] = [
        _pattern_matched_steps(p, feature_steps) for p in python_patterns
    ]
    result: Set[str] = set()
    for rust_pattern in rust_patterns:
        rm = _pattern_matched_steps(rust_pattern, feature_steps)
        if rm and any(rm == pm for pm in py_matched):
            continue
        result.add(_normalize_step_text(rust_pattern.text))
    return result


def build_results(repo_root: Path) -> ParityResults:
    """Build parity results for the repository.

    :param repo_root: Repository root path.
    :type repo_root: Path
    :return: Parity results.
    :rtype: ParityResults
    """
    feature_steps = collect_feature_steps(repo_root / "features")
    python_patterns = collect_python_steps(repo_root / "python" / "features" / "steps")
    rust_patterns = collect_rust_steps(repo_root / "rust" / "features" / "steps")
    python_steps = {_normalize_step_text(pattern.text) for pattern in python_patterns}
    rust_steps = {_normalize_step_text(pattern.text) for pattern in rust_patterns}
    return ParityResults(
        feature_steps=feature_steps,
        python_steps=python_steps,
        rust_steps=rust_steps,
        python_patterns=python_patterns,
        rust_patterns=rust_patterns,
        python_executed_steps=collect_runtime_feature_steps(
            repo_root / "features", PYTHON_EXCLUDED_TAGS
        ),
        rust_executed_steps=collect_runtime_feature_steps(
            repo_root / "features", RUST_EXCLUDED_TAGS
        ),
    )


def _format_step_list(title: str, steps: Sequence[str]) -> List[str]:
    if not steps:
        return []
    lines = [f"{title}:"]
    for step in steps:
        lines.append(f"  - {step}")
    return lines


def load_known_unimplemented_steps(path: Optional[Path]) -> Set[str]:
    """Load the ratchet of steps known to lack an implementation.

    Each line is ``<runtime>|<step text>``; blank lines and ``#`` lines are ignored.

    :param path: File to read, or None for an empty ratchet.
    :type path: Optional[Path]
    :return: Set of ``<runtime>|<step text>`` entries.
    :rtype: Set[str]
    """
    if path is None or not path.exists():
        return set()
    entries: Set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            entries.add(line)
    return entries


def current_unimplemented_steps(results: ParityResults) -> Set[str]:
    entries = {f"python|{step}" for step in results.missing_in_python()}
    entries |= {f"rust|{step}" for step in results.missing_in_rust()}
    return entries


def report(
    results: ParityResults, known_unimplemented: Optional[Set[str]] = None
) -> Tuple[bool, List[str]]:
    """Report parity results.

    :param results: Parity results to summarize.
    :type results: ParityResults
    :param known_unimplemented: Ratchet of ``<runtime>|<step>`` gaps tolerated for now.
    :type known_unimplemented: Optional[Set[str]]
    :return: Tuple of ok flag and output lines.
    :rtype: Tuple[bool, List[str]]
    """
    known = known_unimplemented or set()
    current = current_unimplemented_steps(results)
    new_gaps = sorted(current - known)
    fixed_gaps = sorted(known - current)
    missing_in_python = sorted(results.missing_in_python())
    missing_in_rust = sorted(results.missing_in_rust())
    python_only = sorted(
        _python_only_with_equivalence(
            results.python_patterns,
            results.rust_patterns,
            results.feature_steps,
        )
    )
    rust_only = sorted(
        _rust_only_with_equivalence(
            results.python_patterns,
            results.rust_patterns,
            results.feature_steps,
        )
    )

    lines: List[str] = []
    lines.append(f"Feature steps: {len(results.feature_steps)}")
    lines.append(f"Python steps: {len(results.python_steps)}")
    lines.append(f"Rust steps: {len(results.rust_steps)}")

    lines.extend(_format_step_list("New steps missing an implementation", new_gaps))
    lines.extend(
        _format_step_list(
            "Fixed steps still listed as known gaps (remove them from the list)",
            fixed_gaps,
        )
    )
    lines.append(f"Known unimplemented steps tolerated: {len(current & known)}")
    lines.extend(_format_step_list("Python-only steps", python_only))
    lines.extend(_format_step_list("Rust-only steps", rust_only))

    strict = os.getenv("KANBUS_PARITY_STRICT", "1") != "0"
    ok = not (new_gaps or fixed_gaps)
    if not strict:
        ok = True
    return ok, lines


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    :param argv: Raw argument list.
    :type argv: Sequence[str]
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description="Check spec parity across implementations."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to the repository root.",
    )
    parser.add_argument(
        "--known",
        type=Path,
        default=None,
        help="Ratchet file of known unimplemented steps.",
    )
    parser.add_argument(
        "--update-known",
        action="store_true",
        help="Rewrite the ratchet file with the current gaps.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    """Run the spec parity check.

    :param argv: Raw argument list.
    :type argv: Sequence[str]
    :return: Exit code.
    :rtype: int
    """
    args = parse_args(argv)
    results = build_results(args.repo)
    known_path = (
        args.known or args.repo / "tools" / "parity" / "known_unimplemented_steps.txt"
    )
    if args.update_known:
        entries = sorted(current_unimplemented_steps(results))
        known_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {known_path}")
        return 0
    ok, lines = report(results, load_known_unimplemented_steps(known_path))
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
