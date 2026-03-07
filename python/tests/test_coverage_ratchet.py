from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import coverage_ratchet  # noqa: E402


def write_coverage_xml(path: Path, line_rate: float) -> None:
    path.write_text(f'<coverage line-rate="{line_rate}"/>', encoding="utf-8")


def test_parse_line_rate_returns_percentage_points(tmp_path: Path) -> None:
    xml_path = tmp_path / "coverage.xml"
    write_coverage_xml(xml_path, 0.805)

    assert coverage_ratchet.parse_line_rate(xml_path) == 80.5


def test_evaluate_ratchet_detects_regressions_and_gap() -> None:
    metrics = coverage_ratchet.CoverageMetrics(
        python_line_coverage=80.0,
        rust_line_coverage=64.0,
        gap_points=16.0,
    )
    baseline = coverage_ratchet.CoverageBaseline(
        python_line_coverage=80.5,
        rust_line_coverage=65.0,
        max_gap_points=15.5,
        updated_at="2026-03-06T00:00:00Z",
    )

    failures = coverage_ratchet.evaluate_ratchet(metrics, baseline)

    assert any("python coverage regression" in failure for failure in failures)
    assert any("rust coverage regression" in failure for failure in failures)
    assert any("coverage gap widened" in failure for failure in failures)


def test_ratchet_baseline_only_moves_forward() -> None:
    baseline = coverage_ratchet.CoverageBaseline(
        python_line_coverage=80.5,
        rust_line_coverage=65.0,
        max_gap_points=15.5,
        updated_at="2026-03-06T00:00:00Z",
    )
    metrics = coverage_ratchet.CoverageMetrics(
        python_line_coverage=80.0,
        rust_line_coverage=70.0,
        gap_points=10.0,
    )

    updated = coverage_ratchet.ratchet_baseline(baseline, metrics)

    assert updated.python_line_coverage == 80.5
    assert updated.rust_line_coverage == 70.0
    assert updated.max_gap_points == 10.0


def test_main_update_baseline_writes_ratcheted_values(tmp_path: Path) -> None:
    python_xml = tmp_path / "python.xml"
    rust_xml = tmp_path / "rust.xml"
    baseline_path = tmp_path / "baseline.json"

    write_coverage_xml(python_xml, 0.81)
    write_coverage_xml(rust_xml, 0.70)
    baseline_path.write_text(
        json.dumps(
            {
                "python_line_coverage": 80.5,
                "rust_line_coverage": 65.0,
                "max_gap_points": 15.5,
                "updated_at": "2026-03-06T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    exit_code = coverage_ratchet.main(
        [
            "--python-xml",
            str(python_xml),
            "--rust-xml",
            str(rust_xml),
            "--baseline-file",
            str(baseline_path),
            "--update-baseline",
        ]
    )

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["python_line_coverage"] == 81.0
    assert payload["rust_line_coverage"] == 70.0
    assert payload["max_gap_points"] == 11.0


def test_main_fails_on_regression(tmp_path: Path) -> None:
    python_xml = tmp_path / "python.xml"
    rust_xml = tmp_path / "rust.xml"
    baseline_path = tmp_path / "baseline.json"

    write_coverage_xml(python_xml, 0.80)
    write_coverage_xml(rust_xml, 0.60)
    baseline_path.write_text(
        json.dumps(
            {
                "python_line_coverage": 80.5,
                "rust_line_coverage": 65.0,
                "max_gap_points": 15.5,
                "updated_at": "2026-03-06T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    exit_code = coverage_ratchet.main(
        [
            "--python-xml",
            str(python_xml),
            "--rust-xml",
            str(rust_xml),
            "--baseline-file",
            str(baseline_path),
        ]
    )

    assert exit_code == 1
