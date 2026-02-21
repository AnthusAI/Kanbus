"""Integration steps for Beads interoperability."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from behave import given, then, when

from features.steps.shared import ensure_project_directory, run_cli
from kanbus.ids import format_issue_key


def _fixture_beads_dir() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "specs" / "fixtures" / "beads_repo" / ".beads"


def _issues_path(context: object) -> Path:
    return context.working_directory / ".beads" / "issues.jsonl"


@given("a Beads fixture repository")
def given_beads_fixture_repo(context: object) -> None:
    temp_dir = Path(context.temp_dir)
    repo_path = temp_dir / "beads-interop"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    ensure_project_directory(repo_path)
    beads_dir = repo_path / ".beads"
    beads_dir.mkdir()
    fixture = _fixture_beads_dir()
    shutil.copy(fixture / "issues.jsonl", beads_dir / "issues.jsonl")
    shutil.copy(fixture / "metadata.json", beads_dir / "metadata.json")
    # Minimal config file so Kanbus CLI can resolve configuration.
    (repo_path / ".kanbus.yml").write_text("", encoding="utf-8")
    context.working_directory = repo_path
    context.last_beads_issue_id = None


@when('I run "kanbus --beads create Interop child via Kanbus --parent bdx-epic"')
def when_create_child(context: object) -> None:
    run_cli(context, "kanbus --beads create Interop child via Kanbus --parent bdx-epic")
    context.last_beads_issue_id = _capture_last_issue_id(context)


@when('I run "kanbus --beads create Interop updatable --parent bdx-epic"')
def when_create_updatable(context: object) -> None:
    run_cli(context, "kanbus --beads create Interop updatable --parent bdx-epic")
    context.last_beads_issue_id = _capture_last_issue_id(context)


@when('I run "kanbus --beads create Interop deletable --parent bdx-epic"')
def when_create_deletable(context: object) -> None:
    run_cli(context, "kanbus --beads create Interop deletable --parent bdx-epic")
    context.last_beads_issue_id = _capture_last_issue_id(context)


@when('I update the last created beads issue to status "{status}"')
def when_update_last_beads_issue(context: object, status: str) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    run_cli(context, f"kanbus --beads update {identifier} --status {status}")


@when("I delete the last created beads issue")
def when_delete_last_beads_issue(context: object) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    run_cli(context, f"kanbus --beads delete {identifier}")


@then("the last created beads issue should exist in beads issues.jsonl")
def then_last_issue_exists_in_beads(context: object) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    data = _load_beads_records(_issues_path(context))
    assert any(record.get("id") == identifier for record in data)


@then("beads issues.jsonl should contain the last created beads issue")
def then_beads_contains_last_issue(context: object) -> None:
    then_last_issue_exists_in_beads(context)


@then(
    'beads issues.jsonl should show the last created beads issue with status "{status}"'
)
def then_last_issue_has_status(context: object, status: str) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    data = _load_beads_records(_issues_path(context))
    match = next((record for record in data if record.get("id") == identifier), None)
    assert match is not None, "issue not found in beads JSONL"
    assert match.get("status") == status


@then("beads issues.jsonl should not contain the last created beads issue")
def then_beads_missing_last_issue(context: object) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    data = _load_beads_records(_issues_path(context))
    assert all(record.get("id") != identifier for record in data)


@then("the last created beads issue should appear in the Kanbus beads list output")
def then_last_issue_in_beads_list_output(context: object) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    display_key = format_issue_key(identifier, project_context=True)
    assert re.search(
        display_key, result.stdout, flags=re.IGNORECASE
    ), "issue id not in list output"


@then("the last created beads issue should not appear in the Kanbus beads list output")
def then_last_issue_not_in_beads_list_output(context: object) -> None:
    identifier = context.last_beads_issue_id
    assert identifier, "last beads issue id missing"
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    display_key = format_issue_key(identifier, project_context=True)
    assert not re.search(
        display_key, result.stdout, flags=re.IGNORECASE
    ), "issue id unexpectedly present in list output"


def _load_beads_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _capture_last_issue_id(context: object) -> str:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    # Accept full beads/kanbus identifier with any prefix, case-insensitive
    match = re.search(r"([A-Za-z]+-[A-Za-z0-9.]+)", result.stdout, flags=re.IGNORECASE)
    assert match, "no issue identifier found in stdout"
    return match.group(1).lower()
