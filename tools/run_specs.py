#!/usr/bin/env python3
"""Run Python and Rust Gherkin specs with coverage reporting."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CommandResult:
    """Result of a subprocess command."""

    command: list[str]
    return_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CoverageResult:
    """Coverage result summary."""

    line_rate: float
    percentage: float


@dataclass(frozen=True)
class SpecRunSummary:
    """Summary of spec runs across Python and Rust."""

    python_ok: bool
    rust_ok: bool
    python_coverage: CoverageResult | None
    rust_coverage: CoverageResult | None
    python_error: str | None
    rust_error: str | None
    rust_coverage_ok: bool
    rust_coverage_error: str | None


def _run_command(command: list[str], cwd: Path | None = None) -> CommandResult:
    """Run a subprocess command and capture output.

    :param command: Command and arguments to execute.
    :type command: list[str]
    :param cwd: Working directory for the command.
    :type cwd: Path | None
    :return: Command result with stdout/stderr and return code.
    :rtype: CommandResult
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=command,
        return_code=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


def _parse_line_rate(xml_path: Path) -> CoverageResult:
    """Parse coverage line-rate from an XML report.

    :param xml_path: Path to the coverage XML file.
    :type xml_path: Path
    :return: Coverage results.
    :rtype: CoverageResult
    :raises ValueError: If the line-rate attribute is missing.
    """
    import xml.etree.ElementTree as element_tree

    root = element_tree.parse(xml_path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise ValueError("Missing line-rate attribute in coverage XML")
    value = float(line_rate)
    return CoverageResult(line_rate=value, percentage=round(value * 100.0, 1))


def _run_python_specs() -> tuple[bool, CoverageResult | None, CommandResult]:
    """Run Python Behave specs with coverage reporting.

    :return: Tuple of success flag, coverage result, and command result.
    :rtype: tuple[bool, CoverageResult | None, CommandResult]
    """
    python_dir = ROOT / "python"
    coverage_xml = python_dir / "coverage.xml"
    if coverage_xml.exists():
        coverage_xml.unlink()

    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--source",
        "kanbus",
        "-m",
        "behave",
    ]
    result = _run_command(command, cwd=python_dir)
    ok = result.return_code == 0
    if ok:
        _run_command([sys.executable, "-m", "coverage", "xml", "-o", "coverage.xml"], cwd=python_dir)

    coverage_result = None
    if coverage_xml.exists():
        coverage_result = _parse_line_rate(coverage_xml)
    return ok, coverage_result, result


def _run_rust_specs() -> tuple[bool, CommandResult]:
    """Run Rust cucumber specs.

    :return: Tuple of success flag and command result.
    :rtype: tuple[bool, CommandResult]
    """
    rust_dir = ROOT / "rust"
    command = ["cargo", "test", "--test", "cucumber"]
    result = _run_command(command, cwd=rust_dir)
    return result.return_code == 0, result


def _run_rust_coverage() -> tuple[bool, CoverageResult | None, CommandResult]:
    """Run Rust coverage via cargo-llvm-cov.

    :return: Tuple of success flag, coverage result, and command result.
    :rtype: tuple[bool, CoverageResult | None, CommandResult]
    """
    rust_dir = ROOT / "rust"
    coverage_dir = ROOT / "coverage-rust"
    coverage_xml = coverage_dir / "cobertura.xml"
    if coverage_xml.exists():
        coverage_xml.unlink()

    console_dir = ROOT / "apps" / "console"
    ui_dir = ROOT / "packages" / "ui"
    coverage_dir.mkdir(parents=True, exist_ok=True)

    assets_result = _run_command(["npm", "ci"], cwd=ui_dir)
    if assets_result.return_code != 0:
        return False, None, assets_result
    assets_result = _run_command(["npm", "run", "build"], cwd=ui_dir)
    if assets_result.return_code != 0:
        return False, None, assets_result
    assets_result = _run_command(["npm", "ci"], cwd=console_dir)
    if assets_result.return_code != 0:
        return False, None, assets_result
    assets_result = _run_command(["npm", "run", "build"], cwd=console_dir)
    if assets_result.return_code != 0:
        return False, None, assets_result
    assets_source = console_dir / "dist"
    assets_target = rust_dir / "embedded_assets" / "console"
    if not assets_source.exists():
        return (
            False,
            None,
            CommandResult(
                command=["sync-console-assets"],
                return_code=1,
                stdout="",
                stderr=f"Missing console assets at {assets_source}",
            ),
        )
    if assets_target.exists():
        shutil.rmtree(assets_target)
    shutil.copytree(assets_source, assets_target)

    command = [
        "cargo",
        "llvm-cov",
        "--locked",
        "--no-report",
        "--all-features",
        "--lib",
        "--bins",
        "--tests",
        "--ignore-filename-regex",
        "features/steps/.*|src/bin/.*|src/main.rs",
    ]
    result = _run_command(command, cwd=rust_dir)
    if result.return_code != 0:
        return False, None, result
    report_result = _run_command(
        [
            "cargo",
            "llvm-cov",
            "report",
            "--locked",
            "--cobertura",
            "--output-path",
            str(coverage_xml),
        ],
        cwd=rust_dir,
    )
    ok = report_result.return_code == 0
    coverage_result = None
    if coverage_xml.exists():
        coverage_result = _parse_line_rate(coverage_xml)
    else:
        ok = False
    return ok, coverage_result, report_result


def _summarize_json(summary: SpecRunSummary) -> None:
    """Print a JSON summary of spec runs.

    :param summary: Summary to print.
    :type summary: SpecRunSummary
    :return: None.
    :rtype: None
    """
    payload = {
        "python": {
            "ok": summary.python_ok,
            "coverage": None,
            "error": summary.python_error,
        },
        "rust": {
            "ok": summary.rust_ok,
            "coverage": None,
            "error": summary.rust_error,
        },
        "rust_coverage": {
            "ok": summary.rust_coverage_ok,
            "error": summary.rust_coverage_error,
        },
    }
    if summary.python_coverage is not None:
        payload["python"]["coverage"] = {
            "line_rate": summary.python_coverage.line_rate,
            "percentage": summary.python_coverage.percentage,
        }
    if summary.rust_coverage is not None:
        payload["rust"]["coverage"] = {
            "line_rate": summary.rust_coverage.line_rate,
            "percentage": summary.rust_coverage.percentage,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))


def _summarize_text(summary: SpecRunSummary) -> None:
    """Print a human-readable summary of spec runs.

    :param summary: Summary to print.
    :type summary: SpecRunSummary
    :return: None.
    :rtype: None
    """
    python_status = "passed" if summary.python_ok else "failed"
    rust_status = "passed" if summary.rust_ok else "failed"
    python_coverage = "n/a"
    rust_coverage = "n/a"
    if summary.python_coverage is not None:
        python_coverage = f"{summary.python_coverage.percentage:.1f}%"
    if summary.rust_coverage is not None:
        rust_coverage = f"{summary.rust_coverage.percentage:.1f}%"
    rust_coverage_status = "passed" if summary.rust_coverage_ok else "failed"

    print("Kanbus spec summary")
    print(f"Python specs: {python_status}")
    print(f"Python coverage: {python_coverage}")
    if summary.python_error:
        print(f"Python error: {summary.python_error}")
    print(f"Rust specs: {rust_status}")
    print(f"Rust coverage: {rust_coverage} ({rust_coverage_status})")
    if summary.rust_error:
        print(f"Rust error: {summary.rust_error}")
    if summary.rust_coverage_error:
        print(f"Rust coverage error: {summary.rust_coverage_error}")


def main(argv: list[str]) -> int:
    """Run the Kanbus spec suite for Python and Rust.

    :param argv: Command-line arguments.
    :type argv: list[str]
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Run Kanbus spec suites")
    parser.add_argument(
        "--skip-rust-coverage",
        action="store_true",
        help="Skip cargo-llvm-cov coverage run.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="text",
        help="Output format for the final summary.",
    )
    args = parser.parse_args(argv)

    python_ok, python_coverage, python_result = _run_python_specs()
    rust_ok, rust_result = _run_rust_specs()

    rust_coverage_ok = True
    rust_coverage = None
    rust_coverage_error = None
    if not args.skip_rust_coverage:
        rust_coverage_ok, rust_coverage, coverage_result = _run_rust_coverage()
        if not rust_coverage_ok:
            rust_coverage_error = (coverage_result.stderr or coverage_result.stdout).strip() or None

    python_error = None
    if not python_ok:
        python_error = python_result.stderr.strip() or python_result.stdout.strip() or None
    rust_error = None
    if not rust_ok:
        rust_error = rust_result.stderr.strip() or rust_result.stdout.strip() or None

    summary = SpecRunSummary(
        python_ok=python_ok,
        rust_ok=rust_ok,
        python_coverage=python_coverage,
        rust_coverage=rust_coverage,
        python_error=python_error,
        rust_error=rust_error,
        rust_coverage_ok=rust_coverage_ok,
        rust_coverage_error=rust_coverage_error,
    )
    if args.format == "json":
        _summarize_json(summary)
    else:
        _summarize_text(summary)

    exit_code = 0
    if not python_ok or not rust_ok or not rust_coverage_ok:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
