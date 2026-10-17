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
    assert any("New steps missing an implementation:" in line for line in lines)
    assert any("python|a missing step" in line for line in lines)
    assert any("rust|a missing step" in line for line in lines)


def test_report_tolerates_steps_listed_in_the_known_gap_ratchet(monkeypatch) -> None:
    results = check_spec_parity.ParityResults(
        feature_steps={"a missing step"},
        python_steps=set(),
        rust_steps=set(),
        python_patterns=[],
        rust_patterns=[],
    )

    monkeypatch.setenv("KANBUS_PARITY_STRICT", "1")
    ok, _lines = check_spec_parity.report(
        results, {"python|a missing step", "rust|a missing step"}
    )

    assert ok is True


def test_report_fails_when_a_known_gap_has_been_fixed(monkeypatch) -> None:
    results = check_spec_parity.ParityResults(
        feature_steps=set(),
        python_steps=set(),
        rust_steps=set(),
        python_patterns=[],
        rust_patterns=[],
    )

    monkeypatch.setenv("KANBUS_PARITY_STRICT", "1")
    ok, lines = check_spec_parity.report(results, {"rust|a fixed step"})

    assert ok is False
    assert any("rust|a fixed step" in line for line in lines)


def test_cucumber_expression_matches_string_int_optional_and_alternation() -> None:
    pattern = check_spec_parity.StepPattern(
        text="the {string} issue(s) should be shown/hidden with {int} rows",
        is_regex=False,
        is_cucumber_expression=True,
    )
    compiled = check_spec_parity._compile_pattern(pattern)

    assert compiled.fullmatch('the "a \\"b\\"" issues should be hidden with 3 rows')
    assert compiled.fullmatch('the "x" issue should be shown with 12 rows')
    assert not compiled.fullmatch("the x issue should be shown with 12 rows")


def test_behave_parse_expression_treats_slash_and_parentheses_literally() -> None:
    pattern = check_spec_parity.StepPattern(
        text="the path (a/b) is {name}", is_regex=False
    )
    compiled = check_spec_parity._compile_pattern(pattern)

    assert compiled.fullmatch("the path (a/b) is anything")
    assert not compiled.fullmatch("the path a is anything")


def test_runtime_steps_exclude_scenarios_by_tag_and_expand_outlines(
    tmp_path: Path,
) -> None:
    feature_dir = tmp_path / "features"
    feature_dir.mkdir()
    (feature_dir / "sample.feature").write_text(
        (
            "Feature: Sample\n"
            "  Background:\n"
            "    Given a background step\n"
            "  @cloud\n"
            "  Scenario: Cloud only\n"
            "    When a cloud step\n"
            "  Scenario Outline: Parameterised\n"
            "    When the delay is <delay>\n"
            "    Examples:\n"
            "      | delay |\n"
            "      | 1s    |\n"
            "      | 2s    |\n"
        ),
        encoding="utf-8",
    )

    python_steps = check_spec_parity.collect_runtime_feature_steps(
        feature_dir, check_spec_parity.PYTHON_EXCLUDED_TAGS
    )
    rust_steps = check_spec_parity.collect_runtime_feature_steps(
        feature_dir, check_spec_parity.RUST_EXCLUDED_TAGS
    )

    assert "a cloud step" in python_steps
    assert "a cloud step" not in rust_steps
    assert {"the delay is 1s", "the delay is 2s", "a background step"} <= rust_steps


def test_python_step_collection_reads_concatenated_literals(tmp_path: Path) -> None:
    steps_dir = tmp_path / "steps"
    steps_dir.mkdir()
    (steps_dir / "sample_steps.py").write_text(
        (
            "from behave import given\n"
            "@given('a signed payload for account \"{account}\" '\n"
            "       'and project \"{project}\"')\n"
            "def step(context, account, project):\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    patterns = check_spec_parity.collect_python_steps(steps_dir)

    assert [pattern.text for pattern in patterns] == [
        'a signed payload for account "{account}" and project "{project}"'
    ]
