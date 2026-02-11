"""End-to-end CRUD integration tests."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import yaml
from click.testing import CliRunner

from taskulus.cli import cli


def run_cli(cwd: Path, command: str) -> object:
    runner = CliRunner()
    args = shlex.split(command)[1:]
    previous = Path.cwd()
    try:
        os.chdir(cwd)
        return runner.invoke(cli, args)
    finally:
        os.chdir(previous)


def load_project_directory(root: Path) -> Path:
    data = yaml.safe_load((root / ".taskulus.yaml").read_text(encoding="utf-8"))
    return root / data["project_dir"]


def load_issue(project_dir: Path, identifier: str) -> dict[str, object]:
    issue_path = project_dir / "issues" / f"{identifier}.json"
    return json.loads(issue_path.read_text(encoding="utf-8"))


def test_crud_workflow(tmp_path: Path) -> None:
    repository_path = tmp_path / "repo"
    repository_path.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repository_path, check=True, capture_output=True
    )

    result = run_cli(repository_path, "tsk init")
    assert result.exit_code == 0

    result = run_cli(repository_path, "tsk create Implement OAuth2 flow")
    assert result.exit_code == 0
    match = re.search(r"(tsk-[0-9a-f]{6})", result.stdout)
    assert match is not None
    identifier = match.group(1)

    result = run_cli(repository_path, f"tsk show {identifier}")
    assert result.exit_code == 0
    assert "Implement OAuth2 flow" in result.stdout

    result = run_cli(repository_path, f'tsk update {identifier} --title "New Title"')
    assert result.exit_code == 0
    project_dir = load_project_directory(repository_path)
    issue = load_issue(project_dir, identifier)
    assert issue["title"] == "New Title"

    result = run_cli(repository_path, f"tsk close {identifier}")
    assert result.exit_code == 0
    issue = load_issue(project_dir, identifier)
    assert issue["status"] == "closed"
    assert issue["closed_at"] is not None

    result = run_cli(repository_path, f"tsk delete {identifier}")
    assert result.exit_code == 0
    issue_path = project_dir / "issues" / f"{identifier}.json"
    assert not issue_path.exists()
