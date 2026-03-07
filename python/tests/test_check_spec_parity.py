from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_spec_parity  # noqa: E402


def test_decode_escaped_literal_unescapes_regex_backslashes() -> None:
    literal = r'a kanbus issue (?P<identifier>[^"\\s]+) exists with priority (?P<priority>\\d+)'

    decoded = check_spec_parity._decode_escaped_literal(literal)

    assert r"\d+" in decoded
    assert r"\\d+" not in decoded


def test_collect_feature_steps_ignores_docstring_content(tmp_path: Path) -> None:
    feature_dir = tmp_path / "features"
    feature_dir.mkdir(parents=True)
    feature_path = feature_dir / "sample.feature"
    feature_path.write_text(
        (
            "Feature: Sample\n"
            "  Scenario: Ignores embedded policy text\n"
            "    Given a real step\n"
            '    """\n'
            "    Then this line should not be parsed as a step\n"
            '    """\n'
            "    Then another real step\n"
        ),
        encoding="utf-8",
    )

    steps = check_spec_parity.collect_feature_steps(feature_dir)

    assert "a real step" in steps
    assert "another real step" in steps
    assert "this line should not be parsed as a step" not in steps


def test_report_respects_non_strict_mode(monkeypatch) -> None:
    results = check_spec_parity.ParityResults(
        feature_steps={"a missing step"},
        python_steps=set(),
        rust_steps=set(),
        python_patterns=[],
        rust_patterns=[],
    )

    monkeypatch.setenv("KANBUS_PARITY_STRICT", "0")
    ok, _lines = check_spec_parity.report(results)

    assert ok is True


def test_report_fails_in_strict_mode_when_missing_steps(monkeypatch) -> None:
    results = check_spec_parity.ParityResults(
        feature_steps={"a missing step"},
        python_steps=set(),
        rust_steps=set(),
        python_patterns=[],
        rust_patterns=[],
    )

    monkeypatch.setenv("KANBUS_PARITY_STRICT", "1")
    ok, lines = check_spec_parity.report(results)

    assert ok is False
    assert any("Missing in Python:" in line for line in lines)
    assert any("Missing in Rust:" in line for line in lines)
