#!/usr/bin/env python3
"""
Verify parity between shared Gherkin steps and both implementations.
"""

from __future__ import annotations

import argparse
import codecs
import re
import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple

STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")

PYTHON_STEP_PATTERN = re.compile(
    r"@(?P<kind>given|when|then)\(\s*[\"'](?P<text>.+?)[\"']\s*\)",
)
RUST_STEP_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*\"(?P<text>.+?)\"\s*\)\]",
    re.DOTALL,
)
RUST_EXPR_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*expr\s*=\s*\"(?P<text>.+?)\"\s*\)\]",
    re.DOTALL,
)
RUST_REGEX_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\s*regex\s*=\s*r#\"(?P<text>.+?)\"#\s*\)\]",
    re.DOTALL,
)


@dataclass(frozen=True)
class StepPattern:
    text: str
    is_regex: bool


@dataclass(frozen=True)
class ParityResults:
    feature_steps: Set[str]
    python_steps: Set[str]
    rust_steps: Set[str]
    python_patterns: Sequence[StepPattern]
    rust_patterns: Sequence[StepPattern]

    def missing_in_python(self) -> Set[str]:
        return _find_missing(self.feature_steps, self.python_patterns)

    def missing_in_rust(self) -> Set[str]:
        return _find_missing(self.feature_steps, self.rust_patterns)

    def python_only(self) -> Set[str]:
        return self.python_steps - self.rust_steps

    def rust_only(self) -> Set[str]:
        return self.rust_steps - self.python_steps


def _extract_tag_names(tag_line: str) -> Set[str]:
    tags = set()
    for tag in tag_line.strip().split():
        if tag.startswith("@"):
            tags.add(tag[1:])
    return tags


def _iter_feature_steps(feature_path: Path) -> Iterable[str]:
    current_feature_tags: Set[str] = set()
    current_scenario_tags: Set[str] = set()
    in_scenario = False
    skip_scenario = False

    for raw_line in feature_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("@"):
            tags = _extract_tag_names(line)
            if in_scenario:
                current_scenario_tags |= tags
            else:
                current_feature_tags |= tags
            continue
        if line.startswith("Feature:"):
            in_scenario = False
            current_scenario_tags = set()
            skip_scenario = False
            continue
        if line.startswith("Scenario"):
            in_scenario = True
            skip_scenario = (
                "wip" in current_feature_tags
                or "wip" in current_scenario_tags
                or "console" in current_feature_tags
                or "console" in current_scenario_tags
            )
            current_scenario_tags = set()
            continue
        if in_scenario and line.split(maxsplit=1)[0] in STEP_KEYWORDS:
            if skip_scenario:
                continue
            step_text = line.split(maxsplit=1)[1].strip()
            yield step_text


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


def collect_python_steps(steps_root: Path) -> List[StepPattern]:
    """Collect step patterns from Python step definition files.

    :param steps_root: Root directory containing Python step files.
    :type steps_root: Path
    :return: List of step patterns.
    :rtype: List[StepPattern]
    """
    steps: List[StepPattern] = []
    for path in steps_root.rglob("*.py"):
        for match in PYTHON_STEP_PATTERN.finditer(path.read_text(encoding="utf-8")):
            text = match.group("text")
            text = codecs.decode(text, "unicode_escape")
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
        for match in RUST_STEP_PATTERN.finditer(contents):
            text = match.group("text")
            text = codecs.decode(text, "unicode_escape")
            steps.append(StepPattern(text=text, is_regex=_looks_like_regex(text)))
        for match in RUST_EXPR_PATTERN.finditer(contents):
            text = match.group("text")
            text = codecs.decode(text, "unicode_escape")
            steps.append(StepPattern(text=text, is_regex=_looks_like_regex(text)))
        for match in RUST_REGEX_PATTERN.finditer(contents):
            text = match.group("text")
            text = codecs.decode(text, "unicode_escape")
            steps.append(StepPattern(text=text, is_regex=True))
    return steps


def _looks_like_regex(text: str) -> bool:
    return text.startswith("^") or text.endswith("$") or "(?P<" in text


def _compile_pattern(pattern: StepPattern) -> re.Pattern[str]:
    if pattern.is_regex:
        return re.compile(pattern.text)
    if "{" in pattern.text and "}" in pattern.text:
        escaped = re.escape(pattern.text)
        return re.compile(re.sub(r"\\\{[^}]+\\\}", r".+", escaped))
    return re.compile(re.escape(pattern.text))


def _normalize_step_text(text: str) -> str:
    normalized = re.sub(r"\{[^}]+\}", "{param}", text)
    normalized = re.sub(r'["\']\{param\}["\']', "{param}", normalized)
    return normalized


def _find_missing(feature_steps: Set[str], patterns: Sequence[StepPattern]) -> Set[str]:
    compiled = [_compile_pattern(pattern) for pattern in patterns]
    missing: Set[str] = set()
    for step in feature_steps:
        if not any(regex.fullmatch(step) for regex in compiled):
            missing.add(step)
    return missing


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
    )


def _format_step_list(title: str, steps: Sequence[str]) -> List[str]:
    if not steps:
        return []
    lines = [f"{title}:"]
    for step in steps:
        lines.append(f"  - {step}")
    return lines


def report(results: ParityResults) -> Tuple[bool, List[str]]:
    """Report parity results.

    :param results: Parity results to summarize.
    :type results: ParityResults
    :return: Tuple of ok flag and output lines.
    :rtype: Tuple[bool, List[str]]
    """
    missing_in_python = sorted(results.missing_in_python())
    missing_in_rust = sorted(results.missing_in_rust())
    python_only = sorted(results.python_only())
    rust_only = sorted(results.rust_only())

    lines: List[str] = []
    lines.append(f"Feature steps: {len(results.feature_steps)}")
    lines.append(f"Python steps: {len(results.python_steps)}")
    lines.append(f"Rust steps: {len(results.rust_steps)}")

    lines.extend(_format_step_list("Missing in Python", missing_in_python))
    lines.extend(_format_step_list("Missing in Rust", missing_in_rust))
    lines.extend(_format_step_list("Python-only steps", python_only))
    lines.extend(_format_step_list("Rust-only steps", rust_only))

    strict = os.getenv("KANBUS_PARITY_STRICT", "1") != "0"
    ok = not (missing_in_python or missing_in_rust)
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
    parser = argparse.ArgumentParser(description="Check spec parity across implementations.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to the repository root.",
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
    ok, lines = report(results)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
