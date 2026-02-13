"""
Utility to provision Beads-based test workspaces under tmp/ for development.

It creates:
  tmp/beads_way      -> pristine clone of the Beads repository (JSONL)
  tmp/taskulus_way   -> copy of that clone, migrated to Taskulus JSON files

Usage:
  python tools/setup_beads_test_projects.py \
    --source https://github.com/<org>/beads \
    [--branch main]

Defaults:
  --source  https://github.com/steveyegge/beads
  --branch  (omitted, clone default branch)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def migrate_taskulus(target: Path) -> None:
    python_src = repo_root() / "python" / "src"
    sys.path.insert(0, str(python_src))
    from taskulus.migration import migrate_from_beads  # type: ignore

    migrate_from_beads(target)


def ensure_issues_jsonl(beads_dir: Path) -> None:
    """Guarantee .beads/issues.jsonl exists (Beads repo ships issues.jsonl.new)."""

    issues_path = beads_dir / "issues.jsonl"
    if issues_path.exists():
        return

    seeded = beads_dir / "issues.jsonl.new"
    if seeded.exists():
        shutil.copyfile(seeded, issues_path)
        return

    raise FileNotFoundError(f"no issues.jsonl in {beads_dir}")


def force_no_db(beads_dir: Path) -> None:
    """Make the cloned Beads repo use JSONL directly (no SQLite/daemon needed)."""

    config_path = beads_dir / "config.yaml"
    config_path.write_text("no-db: true\nno-daemon: true\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up Beads and Taskulus test projects under tmp/."
    )
    parser.add_argument(
        "--source",
        default="https://github.com/steveyegge/beads",
        help="Git URL or local path to the Beads repository.",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Optional branch or tag to clone.",
    )
    args = parser.parse_args()

    root = repo_root()
    tmp_dir = root / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    beads_way = tmp_dir / "beads_way"
    taskulus_way = tmp_dir / "taskulus_way"

    for path in (beads_way, taskulus_way):
        if path.exists():
            shutil.rmtree(path)

    clone_cmd = ["git", "clone", "--depth", "1"]
    if args.branch:
        clone_cmd.extend(["-b", args.branch])
    clone_cmd.extend([args.source, str(beads_way)])
    run(clone_cmd)

    ensure_issues_jsonl(beads_way / ".beads")
    force_no_db(beads_way / ".beads")

    shutil.copytree(beads_way, taskulus_way)

    migrate_taskulus(taskulus_way)

    print(f"Beads clone:      {beads_way}")
    print(f"Taskulus project: {taskulus_way}")


if __name__ == "__main__":
    main()
