"""Behave steps for compatibility mode."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import yaml
from behave import given, then, when

from features.steps.shared import (
    ensure_git_repository,
    ensure_project_directory,
)
from kanbus.beads_write import set_test_beads_slug_sequence
from kanbus.config import DEFAULT_CONFIGURATION


def _fixture_beads_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "fixtures"
        / "beads_repo"
        / ".beads"
    )


@given("a Kanbus project with beads compatibility enabled")
def given_project_with_beads_compatibility(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    target_beads = repository_path / ".beads"
    shutil.copytree(_fixture_beads_dir(), target_beads)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["beads_compatibility"] = True
    (repository_path / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    project_dir = repository_path / payload["project_directory"]
    (project_dir / "issues").mkdir(parents=True, exist_ok=True)
    context.working_directory = repository_path


@given("a project directory exists")
def given_project_directory_exists(context: object) -> None:
    repository_path = getattr(context, "working_directory", None)
    if repository_path is None:
        raise RuntimeError("working directory not set")
    ensure_project_directory(Path(repository_path))


@then('beads issues.jsonl should contain "{identifier}"')
def then_beads_jsonl_contains(context: object, identifier: str) -> None:
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    contents = issues_path.read_text(encoding="utf-8")
    assert identifier in contents


@then('beads issues.jsonl should include assignee "{assignee}"')
def then_beads_jsonl_contains_assignee(context: object, assignee: str) -> None:
    records = _load_beads_records(_issues_path(context))
    assert any(record.get("assignee") == assignee for record in records)


@then('beads issues.jsonl should include description "{description}"')
def then_beads_jsonl_contains_description(context: object, description: str) -> None:
    records = _load_beads_records(_issues_path(context))
    assert any(record.get("description") == description for record in records)


@then('beads issues.jsonl should include status "{status}" for "{identifier}"')
def then_beads_jsonl_contains_status(
    context: object, status: str, identifier: str
) -> None:
    records = _load_beads_records(_issues_path(context))
    matches = [record for record in records if record.get("id") == identifier]
    assert matches
    assert matches[0].get("status") == status


@then('beads issues.jsonl should not contain "{identifier}"')
def then_beads_jsonl_not_contains(context: object, identifier: str) -> None:
    issues_path = _issues_path(context)
    contents = issues_path.read_text(encoding="utf-8")
    # Check that the identifier doesn't exist as an issue ID in the JSON
    for line in contents.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("id") == identifier:
            raise AssertionError(f"Issue {identifier} still exists in issues.jsonl")


@given('the beads slug generator always returns "{slug}"')
def given_beads_slug_generator_returns(context: object, slug: str) -> None:
    set_test_beads_slug_sequence([slug] * 11)


@given('a beads issue with id "{identifier}" exists')
def given_beads_issue_exists(context: object, identifier: str) -> None:
    issues_path = _issues_path(context)
    record = {
        "id": identifier,
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    with issues_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _issues_path(context: object) -> Path:
    return Path(context.working_directory) / ".beads" / "issues.jsonl"


def _load_beads_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
