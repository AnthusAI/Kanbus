#!/usr/bin/env python3
"""Report Python-vs-Rust coverage deltas for shared module names."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any
import xml.etree.ElementTree as element_tree


@dataclass(frozen=True)
class ModuleCoverage:
    """Coverage data for a single module stem."""

    stem: str
    line_coverage: float
    lines_covered: int
    lines_total: int


@dataclass(frozen=True)
class ModuleDelta:
    """Coverage delta between Rust and Python for a shared stem."""

    stem: str
    rust_line_coverage: float
    python_line_coverage: float
    delta_points: float
    rust_lines_total: int
    python_lines_total: int


def parse_line_rate(xml_path: Path) -> float:
    """Parse root line-rate from Cobertura XML as percentage points."""
    root = element_tree.parse(xml_path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise ValueError(f"Missing line-rate in coverage XML: {xml_path}")
    return float(line_rate) * 100.0


def parse_python_modules(xml_path: Path) -> dict[str, ModuleCoverage]:
    """Parse Python module coverage keyed by file stem."""
    root = element_tree.parse(xml_path).getroot()
    modules: dict[str, ModuleCoverage] = {}
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        if not filename.startswith("kanbus/") or not filename.endswith(".py"):
            continue
        stem = Path(filename).stem
        lines = class_node.findall("./lines/line")
        lines_total = len(lines)
        lines_covered = sum(
            1 for line in lines if int(line.attrib.get("hits", "0")) > 0
        )
        line_coverage = (lines_covered / lines_total * 100.0) if lines_total else 0.0
        modules[stem] = ModuleCoverage(
            stem=stem,
            line_coverage=round(line_coverage, 4),
            lines_covered=lines_covered,
            lines_total=lines_total,
        )
    return modules


def parse_rust_modules(xml_path: Path) -> dict[str, ModuleCoverage]:
    """Parse Rust module coverage keyed by file stem."""
    root = element_tree.parse(xml_path).getroot()
    modules: dict[str, ModuleCoverage] = {}
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        if not filename.startswith("src/") or not filename.endswith(".rs"):
            continue
        stem = Path(filename).stem
        lines = class_node.findall("./lines/line")
        lines_total = len(lines)
        lines_covered = sum(
            1 for line in lines if int(line.attrib.get("hits", "0")) > 0
        )
        line_coverage = (lines_covered / lines_total * 100.0) if lines_total else 0.0
        modules[stem] = ModuleCoverage(
            stem=stem,
            line_coverage=round(line_coverage, 4),
            lines_covered=lines_covered,
            lines_total=lines_total,
        )
    return modules


def compute_shared_deltas(
    python_modules: dict[str, ModuleCoverage],
    rust_modules: dict[str, ModuleCoverage],
) -> list[ModuleDelta]:
    """Compute shared-stem Rust-minus-Python coverage deltas."""
    shared = sorted(set(python_modules) & set(rust_modules))
    deltas: list[ModuleDelta] = []
    for stem in shared:
        python_entry = python_modules[stem]
        rust_entry = rust_modules[stem]
        delta = rust_entry.line_coverage - python_entry.line_coverage
        deltas.append(
            ModuleDelta(
                stem=stem,
                rust_line_coverage=rust_entry.line_coverage,
                python_line_coverage=python_entry.line_coverage,
                delta_points=round(delta, 4),
                rust_lines_total=rust_entry.lines_total,
                python_lines_total=python_entry.lines_total,
            )
        )
    deltas.sort(key=lambda item: (item.delta_points, item.stem))
    return deltas


def build_payload(
    python_xml: Path,
    rust_xml: Path,
    limit: int,
) -> dict[str, Any]:
    """Build JSON report payload."""
    python_modules = parse_python_modules(python_xml)
    rust_modules = parse_rust_modules(rust_xml)
    shared_deltas = compute_shared_deltas(python_modules, rust_modules)
    return {
        "python_line_coverage": round(parse_line_rate(python_xml), 4),
        "rust_line_coverage": round(parse_line_rate(rust_xml), 4),
        "gap_points": round(parse_line_rate(python_xml) - parse_line_rate(rust_xml), 4),
        "shared_module_count": len(shared_deltas),
        "largest_rust_deficits": [asdict(item) for item in shared_deltas[:limit]],
        "largest_rust_leads": [asdict(item) for item in shared_deltas[-limit:]],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate Python/Rust coverage parity report."
    )
    parser.add_argument(
        "--python-xml",
        default="coverage-python/coverage.xml",
        help="Path to Python coverage XML.",
    )
    parser.add_argument(
        "--rust-xml",
        default="coverage-rust/cobertura.xml",
        help="Path to Rust coverage XML.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of largest deficits/leads to print.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit report as JSON.",
    )
    return parser.parse_args(argv)


def render_text(payload: dict[str, Any]) -> str:
    """Render human-readable parity report."""
    lines = [
        "Coverage parity report",
        f"python_line_coverage={payload['python_line_coverage']:.2f}",
        f"rust_line_coverage={payload['rust_line_coverage']:.2f}",
        f"gap_points={payload['gap_points']:.2f}",
        f"shared_module_count={payload['shared_module_count']}",
        "largest_rust_deficits:",
    ]
    for item in payload["largest_rust_deficits"]:
        lines.append(
            "  "
            f"{item['stem']}: rust={item['rust_line_coverage']:.2f}% "
            f"python={item['python_line_coverage']:.2f}% "
            f"delta={item['delta_points']:.2f} pts"
        )
    lines.append("largest_rust_leads:")
    for item in payload["largest_rust_leads"]:
        lines.append(
            "  "
            f"{item['stem']}: rust={item['rust_line_coverage']:.2f}% "
            f"python={item['python_line_coverage']:.2f}% "
            f"delta={item['delta_points']:.2f} pts"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run coverage parity reporting."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    payload = build_payload(
        python_xml=Path(args.python_xml),
        rust_xml=Path(args.rust_xml),
        limit=max(args.limit, 1),
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
