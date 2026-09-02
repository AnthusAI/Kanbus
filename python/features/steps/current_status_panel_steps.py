"""Behave steps for the console current status panel."""

from __future__ import annotations

from behave import given, then, when

from features.steps.console_ui_steps import (
    ConsoleIssue,
    _ensure_console_storage,
    _post_notification,
    _require_console_state,
)

RIGHT_NOW_PLACEHOLDER = "(no right-now summary)"
STATUS_FEED_LIMIT = 30


def _find_issue_by_title(title: str, issues: list[ConsoleIssue]) -> ConsoleIssue | None:
    for issue in issues:
        if issue.title == title:
            return issue
    return None


def _status_feed_issues(issues: list[ConsoleIssue]) -> list[ConsoleIssue]:
    sorted_issues = sorted(
        issues,
        key=lambda issue: (issue.updated_at or "", issue.title),
        reverse=True,
    )
    return sorted_issues[:STATUS_FEED_LIMIT]


def _resolve_feed_summary(issue: ConsoleIssue) -> str:
    summary = issue.right_now_summary
    if summary is None or summary.strip() == "":
        return RIGHT_NOW_PLACEHOLDER
    return summary


@when('I switch to the "Current Status" view')
def when_switch_current_status_view(context: object) -> None:
    state = _require_console_state(context)
    state.panel_mode = "now"
    _ensure_console_storage(context).panel_mode = "now"


@given('I switch to the "Current Status" view')
def given_switch_current_status_view(context: object) -> None:
    when_switch_current_status_view(context)


@then("the current status view should be active")
def then_current_status_view_active(context: object) -> None:
    state = _require_console_state(context)
    if state.panel_mode != "now":
        raise AssertionError(f"expected current status view, got {state.panel_mode}")


@given('a status issue "{title}" updated at "{timestamp}"')
def given_status_issue(context: object, title: str, timestamp: str) -> None:
    state = _require_console_state(context)
    state.issues.append(
        ConsoleIssue(
            title=title,
            issue_type="task",
            updated_at=timestamp,
            identifier=f"kanbus-status-{len(state.issues) + 1}",
        )
    )


@given('the status issue "{title}" has right-now summary "{summary}"')
def given_status_issue_summary(context: object, title: str, summary: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    issue.right_now_summary = summary


@given("35 status issues exist with sequential update times")
def given_thirty_five_status_issues(context: object) -> None:
    state = _require_console_state(context)
    for index in range(35):
        state.issues.append(
            ConsoleIssue(
                title=f"Status issue {index + 1}",
                issue_type="task",
                updated_at=f"2026-01-{index + 1:02d}T10:00:00.000Z",
                identifier=f"kanbus-status-{index + 1}",
            )
        )


@then('the status feed should list issues in order "{order}"')
def then_status_feed_order(context: object, order: str) -> None:
    state = _require_console_state(context)
    expected_titles = [title.strip() for title in order.split(",")]
    actual_titles = [issue.title for issue in _status_feed_issues(state.issues)]
    if actual_titles != expected_titles:
        raise AssertionError(
            f"expected feed order {expected_titles}, got {actual_titles}"
        )


@then('the status feed row for "{title}" should show title "{expected}"')
def then_status_feed_row_title(context: object, title: str, expected: str) -> None:
    issue = _find_issue_by_title(title, _require_console_state(context).issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    if issue.title != expected:
        raise AssertionError(f"expected title {expected}, got {issue.title}")


@then('the status feed row for "{title}" should show right-now summary "{expected}"')
def then_status_feed_row_summary(context: object, title: str, expected: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    actual = _resolve_feed_summary(issue)
    if actual != expected:
        raise AssertionError(f"expected summary {expected}, got {actual}")


@when('the right-now summary for "{title}" is updated to "{summary}"')
def when_right_now_summary_updated(context: object, title: str, summary: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    issue.right_now_summary = summary


@when(
    'the console receives an issue update for "{title}" with right-now summary "{summary}"'
)
def when_console_receives_issue_update(
    context: object, title: str, summary: str
) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    issue.right_now_summary = summary
    port = getattr(context, "console_server_port", None)
    if port is None:
        return
    issue_id = issue.identifier or issue.title
    created_at = issue.created_at or issue.updated_at
    _post_notification(
        port,
        {
            "type": "issue_updated",
            "issue_id": issue_id,
            "fields_changed": ["right_now_summary"],
            "issue_data": {
                "id": issue_id,
                "title": issue.title,
                "description": "",
                "type": issue.issue_type,
                "status": issue.status,
                "priority": issue.priority,
                "assignee": issue.assignee,
                "creator": None,
                "parent": None,
                "labels": [],
                "dependencies": [],
                "comments": [
                    {
                        "id": None,
                        "author": comment.author,
                        "text": "",
                        "created_at": comment.created_at,
                    }
                    for comment in issue.comments
                ],
                "created_at": created_at,
                "updated_at": issue.updated_at,
                "closed_at": issue.closed_at,
                "right_now_summary": summary,
                "right_now_updated_at": issue.updated_at,
                "custom": {},
            },
        },
    )


@then("the status feed should contain {count:d} rows")
def then_status_feed_row_count(context: object, count: int) -> None:
    state = _require_console_state(context)
    actual = len(_status_feed_issues(state.issues))
    if actual != count:
        raise AssertionError(f"expected {count} feed rows, got {actual}")
