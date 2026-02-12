"""Check benchmark performance against regression thresholds."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BenchmarkResult:
    """Benchmark results in milliseconds."""

    build_ms: float
    cache_load_ms: float


@dataclass(frozen=True)
class DiscoveryScenarioResult:
    """Discovery benchmark results in milliseconds."""

    discover_ms: float
    list_ms: float
    ready_ms: float


@dataclass(frozen=True)
class DiscoveryBenchmarkResult:
    """Discovery benchmark results for serial and parallel runs."""

    serial: "DiscoveryModeResult"
    parallel: "DiscoveryModeResult"


@dataclass(frozen=True)
class DiscoveryModeResult:
    """Discovery benchmark results for a single mode."""

    single: DiscoveryScenarioResult
    multi: DiscoveryScenarioResult


def _load_baseline(path: Path) -> Dict[str, Any]:
    """Load benchmark baseline thresholds.

    :param path: Path to the baseline JSON file.
    :type path: Path
    :return: Parsed JSON payload.
    :rtype: Dict[str, Any]
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _run_python_benchmark() -> BenchmarkResult:
    """Run the Python index benchmark and parse results.

    :return: Benchmark results.
    :rtype: BenchmarkResult
    """
    benchmark_path = ROOT / "tools" / "benchmark_index.py"
    output = subprocess.check_output([sys.executable, str(benchmark_path)], text=True)
    payload = json.loads(output)
    return BenchmarkResult(
        build_ms=float(payload["build_ms"]),
        cache_load_ms=float(payload["cache_load_ms"]),
    )


def _run_rust_benchmark() -> BenchmarkResult:
    """Run the Rust index benchmark and parse results.

    :return: Benchmark results.
    :rtype: BenchmarkResult
    :raises RuntimeError: If JSON output is missing.
    """
    cargo = ["cargo", "run", "--release", "--bin", "index_benchmark"]
    output = subprocess.check_output(cargo, cwd=ROOT / "rust", text=True)
    lines = output.splitlines()
    json_start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = index
            break
    if json_start is None:
        raise RuntimeError("rust benchmark did not emit JSON")
    json_text = "\n".join(lines[json_start:])
    payload = json.loads(json_text)
    return BenchmarkResult(
        build_ms=float(payload["build_ms"]),
        cache_load_ms=float(payload["cache_load_ms"]),
    )


def _run_python_discovery_benchmark() -> DiscoveryBenchmarkResult:
    """Run the Python discovery benchmark and parse results.

    :return: Discovery benchmark results.
    :rtype: DiscoveryBenchmarkResult
    """
    benchmark_path = ROOT / "tools" / "benchmark_discovery.py"
    output = subprocess.check_output([sys.executable, str(benchmark_path)], text=True)
    payload = json.loads(output)
    return DiscoveryBenchmarkResult(
        serial=DiscoveryModeResult(
            single=DiscoveryScenarioResult(
                discover_ms=float(payload["serial"]["single"]["discover_ms"]),
                list_ms=float(payload["serial"]["single"]["list_ms"]),
                ready_ms=float(payload["serial"]["single"]["ready_ms"]),
            ),
            multi=DiscoveryScenarioResult(
                discover_ms=float(payload["serial"]["multi"]["discover_ms"]),
                list_ms=float(payload["serial"]["multi"]["list_ms"]),
                ready_ms=float(payload["serial"]["multi"]["ready_ms"]),
            ),
        ),
        parallel=DiscoveryModeResult(
            single=DiscoveryScenarioResult(
                discover_ms=float(payload["parallel"]["single"]["discover_ms"]),
                list_ms=float(payload["parallel"]["single"]["list_ms"]),
                ready_ms=float(payload["parallel"]["single"]["ready_ms"]),
            ),
            multi=DiscoveryScenarioResult(
                discover_ms=float(payload["parallel"]["multi"]["discover_ms"]),
                list_ms=float(payload["parallel"]["multi"]["list_ms"]),
                ready_ms=float(payload["parallel"]["multi"]["ready_ms"]),
            ),
        ),
    )


def _run_rust_discovery_benchmark() -> DiscoveryBenchmarkResult:
    """Run the Rust discovery benchmark and parse results.

    :return: Discovery benchmark results.
    :rtype: DiscoveryBenchmarkResult
    :raises RuntimeError: If JSON output is missing.
    """
    cargo = [
        "cargo",
        "run",
        "--release",
        "--manifest-path",
        str(ROOT / "rust" / "Cargo.toml"),
        "--bin",
        "discovery_benchmark",
    ]
    output = subprocess.check_output(cargo, cwd=ROOT, text=True)
    lines = output.splitlines()
    json_start = None
    for index, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = index
            break
    if json_start is None:
        raise RuntimeError("rust discovery benchmark did not emit JSON")
    json_text = "\n".join(lines[json_start:])
    payload = json.loads(json_text)
    return DiscoveryBenchmarkResult(
        serial=DiscoveryModeResult(
            single=DiscoveryScenarioResult(
                discover_ms=float(payload["serial"]["single"]["discover_ms"]),
                list_ms=float(payload["serial"]["single"]["list_ms"]),
                ready_ms=float(payload["serial"]["single"]["ready_ms"]),
            ),
            multi=DiscoveryScenarioResult(
                discover_ms=float(payload["serial"]["multi"]["discover_ms"]),
                list_ms=float(payload["serial"]["multi"]["list_ms"]),
                ready_ms=float(payload["serial"]["multi"]["ready_ms"]),
            ),
        ),
        parallel=DiscoveryModeResult(
            single=DiscoveryScenarioResult(
                discover_ms=float(payload["parallel"]["single"]["discover_ms"]),
                list_ms=float(payload["parallel"]["single"]["list_ms"]),
                ready_ms=float(payload["parallel"]["single"]["ready_ms"]),
            ),
            multi=DiscoveryScenarioResult(
                discover_ms=float(payload["parallel"]["multi"]["discover_ms"]),
                list_ms=float(payload["parallel"]["multi"]["list_ms"]),
                ready_ms=float(payload["parallel"]["multi"]["ready_ms"]),
            ),
        ),
    )


def _check_threshold(
    label: str,
    result: BenchmarkResult,
    baseline: Dict[str, float],
    allowed_regression_pct: float,
) -> list[str]:
    """Check benchmark results against thresholds.

    :param label: Label for failure messages.
    :type label: str
    :param result: Benchmark results.
    :type result: BenchmarkResult
    :param baseline: Baseline thresholds.
    :type baseline: Dict[str, float]
    :param allowed_regression_pct: Allowed regression percentage.
    :type allowed_regression_pct: float
    :return: List of failure messages.
    :rtype: list[str]
    """
    failures = []
    build_limit = baseline["build_ms"] * (1.0 + allowed_regression_pct / 100.0)
    cache_limit = baseline["cache_load_ms"] * (1.0 + allowed_regression_pct / 100.0)

    if result.build_ms > build_limit:
        failures.append(
            f"{label} build_ms {result.build_ms:.2f} exceeded {build_limit:.2f}"
        )
    if result.cache_load_ms > cache_limit:
        failures.append(
            f"{label} cache_load_ms {result.cache_load_ms:.2f} exceeded {cache_limit:.2f}"
        )

    return failures


def _check_discovery_thresholds(
    label: str,
    result: DiscoveryBenchmarkResult,
    baseline: Dict[str, Dict[str, Dict[str, float]]],
    allowed_regression_pct: float,
) -> list[str]:
    """Check discovery benchmarks against thresholds.

    :param label: Label for failure messages.
    :type label: str
    :param result: Discovery benchmark results.
    :type result: DiscoveryBenchmarkResult
    :param baseline: Baseline thresholds for discovery benchmarks.
    :type baseline: Dict[str, Dict[str, Dict[str, float]]]
    :param allowed_regression_pct: Allowed regression percentage.
    :type allowed_regression_pct: float
    :return: List of failure messages.
    :rtype: list[str]
    """
    failures = []
    for mode_name, mode_result in (
        ("serial", result.serial),
        ("parallel", result.parallel),
    ):
        mode_baseline = baseline[mode_name]
        for scenario_name, scenario_result in (
            ("single", mode_result.single),
            ("multi", mode_result.multi),
        ):
            scenario_baseline = mode_baseline[scenario_name]
            for metric in ("discover_ms", "list_ms", "ready_ms"):
                limit = scenario_baseline[metric] * (
                    1.0 + allowed_regression_pct / 100.0
                )
                value = getattr(scenario_result, metric)
                if value > limit:
                    failures.append(
                        f"{label} {mode_name} {scenario_name} {metric} {value:.2f} exceeded {limit:.2f}"
                    )
    return failures


def main() -> int:
    """Run benchmark checks against configured thresholds.

    :return: Exit code 0 when benchmarks are within thresholds, 1 otherwise.
    :rtype: int
    :raises RuntimeError: If the Rust benchmark output is missing JSON.
    """
    baseline_path = ROOT / "tools" / "perf_baseline.json"
    baseline = _load_baseline(baseline_path)
    allowed_regression_pct = float(baseline["allowed_regression_pct"])

    python_result = _run_python_benchmark()
    rust_result = _run_rust_benchmark()
    python_discovery = _run_python_discovery_benchmark()
    rust_discovery = _run_rust_discovery_benchmark()

    failures = []
    failures.extend(
        _check_threshold(
            "python",
            python_result,
            baseline["python"],
            allowed_regression_pct,
        )
    )
    failures.extend(
        _check_threshold(
            "rust",
            rust_result,
            baseline["rust"],
            allowed_regression_pct,
        )
    )
    failures.extend(
        _check_discovery_thresholds(
            "python discovery",
            python_discovery,
            baseline["discovery"]["python"],
            allowed_regression_pct,
        )
    )
    failures.extend(
        _check_discovery_thresholds(
            "rust discovery",
            rust_discovery,
            baseline["discovery"]["rust"],
            allowed_regression_pct,
        )
    )

    summary = {
        "python": python_result.__dict__,
        "rust": rust_result.__dict__,
        "python_discovery": {
            "serial": {
                "single": python_discovery.serial.single.__dict__,
                "multi": python_discovery.serial.multi.__dict__,
            },
            "parallel": {
                "single": python_discovery.parallel.single.__dict__,
                "multi": python_discovery.parallel.multi.__dict__,
            },
        },
        "rust_discovery": {
            "serial": {
                "single": rust_discovery.serial.single.__dict__,
                "multi": rust_discovery.serial.multi.__dict__,
            },
            "parallel": {
                "single": rust_discovery.parallel.single.__dict__,
                "multi": rust_discovery.parallel.multi.__dict__,
            },
        },
        "allowed_regression_pct": allowed_regression_pct,
        "status": "ok" if not failures else "failed",
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
