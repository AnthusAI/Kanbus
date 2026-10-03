"""Steps for dynamic short ID formatting specs."""

from __future__ import annotations

import json
from pathlib import Path

from behave import given, then

from features.steps.shared import load_project_directory, write_issue_file
from kanbus.ids import matches_issue_identifier
from kanbus.models import IssueData


def _short_id_fixtures() -> dict:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "fixtures"
        / "short_id_fixtures.json"
    )
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _build_issue_with_title(identifier: str, title: str) -> IssueData:
    from datetime import datetime, timezone

    return IssueData(
        id=identifier,
        title=title,
        description="",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        closed_at=None,
        custom={},
    )


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@given('a project issue "{identifier}" exists with title "{title}"')
def given_project_issue_with_title(
    context: object, identifier: str, title: str
) -> None:
    project_dir = load_project_directory(context)
    write_issue_file(project_dir, _build_issue_with_title(identifier, title))


@given("the Kanbus configuration sets short_id_length to {length:d}")
def given_configuration_short_id_length(context: object, length: int) -> None:
    import yaml

    working_directory = Path(context.working_directory)
    config_path = working_directory / ".kanbus.yml"
    configuration = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    configuration["short_id_length"] = length
    config_path.write_text(
        yaml.safe_dump(configuration, sort_keys=False), encoding="utf-8"
    )


@given("project issues exist from the short ID uniqueness fixture")
def given_fixture_issues_exist(context: object) -> None:
    project_dir = load_project_directory(context)
    fixtures = _short_id_fixtures()
    for identifier in fixtures["uniqueness_universe"]:
        write_issue_file(
            project_dir, _build_issue_with_title(identifier, "Fixture issue")
        )


@then('the list should show short ID "{short_id}" for issue "{identifier}"')
def then_list_shows_short_id(context: object, short_id: str, identifier: str) -> None:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    ansi_free = _strip_ansi(result.stdout)
    assert (
        short_id in ansi_free
    ), f"list output does not contain {short_id} for {identifier}:\n{ansi_free}"
    assert (
        identifier not in ansi_free
    ), f"list output unexpectedly contains the full id {identifier}"


@then("no two displayed list IDs should collide")
def then_no_displayed_id_collides(context: object) -> None:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    ansi_free = _strip_ansi(result.stdout)
    seen = set()
    for id_field in _displayed_id_fields(ansi_free):
        assert id_field not in seen, f"displayed id {id_field} appears more than once"
        seen.add(id_field)


@then("no displayed short ID should be ambiguous in the visible set")
def then_no_displayed_id_ambiguous(context: object) -> None:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    project_dir = load_project_directory(context)
    full_ids = [path.stem for path in (project_dir / "issues").glob("*.json")]
    ansi_free = _strip_ansi(result.stdout)
    for id_field in _displayed_id_fields(ansi_free):
        matches = sum(
            1 for full in full_ids if matches_issue_identifier(id_field, full)
        )
        assert matches == 1, f"displayed id {id_field} matches {matches} issues"


def _displayed_id_fields(ansi_free: str) -> list[str]:
    fields = []
    for line in ansi_free.splitlines():
        tokens = line.split()
        if len(tokens) < 2:
            continue
        id_field = tokens[1]
        if not id_field or id_field == "-":
            continue
        fields.append(id_field)
    return fields


@then("displayed list IDs should use hash width {width:d}")
def then_displayed_ids_use_hash_width(context: object, width: int) -> None:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    ansi_free = _strip_ansi(result.stdout)
    checked = 0
    for id_field in _displayed_id_fields(ansi_free):
        hash_part = id_field.rsplit("-", 1)[-1]
        assert (
            len(hash_part) == width
        ), f"displayed id {id_field} does not use hash width {width}"
        checked += 1
    assert checked > 0, "no displayed list IDs found in output"


@then('the ambiguity JSON should list full IDs "{expected}"')
def then_ambiguity_json_lists_ids(context: object, expected: str) -> None:
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    payload = json.loads(result.stdout)
    assert payload["error"] == "ambiguous_identifier"
    actual_ids = [entry["id"] for entry in payload["matches"]]
    assert actual_ids == expected.split(", ")
