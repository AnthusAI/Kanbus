#!/usr/bin/env python3
"""
Verify parity between shared Gherkin steps and both implementations.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple

STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")

PYTHON_STEP_PATTERN = re.compile(
    r"@(?P<kind>given|when|then)\(\s*[\"'](?P<text>.+?)[\"']\s*\)",
)
RUST_STEP_PATTERN = re.compile(
    r"#\[(?P<kind>given|when|then)\(\"(?P<text>.+?)\"\)\]",
)


@dataclass(frozen=True)
class ParityResults:
    feature_steps: Set[str]
    python_steps: Set[str]
    rust_steps: Set[str]

    def missing_in_python(self) -> Set[str]:
        return self.feature_steps - self.python_steps

    def missing_in_rust(self) -> Set[str]:
        return self.feature_steps - self.rust_steps

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
            skip_scenario = "wip" in current_feature_tags or "wip" in current_scenario_tags
            current_scenario_tags = set()
            continue
        if in_scenario and line.split(maxsplit=1)[0] in STEP_KEYWORDS:
            if skip_scenario:
                continue
            step_text = line.split(maxsplit=1)[1].strip()
            yield step_text


def collect_feature_steps(features_root: Path) -> Set[str]:
    steps: Set[str] = set()
    for path in features_root.rglob("*.feature"):
        steps.update(_iter_feature_steps(path))
    return steps


def collect_python_steps(steps_root: Path) -> Set[str]:
    steps: Set[str] = set()
    for path in steps_root.rglob("*.py"):
        for match in PYTHON_STEP_PATTERN.finditer(path.read_text(encoding="utf-8")):
            steps.add(match.group("text"))
    return steps


def collect_rust_steps(steps_root: Path) -> Set[str]:
    steps: Set[str] = set()
    for path in steps_root.rglob("*.rs"):
        for match in RUST_STEP_PATTERN.finditer(path.read_text(encoding="utf-8")):
            text = match.group("text").replace(r"\"", "\"")
            steps.add(text)
    return steps


def build_results(repo_root: Path) -> ParityResults:
    feature_steps = collect_feature_steps(repo_root / "specs" / "features")
    python_steps = collect_python_steps(
        repo_root / "python" / "tests" / "step_definitions"
    )
    rust_steps = collect_rust_steps(repo_root / "rust" / "tests" / "step_definitions")
    return ParityResults(
        feature_steps=feature_steps,
        python_steps=python_steps,
        rust_steps=rust_steps,
    )


def _format_step_list(title: str, steps: Sequence[str]) -> List[str]:
    if not steps:
        return []
    lines = [f"{title}:"]
    for step in steps:
        lines.append(f"  - {step}")
    return lines


def report(results: ParityResults) -> Tuple[bool, List[str]]:
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

    ok = not (missing_in_python or missing_in_rust or python_only or rust_only)
    return ok, lines


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check spec parity across implementations.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Path to the repository root.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    results = build_results(args.repo)
    ok, lines = report(results)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
