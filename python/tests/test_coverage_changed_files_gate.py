from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import coverage_changed_files_gate  # noqa: E402


def write_coverage_xml(path: Path, entries: dict[str, tuple[int, int]]) -> None:
    classes = []
    for filename, (covered, total) in entries.items():
        line_nodes = []
        for index in range(total):
            hits = 1 if index < covered else 0
            line_nodes.append(f'<line number="{index + 1}" hits="{hits}"/>')
        classes.append(
            f'<class filename="{filename}" line-rate="0"><lines>{"".join(line_nodes)}</lines></class>'
        )
    xml = (
        '<coverage line-rate="0"><packages><package><classes>'
        f'{"".join(classes)}'
        "</classes></package></packages></coverage>"
    )
    path.write_text(xml, encoding="utf-8")


def run_main(
    tmp_path: Path,
    monkeypatch,
    changed_files: list[str],
    python_entries: dict[str, tuple[int, int]],
    rust_entries: dict[str, tuple[int, int]],
    config: dict[str, object],
) -> int:
    python_xml = tmp_path / "python.xml"
    rust_xml = tmp_path / "rust.xml"
    config_path = tmp_path / "gate.json"
    write_coverage_xml(python_xml, python_entries)
    write_coverage_xml(rust_xml, rust_entries)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(
        coverage_changed_files_gate,
        "_run_git_diff",
        lambda base_ref, head_ref: changed_files,
    )
    return coverage_changed_files_gate.main(
        [
            "--python-xml",
            str(python_xml),
            "--rust-xml",
            str(rust_xml),
            "--config",
            str(config_path),
            "--base-ref",
            "BASE",
            "--head-ref",
            "HEAD",
            "--json",
        ]
    )


def test_gate_passes_when_no_changed_source_files(tmp_path: Path, monkeypatch) -> None:
    exit_code = run_main(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        changed_files=["README.md"],
        python_entries={"kanbus/cli.py": (80, 100)},
        rust_entries={"src/cli.rs": (80, 100)},
        config={
            "python_min": 75.0,
            "rust_min": 65.0,
            "waivers": [],
            "waiver_min_improvement_points": 3.0,
            "file_baselines": {},
        },
    )
    assert exit_code == 0


def test_gate_fails_for_non_waived_file_below_minimum(
    tmp_path: Path, monkeypatch
) -> None:
    exit_code = run_main(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        changed_files=["python/src/kanbus/cli.py"],
        python_entries={"kanbus/cli.py": (60, 100)},
        rust_entries={"src/cli.rs": (80, 100)},
        config={
            "python_min": 75.0,
            "rust_min": 65.0,
            "waivers": [],
            "waiver_min_improvement_points": 3.0,
            "file_baselines": {},
        },
    )
    assert exit_code == 1


def test_gate_passes_waived_file_with_required_improvement(
    tmp_path: Path, monkeypatch
) -> None:
    exit_code = run_main(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        changed_files=["python/src/kanbus/snyk_sync.py"],
        python_entries={"kanbus/snyk_sync.py": (40, 100)},
        rust_entries={"src/cli.rs": (80, 100)},
        config={
            "python_min": 75.0,
            "rust_min": 65.0,
            "waivers": ["python/src/kanbus/snyk_sync.py"],
            "waiver_min_improvement_points": 3.0,
            "file_baselines": {"python/src/kanbus/snyk_sync.py": 35.0},
        },
    )
    assert exit_code == 0


def test_gate_fails_waived_file_with_insufficient_improvement(
    tmp_path: Path, monkeypatch
) -> None:
    exit_code = run_main(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        changed_files=["python/src/kanbus/snyk_sync.py"],
        python_entries={"kanbus/snyk_sync.py": (36, 100)},
        rust_entries={"src/cli.rs": (80, 100)},
        config={
            "python_min": 75.0,
            "rust_min": 65.0,
            "waivers": ["python/src/kanbus/snyk_sync.py"],
            "waiver_min_improvement_points": 3.0,
            "file_baselines": {"python/src/kanbus/snyk_sync.py": 35.0},
        },
    )
    assert exit_code == 1
