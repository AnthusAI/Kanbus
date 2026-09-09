"""Behave steps for standup time window scenarios."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml
from behave import given, then, when

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.standup import load_standup_configuration, resolve_standup_profile
from kanbus.standup_window import (
    StandupWindowOverrides,
    parse_standup_lookback_hours,
    resolve_standup_window_settings,
)

from features.steps.shared import (
    load_project_directory,
    read_issue_file,
    write_issue_file,
)


def _load_config_payload(context: object) -> dict:
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = dict(DEFAULT_CONFIGURATION)
    return payload


def _write_config_payload(context: object, payload: dict) -> None:
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _standup_timezone(context: object) -> ZoneInfo:
    timezone_name = getattr(context, "standup_timezone_name", None)
    if timezone_name:
        return ZoneInfo(timezone_name)
    configuration = load_standup_configuration(Path(context.working_directory))
    settings = resolve_standup_window_settings(
        configuration,
        MEETING_SCRIPT_PROFILE,
        None,
    )
    return settings.timezone


MEETING_SCRIPT_PROFILE = "meeting-script"


def _report_time(context: object) -> datetime:
    override = getattr(context, "standup_report_time", None)
    if override is not None:
        return override
    return datetime.now(timezone.utc)


def _clear_report_time() -> None:
    os.environ.pop("KANBUS_STANDUP_REPORT_TIME", None)


def _set_report_time(context: object, report_time: datetime) -> None:
    context.standup_report_time = report_time
    os.environ["KANBUS_STANDUP_REPORT_TIME"] = report_time.isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _ensure_live_report_time(context: object) -> None:
    if getattr(context, "standup_report_time", None) is None:
        _clear_report_time()


def _resolved_window_settings(
    context: object,
    profile: Optional[str] = None,
    apply_profile_defaults: bool = True,
) -> object:
    root = Path(context.working_directory)
    configuration = load_standup_configuration(root)
    resolved_profile = None
    if apply_profile_defaults:
        resolved_profile = resolve_standup_profile(
            profile or getattr(context, "standup_profile", None)
        )
    overrides = getattr(context, "standup_window_overrides", StandupWindowOverrides())
    return resolve_standup_window_settings(configuration, resolved_profile, overrides)


@given('standup window is "{window}"')
def given_standup_window(context: object, window: str) -> None:
    """Set standup window in project configuration."""
    _ensure_live_report_time(context)
    payload = _load_config_payload(context)
    payload.setdefault("standup", {})
    payload["standup"]["window"] = window
    _write_config_payload(context, payload)


@given('standup lookback is "{lookback}"')
def given_standup_lookback(context: object, lookback: str) -> None:
    """Set standup lookback in project configuration."""
    payload = _load_config_payload(context)
    payload.setdefault("standup", {})
    payload["standup"]["lookback"] = lookback
    _write_config_payload(context, payload)


@given("standup skip_weekends is {enabled}")
def given_standup_skip_weekends(context: object, enabled: str) -> None:
    """Set standup skip_weekends in project configuration."""
    payload = _load_config_payload(context)
    payload.setdefault("standup", {})
    payload["standup"]["skip_weekends"] = enabled.lower() == "true"
    _write_config_payload(context, payload)


@given('standup timezone is "{timezone_name}"')
def given_standup_timezone(context: object, timezone_name: str) -> None:
    """Set standup timezone in project configuration."""
    context.standup_timezone_name = timezone_name
    payload = _load_config_payload(context)
    payload.setdefault("standup", {})
    payload["standup"]["timezone"] = timezone_name
    _write_config_payload(context, payload)


@given("the report time is fixed")
def given_report_time_is_fixed(context: object) -> None:
    """Pin standup report time for deterministic bucket tests."""
    _set_report_time(context, datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc))


@given("the report time is {weekday} {hour:d}:00 in standup timezone")
def given_report_time_in_standup_timezone(
    context: object, weekday: str, hour: int
) -> None:
    """Pin report time to a weekday and hour in standup timezone."""
    weekday_map = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }
    target_weekday = weekday_map[weekday]
    timezone_info = _standup_timezone(context)
    base = datetime(2026, 3, 9, hour, 0, tzinfo=timezone_info)
    while base.weekday() != target_weekday:
        base += timedelta(days=1)
    _set_report_time(context, base.astimezone(timezone.utc))


@given('issue "{identifier}" has closed_at {hours:d} hours before report time')
def given_issue_closed_at_hours_before_report(
    context: object, identifier: str, hours: int
) -> None:
    """Set issue closed_at relative to the pinned report time."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    closed_at = _report_time(context) - timedelta(hours=hours)
    issue = issue.model_copy(update={"closed_at": closed_at, "status": "closed"})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" closed on the previous calendar day in standup timezone')
def given_issue_closed_previous_calendar_day(context: object, identifier: str) -> None:
    """Set issue closed_at on the previous calendar day in standup timezone."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    timezone_info = _standup_timezone(context)
    report_local = _report_time(context).astimezone(timezone_info)
    previous_day = report_local.date() - timedelta(days=1)
    closed_at = datetime(
        previous_day.year,
        previous_day.month,
        previous_day.day,
        16,
        0,
        tzinfo=timezone_info,
    ).astimezone(timezone.utc)
    issue = issue.model_copy(update={"closed_at": closed_at, "status": "closed"})
    write_issue_file(project_dir, issue)


@given(
    'issue "{identifier}" closed two calendar days before report day in standup timezone'
)
def given_issue_closed_two_calendar_days_before(
    context: object, identifier: str
) -> None:
    """Set issue closed_at two calendar days before the report day."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    timezone_info = _standup_timezone(context)
    report_local = _report_time(context).astimezone(timezone_info)
    closed_day = report_local.date() - timedelta(days=2)
    closed_at = datetime(
        closed_day.year,
        closed_day.month,
        closed_day.day,
        16,
        0,
        tzinfo=timezone_info,
    ).astimezone(timezone.utc)
    issue = issue.model_copy(update={"closed_at": closed_at, "status": "closed"})
    write_issue_file(project_dir, issue)


@given(
    'issue "{identifier}" closed on {weekday} before this Monday in standup timezone'
)
def given_issue_closed_on_weekday_before_monday(
    context: object, identifier: str, weekday: str
) -> None:
    """Set issue closed_at on a weekday before the report Monday."""
    weekday_map = {
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
        "Thursday": 3,
    }
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    timezone_info = _standup_timezone(context)
    report_local = _report_time(context).astimezone(timezone_info)
    days_back = (report_local.weekday() - weekday_map[weekday]) % 7
    if days_back == 0:
        days_back = 7
    closed_day = report_local.date() - timedelta(days=days_back)
    closed_at = datetime(
        closed_day.year,
        closed_day.month,
        closed_day.day,
        16,
        0,
        tzinfo=timezone_info,
    ).astimezone(timezone.utc)
    issue = issue.model_copy(update={"closed_at": closed_at, "status": "closed"})
    write_issue_file(project_dir, issue)


@given('the Kanbus configuration sets standup window to "{window}"')
def given_config_standup_window(context: object, window: str) -> None:
    """Set standup window in Kanbus configuration."""
    given_standup_window(context, window)


@given('the Kanbus configuration sets standup lookback to "{lookback}"')
def given_config_standup_lookback(context: object, lookback: str) -> None:
    """Set standup lookback in Kanbus configuration."""
    given_standup_lookback(context, lookback)


@given("the Kanbus configuration sets standup skip_weekends to {enabled}")
def given_config_standup_skip_weekends(context: object, enabled: str) -> None:
    """Set standup skip_weekends in Kanbus configuration."""
    given_standup_skip_weekends(context, enabled)


@when("I inspect standup window configuration")
def when_inspect_standup_window_configuration(context: object) -> None:
    """Resolve global standup window settings for assertions."""
    context.standup_window_settings = _resolved_window_settings(
        context,
        apply_profile_defaults=False,
    )


@when('I resolve standup window settings for profile "{profile}"')
def when_resolve_standup_window_settings(context: object, profile: str) -> None:
    """Resolve standup window settings for a profile."""
    context.standup_profile = profile
    context.standup_window_settings = _resolved_window_settings(context, profile)


@when("I resolve standup lookback duration")
def when_resolve_standup_lookback_duration(context: object) -> None:
    """Resolve lookback hours from configured lookback string."""
    payload = _load_config_payload(context)
    lookback = payload.get("standup", {}).get("lookback", "24h")
    context.standup_lookback_hours = parse_standup_lookback_hours(lookback)


@when("I resolve standup window settings in both runtimes")
def when_resolve_standup_window_settings_both_runtimes(context: object) -> None:
    """Resolve standup window settings in Python and Rust."""
    root = Path(context.working_directory)
    configuration = load_standup_configuration(root)
    overrides = getattr(context, "standup_window_overrides", StandupWindowOverrides())
    python_settings = resolve_standup_window_settings(configuration, None, overrides)
    context.python_window_settings = python_settings

    probe_binary = (
        Path(__file__).resolve().parents[3]
        / "rust"
        / "target"
        / "release"
        / "standup_window_probe"
    )
    if not probe_binary.is_file():
        build_result = subprocess.run(
            ["cargo", "build", "--quiet", "--bin", "standup_window_probe"],
            cwd=probe_binary.parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        if build_result.returncode != 0:
            raise AssertionError(build_result.stderr or build_result.stdout)
    result = subprocess.run(
        [str(probe_binary), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    context.rust_window_settings = json.loads(result.stdout)


@then('standup window should be "{window}"')
def then_standup_window_should_be(context: object, window: str) -> None:
    """Assert resolved standup window mode."""
    settings = context.standup_window_settings
    assert settings.window == window


@then('standup lookback should be "{lookback}"')
def then_standup_lookback_should_be(context: object, lookback: str) -> None:
    """Assert resolved standup lookback string."""
    settings = context.standup_window_settings
    assert settings.lookback == lookback


@then("standup skip_weekends should be {enabled}")
def then_standup_skip_weekends_should_be(context: object, enabled: str) -> None:
    """Assert resolved standup skip_weekends flag."""
    expected = enabled.lower() == "true"
    settings = context.standup_window_settings
    assert settings.skip_weekends is expected


@then("standup lookback hours should be {hours:d}")
def then_standup_lookback_hours_should_be(context: object, hours: int) -> None:
    """Assert resolved lookback hours."""
    assert context.standup_lookback_hours == hours


@then('Python and Rust should agree on window "{window}"')
def then_python_rust_agree_on_window(context: object, window: str) -> None:
    """Assert Python and Rust agree on window mode."""
    assert context.python_window_settings.window == window
    assert context.rust_window_settings["window"] == window


@then("Python and Rust should agree on lookback hours {hours:d}")
def then_python_rust_agree_on_lookback_hours(context: object, hours: int) -> None:
    """Assert Python and Rust agree on lookback hours."""
    assert context.python_window_settings.lookback_hours == hours
    assert context.rust_window_settings["lookback_hours"] == hours


@then('the response should accept fields "{fields}"')
def then_response_accepts_fields(context: object, fields: str) -> None:
    """Assert console API accepts standup window request fields."""
    from kanbus.console_standup import StandupGenerateRequest

    payload = getattr(context, "last_post_json", {})
    accepted = StandupGenerateRequest.model_validate(payload)
    for field_name in (item.strip() for item in fields.split(",")):
        normalized = field_name.replace("and ", "").strip().strip('"')
        assert hasattr(accepted, normalized), f"missing accepted field: {normalized}"

    port = getattr(context, "console_server_port", None)
    if port is None:
        return
    url = f"http://127.0.0.1:{port}/api/standup"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        if "unknown field" in body.lower() or "unexpected field" in body.lower():
            raise AssertionError(
                f"standup API rejected fields: {error.code} {body}"
            ) from error


@when('I POST "{path}" with JSON:')
def when_post_with_json(context: object, path: str) -> None:
    """Store JSON payload for a console API POST request."""
    context.last_post_path = path
    context.last_post_json = json.loads(context.text)


@then('command help should mention "{flag}"')
def then_command_help_should_mention(context: object, flag: str) -> None:
    """Assert CLI help mentions a flag."""
    stdout = context.result.stdout
    assert flag in stdout
