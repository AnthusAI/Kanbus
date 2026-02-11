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


def _load_baseline(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_python_benchmark() -> BenchmarkResult:
    benchmark_path = ROOT / "tools" / "benchmark_index.py"
    output = subprocess.check_output([sys.executable, str(benchmark_path)], text=True)
    payload = json.loads(output)
    return BenchmarkResult(
        build_ms=float(payload["build_ms"]),
        cache_load_ms=float(payload["cache_load_ms"]),
    )


def _run_rust_benchmark() -> BenchmarkResult:
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


def _check_threshold(
    label: str,
    result: BenchmarkResult,
    baseline: Dict[str, float],
    allowed_regression_pct: float,
) -> list[str]:
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


def main() -> int:
    baseline_path = ROOT / "tools" / "perf_baseline.json"
    baseline = _load_baseline(baseline_path)
    allowed_regression_pct = float(baseline["allowed_regression_pct"])

    python_result = _run_python_benchmark()
    rust_result = _run_rust_benchmark()

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

    summary = {
        "python": python_result.__dict__,
        "rust": rust_result.__dict__,
        "allowed_regression_pct": allowed_regression_pct,
        "status": "ok" if not failures else "failed",
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
