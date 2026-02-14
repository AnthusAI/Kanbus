"""Behave steps for compatibility mode."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import yaml
from behave import given, then, when

from features.steps.shared import ensure_git_repository, run_cli
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


@when('I run "kanbus --beads list"')
def when_run_list_beads(context: object) -> None:
    run_cli(context, "kanbus --beads list")


@when('I run "kanbus --beads list --no-local"')
def when_run_list_beads_no_local(context: object) -> None:
    run_cli(context, "kanbus --beads list --no-local")


@when('I run "kanbus --beads ready"')
def when_run_ready_beads(context: object) -> None:
    run_cli(context, "kanbus --beads ready")


@when('I run "kanbus --beads ready --no-local"')
def when_run_ready_beads_no_local(context: object) -> None:
    run_cli(context, "kanbus --beads ready --no-local")


@when('I run "kanbus --beads show {identifier}"')
def when_run_show_beads(context: object, identifier: str) -> None:
    run_cli(context, f"kanbus --beads show {identifier}")


@when('I run "kanbus --beads create New beads child --parent bdx-epic"')
def when_run_create_beads_child(context: object) -> None:
    run_cli(context, "kanbus --beads create New beads child --parent bdx-epic")


@then('beads issues.jsonl should contain "{identifier}"')
def then_beads_jsonl_contains(context: object, identifier: str) -> None:
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    contents = issues_path.read_text(encoding="utf-8")
    assert identifier in contents


@when('I run "kanbus --beads create Local beads issue --local"')
def when_run_create_beads_local(context: object) -> None:
    run_cli(context, "kanbus --beads create Local beads issue --local")


@when('I run "kanbus --beads create Missing beads issue"')
def when_run_create_beads_missing(context: object) -> None:
    run_cli(context, "kanbus --beads create Missing beads issue")


@when('I run "kanbus --beads create Missing issues file"')
def when_run_create_beads_missing_issues(context: object) -> None:
    run_cli(context, "kanbus --beads create Missing issues file")


@when('I run "kanbus --beads create Empty beads file"')
def when_run_create_beads_empty(context: object) -> None:
    run_cli(context, "kanbus --beads create Empty beads file")


@when('I run "kanbus --beads create Orphan beads issue --parent bdx-missing"')
def when_run_create_beads_orphan(context: object) -> None:
    run_cli(context, "kanbus --beads create Orphan beads issue --parent bdx-missing")


@when('I run "kanbus --beads create Assigned beads issue --assignee dev@example.com"')
def when_run_create_beads_assigned(context: object) -> None:
    run_cli(
        context,
        "kanbus --beads create Assigned beads issue --assignee dev@example.com",
    )


@when('I run "kanbus --beads create Described beads issue --description Details"')
def when_run_create_beads_description(context: object) -> None:
    run_cli(
        context, "kanbus --beads create Described beads issue --description Details"
    )


@when('I run "kanbus --beads create Beads with blanks"')
def when_run_create_beads_blank(context: object) -> None:
    run_cli(context, "kanbus --beads create Beads with blanks")


@when('I run "kanbus --beads create Invalid prefix"')
def when_run_create_beads_invalid_prefix(context: object) -> None:
    run_cli(context, "kanbus --beads create Invalid prefix")


@when('I run "kanbus --beads create Colliding beads issue"')
def when_run_create_beads_collision(context: object) -> None:
    run_cli(context, "kanbus --beads create Colliding beads issue")


@when('I run "kanbus --beads create Next child --parent bdx-epic"')
def when_run_create_beads_next_child(context: object) -> None:
    run_cli(context, "kanbus --beads create Next child --parent bdx-epic")


@when('I run "kanbus --beads update bdx-missing --status closed"')
def when_run_update_beads_missing(context: object) -> None:
    run_cli(context, "kanbus --beads update bdx-missing --status closed")


@when('I run "kanbus --beads update bdx-epic --status closed"')
def when_run_update_beads_success(context: object) -> None:
    run_cli(context, "kanbus --beads update bdx-epic --status closed")


@when('I run "kanbus --beads delete bdx-missing"')
def when_run_delete_beads_missing(context: object) -> None:
    run_cli(context, "kanbus --beads delete bdx-missing")


@when('I run "kanbus --beads delete bdx-task"')
def when_run_delete_beads_success(context: object) -> None:
    run_cli(context, "kanbus --beads delete bdx-task")


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
    assert identifier not in contents


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
