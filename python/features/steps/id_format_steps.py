"""Steps for ID format mode integration tests."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from behave import given, then, when

from features.steps.shared import run_cli
from kanbus.ids import format_issue_key
from kanbus.migration import migrate_from_beads


def _fixture_beads_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "fixtures"
        / "beads_repo"
        / ".beads"
    )


@given("a migrated Kanbus repository from the Beads fixture")
def given_migrated_kanbus_repo(context: object) -> None:
    temp_dir = Path(tempfile.mkdtemp())
    repo_path = temp_dir
    beads_dir = repo_path / ".beads"
    beads_dir.mkdir(parents=True, exist_ok=True)
    fixture = _fixture_beads_dir()
    shutil.copy(fixture / "issues.jsonl", beads_dir / "issues.jsonl")
    shutil.copy(fixture / "metadata.json", beads_dir / "metadata.json")
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    migrate_from_beads(repo_path)
    context.working_directory = repo_path
    context.before_ids = set()
    context.last_kanbus_id = None


@when('I run "kanbus create Native deletable --type epic"')
def when_run_create_native_deletable(context: object) -> None:
    run_cli(context, "kanbus create Native deletable --type epic")
    given_record_new_kanbus_id(context)


@given("I record existing Kanbus issue ids")
def given_record_existing_ids(context: object) -> None:
    project_dir = Path(context.working_directory) / "project" / "issues"
    context.before_ids = {path.stem for path in project_dir.glob("*.json")}


@then('stdout should match pattern "{pattern}"')
def then_stdout_matches_pattern(context: object, pattern: str) -> None:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert re.search(
        pattern, cleaned, flags=re.IGNORECASE
    ), f"pattern {pattern} not found in {cleaned!r}"


@then('beads issues.jsonl should contain an id matching "{pattern}"')
def then_beads_jsonl_contains_pattern(context: object, pattern: str) -> None:
    issues_path = Path(context.working_directory) / ".beads" / "issues.jsonl"
    text = issues_path.read_text(encoding="utf-8")
    ids = []
    for line in text.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        ids.append(record.get("id", ""))
    regex = re.compile(pattern)
    assert any(regex.match(value) for value in ids), f"no id matching {pattern}"


@then('the last Kanbus issue id should match "{pattern}"')
def then_last_kanbus_id_matches(context: object, pattern: str) -> None:
    project_dir = Path(context.working_directory) / "project" / "issues"
    current_ids = {path.stem for path in project_dir.glob("*.json")}
    new_ids = current_ids - getattr(context, "before_ids", set())
    assert new_ids, "no new issue created"
    assert len(new_ids) == 1, f"expected one new id, found {len(new_ids)}"
    identifier = next(iter(new_ids))
    regex = re.compile(pattern)
    assert regex.match(identifier), f"{identifier} does not match {pattern}"
    context.last_kanbus_id = identifier


@given("I record the new Kanbus issue id")
def given_record_new_kanbus_id(context: object) -> None:
    project_dir = Path(context.working_directory) / "project" / "issues"
    current_ids = {path.stem for path in project_dir.glob("*.json")}
    before = getattr(context, "before_ids", set())
    new_ids = current_ids - before
    assert new_ids, "no new issue created"
    assert len(new_ids) == 1, f"expected one new id, found {len(new_ids)}"
    context.last_kanbus_id = next(iter(new_ids))
    context.before_ids = current_ids


@then("the last Kanbus issue id should be recorded")
def then_last_kanbus_id_recorded(context: object) -> None:
    assert getattr(context, "last_kanbus_id", None), "no Kanbus issue id recorded"


@then("the recorded Kanbus issue id should appear in the Kanbus list output")
def then_recorded_id_in_list_output(context: object) -> None:
    identifier = getattr(context, "last_kanbus_id", None)
    assert identifier, "no Kanbus issue id recorded"
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    display_key = format_issue_key(identifier, project_context=True)
    assert display_key in result.stdout, "recorded id not found in Kanbus list output"


@then("the recorded Kanbus issue id should not appear in the Kanbus list output")
def then_recorded_id_not_in_list_output(context: object) -> None:
    identifier = getattr(context, "last_kanbus_id", None)
    assert identifier, "no Kanbus issue id recorded"
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    display_key = format_issue_key(identifier, project_context=True)
    assert (
        display_key not in result.stdout
    ), "recorded id unexpectedly present in Kanbus list output"


@when("I delete the recorded Kanbus issue")
def when_delete_recorded_kanbus_issue(context: object) -> None:
    identifier = getattr(context, "last_kanbus_id", None)
    assert identifier, "no Kanbus issue id recorded"
    run_cli(context, f"kanbus delete {identifier}")


@when("I create a native task under the recorded Kanbus epic")
def when_create_native_task_under_recorded_epic(context: object) -> None:
    parent_id = getattr(context, "last_kanbus_id", None)
    assert parent_id, "no recorded epic id"
    run_cli(
        context,
        f"kanbus create Native task --parent {parent_id}",
    )
