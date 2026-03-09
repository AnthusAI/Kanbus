#!/usr/bin/env python3
"""Enforce coverage floors for changed source files."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any
import xml.etree.ElementTree as element_tree


@dataclass(frozen=True)
class FileCoverage:
    """Per-file coverage details."""

    percentage: float
    covered: int
    total: int


def _parse_coverage(xml_path: Path) -> dict[str, FileCoverage]:
    root = element_tree.parse(xml_path).getroot()
    files: dict[str, FileCoverage] = {}
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        lines = class_node.findall("./lines/line")
        total = len(lines)
        covered = sum(1 for line in lines if int(line.attrib.get("hits", "0")) > 0)
        percentage = round((covered / total * 100.0) if total else 0.0, 4)
        files[filename] = FileCoverage(
            percentage=percentage,
            covered=covered,
            total=total,
        )
    return files


def _run_git_diff(base_ref: str, head_ref: str) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    raise RuntimeError(
        f"unable to compute changed files for refs {base_ref}..{head_ref}"
    )


def _map_python_coverage_key(changed_file: str) -> str | None:
    prefix = "python/src/"
    if not changed_file.startswith(prefix) or not changed_file.endswith(".py"):
        return None
    return changed_file.removeprefix(prefix)


def _map_rust_coverage_key(changed_file: str) -> str | None:
    prefix = "rust/"
    if not changed_file.startswith(prefix) or not changed_file.endswith(".rs"):
        return None
    return changed_file.removeprefix(prefix)


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("python_min", 75.0)
    payload.setdefault("rust_min", 65.0)
    payload.setdefault("waivers", [])
    payload.setdefault("waiver_min_improvement_points", 3.0)
    payload.setdefault("file_baselines", {})
    return payload


def _evaluate_file(
    changed_file: str,
    language: str,
    coverage_key: str,
    coverage_files: dict[str, FileCoverage],
    config: dict[str, Any],
) -> dict[str, Any]:
    entry = coverage_files.get(coverage_key)
    if entry is None:
        return {
            "file": changed_file,
            "language": language,
            "status": "failed",
            "reason": f"coverage entry not found for '{coverage_key}'",
        }

    minimum = float(config[f"{language}_min"])
    waivers = set(config["waivers"])
    waiver_improvement = float(config["waiver_min_improvement_points"])
    baselines: dict[str, float] = {
        key: float(value) for key, value in config["file_baselines"].items()
    }
    is_waived = changed_file in waivers

    if entry.percentage >= minimum:
        return {
            "file": changed_file,
            "language": language,
            "status": "passed",
            "percentage": entry.percentage,
            "minimum": minimum,
            "waived": is_waived,
            "reason": "meets minimum",
        }

    if not is_waived:
        return {
            "file": changed_file,
            "language": language,
            "status": "failed",
            "percentage": entry.percentage,
            "minimum": minimum,
            "waived": False,
            "reason": "below minimum and not waived",
        }

    baseline = baselines.get(changed_file)
    if baseline is None:
        return {
            "file": changed_file,
            "language": language,
            "status": "failed",
            "percentage": entry.percentage,
            "minimum": minimum,
            "waived": True,
            "reason": "waived file is missing file_baselines entry",
        }

    improvement = round(entry.percentage - baseline, 4)
    if improvement < waiver_improvement:
        return {
            "file": changed_file,
            "language": language,
            "status": "failed",
            "percentage": entry.percentage,
            "minimum": minimum,
            "waived": True,
            "baseline": baseline,
            "improvement": improvement,
            "waiver_min_improvement_points": waiver_improvement,
            "reason": "waived file did not improve enough",
        }
    return {
        "file": changed_file,
        "language": language,
        "status": "passed",
        "percentage": entry.percentage,
        "minimum": minimum,
        "waived": True,
        "baseline": baseline,
        "improvement": improvement,
        "waiver_min_improvement_points": waiver_improvement,
        "reason": "waived file improved enough",
    }


def _render_text(payload: dict[str, Any]) -> str:
    lines = [
        "Changed-files coverage gate",
        f"base_ref={payload['base_ref']}",
        f"head_ref={payload['head_ref']}",
        f"changed_source_files={payload['changed_source_files']}",
        f"checked_files={payload['checked_files']}",
        f"failed_files={payload['failed_files']}",
    ]
    for result in payload["results"]:
        line = (
            f"{result['status']}: {result['file']} ({result['language']})"
            f" - {result['reason']}"
        )
        if "percentage" in result:
            line += f" [{result['percentage']:.2f}%]"
        lines.append(line)
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enforce coverage thresholds for changed Python and Rust files.",
    )
    parser.add_argument("--python-xml", required=True)
    parser.add_argument("--rust-xml", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config = _load_config(Path(args.config))
    python_coverage = _parse_coverage(Path(args.python_xml))
    rust_coverage = _parse_coverage(Path(args.rust_xml))
    changed_files = _run_git_diff(args.base_ref, args.head_ref)

    results: list[dict[str, Any]] = []
    checked = 0
    changed_source = 0
    for changed_file in changed_files:
        python_key = _map_python_coverage_key(changed_file)
        rust_key = _map_rust_coverage_key(changed_file)
        if python_key is None and rust_key is None:
            continue
        changed_source += 1
        if python_key is not None:
            checked += 1
            results.append(
                _evaluate_file(
                    changed_file=changed_file,
                    language="python",
                    coverage_key=python_key,
                    coverage_files=python_coverage,
                    config=config,
                )
            )
        if rust_key is not None:
            checked += 1
            results.append(
                _evaluate_file(
                    changed_file=changed_file,
                    language="rust",
                    coverage_key=rust_key,
                    coverage_files=rust_coverage,
                    config=config,
                )
            )

    failed = [result for result in results if result["status"] != "passed"]
    payload = {
        "passed": not failed,
        "base_ref": args.base_ref,
        "head_ref": args.head_ref,
        "changed_source_files": changed_source,
        "checked_files": checked,
        "failed_files": len(failed),
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(payload))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
