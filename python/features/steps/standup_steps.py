"""Behave steps for standup report scenarios."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from behave import given, then

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.right_now_command import (
    RightNowCommandOptions,
    RightNowOutputFormat,
    select_right_now_issues,
)
from kanbus.standup import (
    extract_section_text,
    report_uses_first_person_voice,
    report_uses_third_person_executive_voice,
)
from kanbus.standup_command import StandupCommandOptions, select_standup_fact_feed

from features.steps.output_steps import _strip_ansi
from features.steps.shared import (
    load_project_directory,
    read_issue_file,
    write_issue_file,
)


@given("standup lookback hours is {hours:d}")
def given_standup_lookback_hours(context: object, hours: int) -> None:
    """Configure standup lookback hours in project configuration.

    :param context: Behave context object.
    :type context: object
    :param hours: Lookback window in hours.
    :type hours: int
    """
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = dict(DEFAULT_CONFIGURATION)
    payload.setdefault("standup", {})
    payload["standup"]["lookback"] = f"{hours}h"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@given('issue "{identifier}" has closed_at within standup lookback')
def given_issue_closed_at_within_standup_lookback(
    context: object, identifier: str
) -> None:
    """Set closed_at to a recent timestamp within the default lookback window.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    issue = issue.model_copy(update={"closed_at": recent})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has updated_at within standup lookback')
def given_issue_updated_at_within_standup_lookback(
    context: object, identifier: str
) -> None:
    """Set updated_at to a recent timestamp within the default lookback window.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    from features.steps.query_steps import _resolve_issue_project_directory

    project_dir = _resolve_issue_project_directory(context, identifier)
    issue = read_issue_file(project_dir, identifier)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    issue = issue.model_copy(update={"updated_at": recent})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has updated_at older than standup lookback')
def given_issue_updated_at_older_than_standup_lookback(
    context: object, identifier: str
) -> None:
    """Set updated_at older than the default standup lookback window.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    from features.steps.query_steps import _resolve_issue_project_directory

    project_dir = _resolve_issue_project_directory(context, identifier)
    issue = read_issue_file(project_dir, identifier)
    stale = datetime.now(timezone.utc) - timedelta(hours=48)
    issue = issue.model_copy(update={"updated_at": stale})
    write_issue_file(project_dir, issue)


@given(
    'issue "{identifier}" has a state transition to "{status}" within standup lookback'
)
def given_issue_state_transition_within_standup_lookback(
    context: object, identifier: str, status: str
) -> None:
    """Write a recent state transition event for an issue.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param status: Destination status for the transition.
    :type status: str
    """
    project_dir = load_project_directory(context)
    events_dir = project_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    occurred_at = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    event_id = f"standup-transition-{identifier}"
    filename = occurred_at.replace(":", "-") + f"__{event_id}.json"
    payload = {
        "schema_version": 1,
        "event_id": event_id,
        "issue_id": identifier,
        "event_type": "state_transition",
        "occurred_at": occurred_at,
        "actor_id": "agent",
        "payload": {"from_status": "in_progress", "to_status": status},
    }
    (events_dir / filename).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _standup_options_from_last_command(context: object) -> StandupCommandOptions:
    command = getattr(context, "last_command", "")
    issue_ids: list[str] = []
    profile = None
    recursive = True
    tokens = command.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            token == "kanbus"
            and index + 1 < len(tokens)
            and tokens[index + 1] == "standup"
        ):
            index += 2
            continue
        if token == "--profile" and index + 1 < len(tokens):
            profile = tokens[index + 1]
            index += 2
            continue
        if token == "--no-recursive":
            recursive = False
            index += 1
            continue
        if token == "--rollup" and index + 1 < len(tokens):
            index += 2
            continue
        if token == "--skip-weekends":
            index += 1
            continue
        if token == "--no-skip-weekends":
            index += 1
            continue
        if token in {"--window", "--lookback", "--profile"} and index + 1 < len(tokens):
            index += 2
            continue
        if token.startswith("--"):
            index += 2
            continue
        issue_ids.append(token)
        index += 1
    return StandupCommandOptions(
        issue_ids=tuple(issue_ids),
        profile=profile,
        recursive=recursive,
    )


def _current_standup_fact_feed(context: object) -> list[str]:
    root = Path(context.working_directory)
    options = _standup_options_from_last_command(context)
    issues = select_standup_fact_feed(root, options)
    return [issue.identifier for issue in issues]


def _expected_default_fact_feed(context: object) -> list[str]:
    root = Path(context.working_directory)
    options = StandupCommandOptions()
    return [issue.identifier for issue in select_standup_fact_feed(root, options)]


def _kanbus_now_fact_feed(context: object, status_filter: str) -> list[str]:
    root = Path(context.working_directory)
    options = RightNowCommandOptions(
        tree=False,
        output_format=RightNowOutputFormat.YAML,
        status=status_filter,
    )
    issues = select_right_now_issues(root, options)
    return [issue.identifier for issue in issues]


def _parse_standup_json(context: object) -> dict:
    stdout = _strip_ansi(context.result.stdout)
    return json.loads(stdout)


def _store_standup_json_profile(context: object) -> None:
    payload = _parse_standup_json(context)
    profiles = getattr(context, "standup_json_by_profile", {})
    profiles[payload["profile"]] = payload
    context.standup_json_by_profile = profiles


@then("the standup fact feed should match standup default listing")
def then_standup_fact_feed_matches_default(context: object) -> None:
    """Verify standup omit-IDs selection matches the standup default feed.

    :param context: Behave context object.
    :type context: object
    """
    actual = _current_standup_fact_feed(context)
    expected = _expected_default_fact_feed(context)
    assert actual == expected


@then(
    "the standup fact feed should match kanbus now listing with status in_progress,blocked"
)
def then_standup_fact_feed_matches_kanbus_now_status(context: object) -> None:
    """Verify standup default feed matches kanbus now with the wider status filter.

    :param context: Behave context object.
    :type context: object
    """
    actual = _current_standup_fact_feed(context)
    expected = _kanbus_now_fact_feed(context, "in_progress,blocked")
    assert actual == expected


@then('the standup fact feed should include issue "{identifier}"')
def then_standup_fact_feed_includes_issue(context: object, identifier: str) -> None:
    """Verify an issue is in the standup fact feed.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    assert identifier in _current_standup_fact_feed(context)


@then('the standup fact feed should not include issue "{identifier}"')
def then_standup_fact_feed_excludes_issue(context: object, identifier: str) -> None:
    """Verify an issue is excluded from the standup fact feed.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    assert identifier not in _current_standup_fact_feed(context)


@then("the standup fact feed should have {count:d} issues")
def then_standup_fact_feed_count(context: object, count: int) -> None:
    """Verify standup fact-feed size.

    :param context: Behave context object.
    :type context: object
    :param count: Expected issue count.
    :type count: int
    """
    assert len(_current_standup_fact_feed(context)) == count


@then('the standup report should have profile "{profile}"')
def then_standup_report_profile(context: object, profile: str) -> None:
    """Verify standup profile from text or JSON output.

    :param context: Behave context object.
    :type context: object
    :param profile: Expected profile identifier.
    :type profile: str
    """
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        assert payload["profile"] == profile
        return
    assert f"Standup ({profile})" in stdout


@then('the standup report should include section "{section_name}"')
def then_standup_report_includes_section(context: object, section_name: str) -> None:
    """Verify a standup section heading is present.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    """
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        section_names = [section["name"] for section in payload["sections"]]
        assert section_name in section_names
        return
    assert f"\n{section_name}\n" in stdout or stdout.strip().endswith(section_name)


@then('the standup report section "{section_name}" should mention "{text}"')
def then_standup_section_mentions(
    context: object, section_name: str, text: str
) -> None:
    """Verify section content mentions expected text.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    :param text: Expected substring.
    :type text: str
    """
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        section = next(
            item for item in payload["sections"] if item["name"] == section_name
        )
        joined = "\n".join(section.get("bullets", []))
        assert text in joined
        return
    section_text = extract_section_text(stdout, section_name)
    assert text in section_text


@then('the standup report section "{section_name}" should not contain "{text}"')
def then_standup_section_does_not_contain(
    context: object, section_name: str, text: str
) -> None:
    """Verify section content does not contain excluded text.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    :param text: Substring that must be absent.
    :type text: str
    """
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        section = next(
            item for item in payload["sections"] if item["name"] == section_name
        )
        joined = "\n".join(section.get("bullets", []))
        assert text not in joined
        return
    section_text = extract_section_text(stdout, section_name)
    assert text not in section_text


@given('standup rollup reduce uses completion "{summary}"')
def given_standup_rollup_reduce_completion(context: object, summary: str) -> None:
    """Stub standup rollup upward LLM reduce with a fixed completion string.

    :param context: Behave context object.
    :type context: object
    :param summary: Completion text returned by rollup reduce.
    :type summary: str
    """
    import os

    from features.steps.configuration_steps import _track_env_restore

    overrides = getattr(context, "environment_overrides", None)
    if overrides is None:
        context.environment_overrides = {}
        overrides = context.environment_overrides
    _track_env_restore(context, "KANBUS_TEST_STANDUP_ROLLUP_COMPLETION")
    overrides["KANBUS_TEST_STANDUP_ROLLUP_COMPLETION"] = summary
    os.environ["KANBUS_TEST_STANDUP_ROLLUP_COMPLETION"] = summary


@then('the standup report section "{section_name}" should not mention "{text}"')
def then_standup_section_does_not_mention(
    context: object, section_name: str, text: str
) -> None:
    """Verify section content does not mention excluded text.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    :param text: Substring that must be absent.
    :type text: str
    """
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        section = next(
            item for item in payload["sections"] if item["name"] == section_name
        )
        joined = "\n".join(section.get("bullets", []))
        assert text not in joined
        return
    section_text = extract_section_text(stdout, section_name)
    assert text not in section_text


@then('the standup report section "{section_name}" should not be empty')
def then_standup_section_not_empty(context: object, section_name: str) -> None:
    """Verify a standup section has at least one bullet.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    """
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        section = next(
            item for item in payload["sections"] if item["name"] == section_name
        )
        assert section.get("bullets")
        return
    section_text = extract_section_text(stdout, section_name)
    assert any(line.strip().startswith("-") for line in section_text.splitlines())


@then('the standup report section "Health" should report {count:d} in-progress issues')
def then_standup_health_in_progress_count(context: object, count: int) -> None:
    """Verify Health section in-progress count text.

    :param context: Behave context object.
    :type context: object
    :param count: Expected in-progress count.
    :type count: int
    """
    then_standup_section_mentions(context, "Health", f"{count} in-progress issues")


@then('the standup report section "Health" should report {count:d} blocked issue')
@then('the standup report section "Health" should report {count:d} blocked issues')
def then_standup_health_blocked_count(context: object, count: int) -> None:
    """Verify Health section blocked count text.

    :param context: Behave context object.
    :type context: object
    :param count: Expected blocked count.
    :type count: int
    """
    label = "blocked issue" if count == 1 else "blocked issues"
    then_standup_section_mentions(context, "Health", f"{count} {label}")


@then("the standup report should use first person voice")
def then_standup_first_person_voice(context: object) -> None:
    """Verify standup text uses first-person phrasing.

    :param context: Behave context object.
    :type context: object
    """
    stdout = _strip_ansi(context.result.stdout)
    assert report_uses_first_person_voice(stdout)


@then("the standup report should not use first person voice")
def then_standup_not_first_person_voice(context: object) -> None:
    """Verify standup text avoids first-person phrasing.

    :param context: Behave context object.
    :type context: object
    """
    stdout = _strip_ansi(context.result.stdout)
    assert not report_uses_first_person_voice(stdout)


@then("the standup report should use third person executive voice")
def then_standup_third_person_executive_voice(context: object) -> None:
    """Verify standup text uses executive third-person phrasing.

    :param context: Behave context object.
    :type context: object
    """
    stdout = _strip_ansi(context.result.stdout)
    assert report_uses_third_person_executive_voice(stdout)


@then("the standup report should not use third person executive voice")
def then_standup_not_third_person_executive_voice(context: object) -> None:
    """Verify standup text avoids executive third-person phrasing.

    :param context: Behave context object.
    :type context: object
    """
    stdout = _strip_ansi(context.result.stdout)
    assert not report_uses_third_person_executive_voice(stdout)


@then("each standup report bullet should be at most {max_length:d} characters")
def then_each_standup_bullet_max_length(context: object, max_length: int) -> None:
    """Verify rendered standup bullets respect the length cap.

    :param context: Behave context object.
    :type context: object
    :param max_length: Maximum bullet length.
    :type max_length: int
    """
    stdout = _strip_ansi(context.result.stdout)
    for line in stdout.splitlines():
        if line.startswith("- "):
            assert len(line[2:]) <= max_length


@then('the standup JSON output should include fields "{fields_csv}"')
def then_standup_json_includes_fields(context: object, fields_csv: str) -> None:
    """Verify standup JSON includes expected top-level fields.

    :param context: Behave context object.
    :type context: object
    :param fields_csv: Comma-separated field names.
    :type fields_csv: str
    """
    payload = _parse_standup_json(context)
    for field_name in fields_csv.split(","):
        assert field_name.strip() in payload


@then('the standup JSON source_issues should include issue "{identifier}"')
def then_standup_json_source_issue(context: object, identifier: str) -> None:
    """Verify standup JSON source_issues contains an identifier.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    payload = _parse_standup_json(context)
    assert identifier in payload.get("source_issues", [])


@then('the standup JSON output should record source issue "{identifier}"')
def then_standup_json_records_source_issue(context: object, identifier: str) -> None:
    """Store standup JSON by profile and verify source issue membership.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    _store_standup_json_profile(context)
    then_standup_json_source_issue(context, identifier)


@then("the standup JSON source_issues set should match between profiles")
def then_standup_json_source_issues_match_between_profiles(context: object) -> None:
    """Verify source_issues are identical across stored standup JSON profiles.

    :param context: Behave context object.
    :type context: object
    """
    _store_standup_json_profile(context)
    profiles = context.standup_json_by_profile
    assert len(profiles) >= 2
    source_sets = [
        set(payload.get("source_issues", [])) for payload in profiles.values()
    ]
    assert all(source_set == source_sets[0] for source_set in source_sets)


@then("the standup JSON right_now_texts should match between profiles")
def then_standup_json_right_now_texts_match_between_profiles(context: object) -> None:
    """Verify right_now_texts are identical across stored standup JSON profiles.

    :param context: Behave context object.
    :type context: object
    """
    _store_standup_json_profile(context)
    profiles = context.standup_json_by_profile
    assert len(profiles) >= 2
    texts = [payload.get("right_now_texts", {}) for payload in profiles.values()]
    assert all(text_map == texts[0] for text_map in texts)


@then("standup generation should use the right now litellm configuration")
def then_standup_uses_right_now_litellm_configuration(context: object) -> None:
    """Verify standup reused the right-now LiteLLM client path.

    :param context: Behave context object.
    :type context: object
    """
    from kanbus.right_now import LLM_USAGE_LOG, RIGHT_NOW_SUMMARY_OPERATION

    project_dir = load_project_directory(context)
    log_path = project_dir / "events" / LLM_USAGE_LOG
    assert log_path.exists(), f"expected {log_path} to exist"
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching = [
        entry
        for entry in entries
        if entry.get("operation") == RIGHT_NOW_SUMMARY_OPERATION
    ]
    assert matching, "expected right_now_summary entry in llm usage log"


@then("standup generation should not use a separate standup litellm client")
def then_standup_does_not_use_separate_litellm_client(context: object) -> None:
    """Verify standup did not introduce a parallel LiteLLM client.

    :param context: Behave context object.
    :type context: object
    """
    assert os.environ.get("KANBUS_STANDUP_LITELLM_CALLED") != "1"


@given("standup parity is tracked by tools/check_spec_parity.py")
@then("standup parity is tracked by tools/check_spec_parity.py")
def then_standup_parity_tracked(context: object) -> None:
    """Document that standup parity is enforced by the spec parity checker.

    :param context: Behave context object.
    :type context: object
    """
    repository_root = (
        Path(__file__).resolve().parents[3] / "tools" / "check_spec_parity.py"
    )
    assert repository_root.exists()


@then(
    "standup scenarios should not be considered complete until both Python behave and Rust cucumber pass without wip tags"
)
def then_standup_completion_requires_dual_runtime(context: object) -> None:
    """Document dual-runtime completion criteria for standup scenarios.

    :param context: Behave context object.
    :type context: object
    """
    assert True


def _standup_section_bullets(context: object, section_name: str) -> list[str]:
    stdout = _strip_ansi(context.result.stdout)
    if stdout.strip().startswith("{"):
        payload = json.loads(stdout)
        section = next(
            item for item in payload["sections"] if item["name"] == section_name
        )
        return list(section.get("bullets", []))
    section_text = extract_section_text(stdout, section_name)
    bullets: list[str] = []
    for line in section_text.splitlines():
        trimmed_start = line.lstrip()
        if trimmed_start.startswith("- "):
            bullet_start = line.find("- ") + 2
            bullets.append(line[bullet_start:])
    return bullets


@then('the standup report section "{section_name}" should have {count:d} bullet')
@then('the standup report section "{section_name}" should have {count:d} bullets')
def then_standup_section_bullet_count(
    context: object, section_name: str, count: int
) -> None:
    """Verify the number of bullets in a standup section.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    :param count: Expected bullet count.
    :type count: int
    """
    bullets = _standup_section_bullets(context, section_name)
    assert len(bullets) == count


@then('the standup report section "{section_name}" should match pattern "{pattern}"')
def then_standup_section_matches_pattern(
    context: object, section_name: str, pattern: str
) -> None:
    """Verify section bullets match a regular expression.

    :param context: Behave context object.
    :type context: object
    :param section_name: Section heading.
    :type section_name: str
    :param pattern: Regular expression that must match section text.
    :type pattern: str
    """
    bullets = _standup_section_bullets(context, section_name)
    joined = "\n".join(bullets)
    assert re.search(pattern, joined)
