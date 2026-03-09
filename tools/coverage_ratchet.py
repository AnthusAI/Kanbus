#!/usr/bin/env python3
"""Enforce cross-language coverage ratchets for Python and Rust."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any
import xml.etree.ElementTree as element_tree


@dataclass(frozen=True)
class CoverageMetrics:
    """Current measured coverage metrics."""

    python_line_coverage: float
    rust_line_coverage: float
    gap_points: float


@dataclass(frozen=True)
class CoverageBaseline:
    """Locked ratchet baseline values."""

    python_line_coverage: float
    rust_line_coverage: float
    max_gap_points: float
    updated_at: str | None = None


def parse_line_rate(xml_path: Path) -> float:
    """Parse Cobertura ``line-rate`` as percentage points.

    :param xml_path: Path to coverage XML.
    :type xml_path: Path
    :return: Line coverage percentage in points.
    :rtype: float
    :raises FileNotFoundError: If XML path does not exist.
    :raises ValueError: If XML is malformed or missing ``line-rate``.
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"coverage xml not found: {xml_path}")
    root = element_tree.parse(xml_path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise ValueError(f"Missing line-rate attribute in coverage XML: {xml_path}")
    try:
        return float(line_rate) * 100.0
    except ValueError as error:
        raise ValueError(
            f"Invalid line-rate value '{line_rate}' in coverage XML: {xml_path}"
        ) from error


def load_baseline(path: Path) -> CoverageBaseline:
    """Load baseline values from JSON.

    :param path: Baseline JSON file path.
    :type path: Path
    :return: Parsed coverage baseline.
    :rtype: CoverageBaseline
    :raises FileNotFoundError: If baseline file does not exist.
    :raises ValueError: If JSON content is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"baseline file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return CoverageBaseline(
            python_line_coverage=float(payload["python_line_coverage"]),
            rust_line_coverage=float(payload["rust_line_coverage"]),
            max_gap_points=float(payload["max_gap_points"]),
            updated_at=payload.get("updated_at"),
        )
    except KeyError as error:
        raise ValueError(f"baseline missing required key: {error}") from error
    except (TypeError, ValueError) as error:
        raise ValueError(f"baseline has invalid value types: {error}") from error


def write_baseline(path: Path, baseline: CoverageBaseline) -> None:
    """Write baseline JSON to disk.

    :param path: Baseline JSON file path.
    :type path: Path
    :param baseline: Baseline values to persist.
    :type baseline: CoverageBaseline
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(baseline)
    path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )


def compute_metrics(python_xml: Path, rust_xml: Path) -> CoverageMetrics:
    """Compute current metrics from Python and Rust coverage XML files.

    :param python_xml: Python coverage XML path.
    :type python_xml: Path
    :param rust_xml: Rust coverage XML path.
    :type rust_xml: Path
    :return: Current coverage metrics.
    :rtype: CoverageMetrics
    """
    python_coverage = round(parse_line_rate(python_xml), 4)
    rust_coverage = round(parse_line_rate(rust_xml), 4)
    gap_points = round(python_coverage - rust_coverage, 4)
    return CoverageMetrics(
        python_line_coverage=python_coverage,
        rust_line_coverage=rust_coverage,
        gap_points=gap_points,
    )


def evaluate_ratchet(
    metrics: CoverageMetrics,
    baseline: CoverageBaseline,
) -> list[str]:
    """Evaluate ratchet failures for current metrics.

    :param metrics: Current coverage metrics.
    :type metrics: CoverageMetrics
    :param baseline: Locked baseline constraints.
    :type baseline: CoverageBaseline
    :return: List of failure messages.
    :rtype: list[str]
    """
    failures: list[str] = []
    tolerance = 0.05

    if metrics.python_line_coverage < baseline.python_line_coverage - tolerance:
        failures.append(
            "python coverage regression: "
            f"{metrics.python_line_coverage:.2f}% < {baseline.python_line_coverage:.2f}%"
        )
    if metrics.rust_line_coverage < baseline.rust_line_coverage - tolerance:
        failures.append(
            "rust coverage regression: "
            f"{metrics.rust_line_coverage:.2f}% < {baseline.rust_line_coverage:.2f}%"
        )
    if metrics.gap_points > baseline.max_gap_points + tolerance:
        failures.append(
            "python/rust coverage gap widened: "
            f"{metrics.gap_points:.2f} pts > {baseline.max_gap_points:.2f} pts"
        )
    return failures


def ratchet_baseline(
    baseline: CoverageBaseline,
    metrics: CoverageMetrics,
) -> CoverageBaseline:
    """Advance the baseline without allowing regressions.

    :param baseline: Existing baseline values.
    :type baseline: CoverageBaseline
    :param metrics: Current measured metrics.
    :type metrics: CoverageMetrics
    :return: Ratcheted baseline.
    :rtype: CoverageBaseline
    """
    timestamp = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    return CoverageBaseline(
        python_line_coverage=round(
            max(baseline.python_line_coverage, metrics.python_line_coverage), 4
        ),
        rust_line_coverage=round(
            max(baseline.rust_line_coverage, metrics.rust_line_coverage), 4
        ),
        max_gap_points=round(min(baseline.max_gap_points, metrics.gap_points), 4),
        updated_at=timestamp,
    )


def format_text_output(
    metrics: CoverageMetrics,
    baseline: CoverageBaseline,
    failures: list[str],
) -> str:
    """Render a human-readable ratchet summary.

    :param metrics: Current coverage metrics.
    :type metrics: CoverageMetrics
    :param baseline: Baseline constraints.
    :type baseline: CoverageBaseline
    :param failures: Ratchet failures.
    :type failures: list[str]
    :return: Multi-line text summary.
    :rtype: str
    """
    lines = [
        "Coverage ratchet summary",
        f"python_line_coverage={metrics.python_line_coverage:.2f}",
        f"rust_line_coverage={metrics.rust_line_coverage:.2f}",
        f"gap_points={metrics.gap_points:.2f}",
        f"baseline_python_line_coverage={baseline.python_line_coverage:.2f}",
        f"baseline_rust_line_coverage={baseline.rust_line_coverage:.2f}",
        f"baseline_max_gap_points={baseline.max_gap_points:.2f}",
    ]
    if failures:
        lines.append("status=failing")
        lines.extend(f"failure={failure}" for failure in failures)
    else:
        lines.append("status=passing")
    return "\n".join(lines)


def build_json_payload(
    metrics: CoverageMetrics,
    baseline: CoverageBaseline,
    failures: list[str],
    baseline_file: Path,
) -> dict[str, Any]:
    """Build machine-readable ratchet output.

    :param metrics: Current metrics.
    :type metrics: CoverageMetrics
    :param baseline: Baseline constraints.
    :type baseline: CoverageBaseline
    :param failures: Ratchet failures.
    :type failures: list[str]
    :param baseline_file: Baseline file path.
    :type baseline_file: Path
    :return: JSON-serializable payload.
    :rtype: dict[str, Any]
    """
    return {
        "passed": not failures,
        "metrics": asdict(metrics),
        "baseline": asdict(baseline),
        "baseline_file": str(baseline_file),
        "failures": failures,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    :param argv: Raw argument list.
    :type argv: list[str]
    :return: Parsed arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description="Enforce Python/Rust coverage ratchets."
    )
    parser.add_argument(
        "--python-xml",
        default="coverage-python/coverage.xml",
        help="Path to Python coverage Cobertura XML.",
    )
    parser.add_argument(
        "--rust-xml",
        default="coverage-rust/cobertura.xml",
        help="Path to Rust coverage Cobertura XML.",
    )
    parser.add_argument(
        "--baseline-file",
        default="config/coverage-baselines.json",
        help="Path to baseline JSON file.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Ratchet baseline file forward from current metrics.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run coverage ratchet checks.

    :param argv: Raw arguments.
    :type argv: list[str] | None
    :return: Exit code.
    :rtype: int
    """
    args = parse_args(argv if argv is not None else sys.argv[1:])
    python_xml = Path(args.python_xml)
    rust_xml = Path(args.rust_xml)
    baseline_file = Path(args.baseline_file)

    metrics = compute_metrics(python_xml, rust_xml)

    if args.update_baseline:
        if baseline_file.exists():
            existing = load_baseline(baseline_file)
        else:
            existing = CoverageBaseline(
                python_line_coverage=0.0,
                rust_line_coverage=0.0,
                max_gap_points=9999.0,
                updated_at=None,
            )
        updated = ratchet_baseline(existing, metrics)
        write_baseline(baseline_file, updated)
        payload = build_json_payload(metrics, updated, [], baseline_file)
        payload["updated"] = True
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Coverage baseline updated.")
            print(format_text_output(metrics, updated, []))
        return 0

    baseline = load_baseline(baseline_file)
    failures = evaluate_ratchet(metrics, baseline)
    if args.json:
        print(
            json.dumps(
                build_json_payload(metrics, baseline, failures, baseline_file),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(format_text_output(metrics, baseline, failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
