"""Behave steps for console standup drawer scenarios."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from behave import given, then, when

from kanbus.models import IssueData
from kanbus.standup import (
    MEETING_SCRIPT_PROFILE,
    build_standup_report,
    collect_right_now_texts,
    format_standup_text,
    resolve_standup_profile,
)
from kanbus.standup_window import (
    DEFAULT_STANDUP_LOOKBACK,
    ROLLING_WINDOW,
    StandupWindowSettings,
)
from zoneinfo import ZoneInfo
from kanbus.standup_command import STANDUP_DEFAULT_STATUS_FILTER

from features.steps.console_ui_steps import (
    ConsoleIssue,
    ConsoleState,
    _console_app_root,
    _require_console_state,
)


@dataclass
class StandupPanelState:
    """Simulated standup drawer state for console UI scenarios."""

    is_open: bool = False
    profile: str = MEETING_SCRIPT_PROFILE
    is_generating: bool = False
    error: str | None = None
    report_text: str | None = None
    section_names: list[str] = field(default_factory=list)
    clipboard: str | None = None
    generation_should_fail: bool = False


def _ensure_standup_state(context: object) -> StandupPanelState:
    state = getattr(context, "console_standup_state", None)
    if state is None:
        state = StandupPanelState()
        context.console_standup_state = state
    return state


def _parse_console_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _standup_statuses() -> set[str]:
    return {status.strip() for status in STANDUP_DEFAULT_STATUS_FILTER.split(",")}


def _console_issue_to_issue_data(issue: ConsoleIssue) -> IssueData:
    timestamp = _parse_console_timestamp(issue.updated_at)
    return IssueData.model_validate(
        {
            "id": issue.identifier or issue.title,
            "title": issue.title,
            "description": "",
            "type": issue.issue_type,
            "status": issue.status,
            "priority": issue.priority,
            "assignee": issue.assignee,
            "creator": "agent",
            "parent": None,
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "closed_at": (
                _parse_console_timestamp(issue.closed_at) if issue.closed_at else None
            ),
            "right_now_summary": issue.right_now_summary,
            "right_now_updated_at": timestamp if issue.right_now_summary else None,
            "custom": {},
            "agent": None,
        }
    )


def _standup_fact_feed_issues(console_state: ConsoleState) -> list[IssueData]:
    allowed_statuses = _standup_statuses()
    issues = [
        _console_issue_to_issue_data(issue)
        for issue in console_state.issues
        if issue.status in allowed_statuses
    ]
    return sorted(
        issues,
        key=lambda issue: (
            issue.updated_at.isoformat() if issue.updated_at else "",
            issue.identifier,
        ),
        reverse=True,
    )


def _generate_from_console_state(
    console_state: ConsoleState,
    profile_name: str,
) -> tuple[str, list[str]]:
    profile = resolve_standup_profile(profile_name)
    issues = _standup_fact_feed_issues(console_state)
    right_now_texts = collect_right_now_texts(issues)
    window_settings = StandupWindowSettings(
        window=ROLLING_WINDOW,
        lookback=DEFAULT_STANDUP_LOOKBACK,
        lookback_hours=24,
        skip_weekends=False,
        timezone=ZoneInfo("UTC"),
    )
    report = build_standup_report(
        profile,
        issues,
        right_now_texts,
        {},
        datetime.now(timezone.utc),
        window_settings,
        False,
    )
    section_names = [section.name for section in report.sections]
    return format_standup_text(report), section_names


@given("standup generation is configured to fail")
def given_standup_generation_configured_to_fail(context: object) -> None:
    """Configure the simulated standup drawer to fail generation.

    :param context: Behave context object.
    :type context: object
    """
    _ensure_standup_state(context).generation_should_fail = True


@when("I open the standup drawer")
def when_open_standup_drawer(context: object) -> None:
    """Open the standup drawer from the Now panel.

    :param context: Behave context object.
    :type context: object
    """
    _ensure_standup_state(context).is_open = True


@when('I select the standup profile "{profile}"')
def when_select_standup_profile(context: object, profile: str) -> None:
    """Select a standup profile in the drawer.

    :param context: Behave context object.
    :type context: object
    :param profile: Standup profile identifier.
    :type profile: str
    """
    _ensure_standup_state(context).profile = profile


@when("I generate the standup report")
def when_generate_standup_report(context: object) -> None:
    """Generate a standup report in the simulated drawer.

    :param context: Behave context object.
    :type context: object
    """
    standup = _ensure_standup_state(context)
    console_state = _require_console_state(context)
    standup.is_generating = True
    standup.error = None
    standup.report_text = None
    standup.section_names = []
    if standup.generation_should_fail:
        standup.is_generating = False
        standup.error = "standup generation failed"
        return
    try:
        report_text, section_names = _generate_from_console_state(
            console_state,
            standup.profile,
        )
    except Exception as error:
        standup.is_generating = False
        standup.error = str(error)
        return
    standup.report_text = report_text
    standup.section_names = section_names
    standup.is_generating = False


@when("I copy the standup report")
def when_copy_standup_report(context: object) -> None:
    """Copy the generated standup report to the simulated clipboard.

    :param context: Behave context object.
    :type context: object
    """
    standup = _ensure_standup_state(context)
    if standup.report_text is None:
        raise AssertionError("no standup report to copy")
    standup.clipboard = standup.report_text


@when('I request a standup report from the console API with profile "{profile}"')
def when_request_standup_from_console_api(context: object, profile: str) -> None:
    """POST /api/standup against the running console server.

    :param context: Behave context object.
    :type context: object
    :param profile: Standup profile identifier.
    :type profile: str
    """
    port = getattr(context, "console_server_port", None)
    if port is None:
        raise AssertionError("console server is not running")
    url = f"http://127.0.0.1:{port}/api/standup"
    payload = json.dumps({"profile": profile}).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as error:
        body = error.read().decode()
        context.standup_api_status = error.code
        context.standup_api_response = json.loads(body) if body else {}
        return
    context.standup_api_status = 200
    context.standup_api_response = json.loads(body)


@then("the now standup button should be visible")
def then_now_standup_button_visible(context: object) -> None:
    """Verify the Now panel toolbar exposes the Standup button.

    :param context: Behave context object.
    :type context: object
    """
    state = _require_console_state(context)
    if state.panel_mode != "now":
        raise AssertionError("expected Now panel to be active")
    source = (
        _console_app_root() / "src" / "components" / "CurrentStatusPanel.tsx"
    ).read_text()
    if 'data-testid="now-standup-button"' not in source:
        raise AssertionError("CurrentStatusPanel is missing now-standup-button")


@then('the standup drawer should show section "{section_name}"')
def then_standup_drawer_shows_section(context: object, section_name: str) -> None:
    """Verify a standup section heading is visible in the drawer.

    :param context: Behave context object.
    :type context: object
    :param section_name: Expected section heading.
    :type section_name: str
    """
    standup = _ensure_standup_state(context)
    if section_name not in standup.section_names:
        raise AssertionError(
            f"expected section {section_name}, got {standup.section_names}"
        )


@then('the standup drawer result should mention "{text}"')
def then_standup_drawer_result_mentions(context: object, text: str) -> None:
    """Verify generated standup text mentions expected content.

    :param context: Behave context object.
    :type context: object
    :param text: Expected substring.
    :type text: str
    """
    standup = _ensure_standup_state(context)
    if standup.report_text is None or text not in standup.report_text:
        raise AssertionError(f"expected standup result to mention {text!r}")


@then('the standup drawer should show error "{message}"')
def then_standup_drawer_shows_error(context: object, message: str) -> None:
    """Verify the standup drawer surfaces a fail-closed error.

    :param context: Behave context object.
    :type context: object
    :param message: Expected error message.
    :type message: str
    """
    standup = _ensure_standup_state(context)
    if standup.error != message:
        raise AssertionError(f"expected error {message!r}, got {standup.error!r}")


@then("the standup drawer should not show a success result")
def then_standup_drawer_has_no_success_result(context: object) -> None:
    """Verify no successful standup result is shown after failure.

    :param context: Behave context object.
    :type context: object
    """
    standup = _ensure_standup_state(context)
    if standup.report_text:
        raise AssertionError("expected no standup success result")


@then('the standup clipboard should contain "{text}"')
def then_standup_clipboard_contains(context: object, text: str) -> None:
    """Verify copied standup text contains expected content.

    :param context: Behave context object.
    :type context: object
    :param text: Expected substring.
    :type text: str
    """
    standup = _ensure_standup_state(context)
    if standup.clipboard is None or text not in standup.clipboard:
        raise AssertionError(f"expected clipboard to contain {text!r}")


@then('the standup API response should have profile "{profile}"')
def then_standup_api_response_profile(context: object, profile: str) -> None:
    """Verify console API standup response profile.

    :param context: Behave context object.
    :type context: object
    :param profile: Expected profile identifier.
    :type profile: str
    """
    status = getattr(context, "standup_api_status", None)
    if status != 200:
        raise AssertionError(f"expected HTTP 200, got {status}")
    response = getattr(context, "standup_api_response", {})
    if response.get("profile") != profile:
        raise AssertionError(
            f"expected profile {profile!r}, got {response.get('profile')!r}"
        )


@then('the standup API response should include section "{section_name}"')
def then_standup_api_response_includes_section(
    context: object, section_name: str
) -> None:
    """Verify console API standup response includes a section heading.

    :param context: Behave context object.
    :type context: object
    :param section_name: Expected section heading.
    :type section_name: str
    """
    response = getattr(context, "standup_api_response", {})
    sections = response.get("sections", [])
    names = [section.get("name") for section in sections]
    if section_name not in names:
        raise AssertionError(f"expected section {section_name!r}, got {names}")


@then('the standup API response text should mention "{text}"')
def then_standup_api_response_text_mentions(context: object, text: str) -> None:
    """Verify console API standup response text mentions expected content.

    :param context: Behave context object.
    :type context: object
    :param text: Expected substring.
    :type text: str
    """
    response = getattr(context, "standup_api_response", {})
    report_text = response.get("text", "")
    if text not in report_text:
        raise AssertionError(f"expected API text to mention {text!r}")
