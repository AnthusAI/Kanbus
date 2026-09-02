"""Behave steps for the console current status panel."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key

from behave import given, then, when

from features.steps.console_ui_steps import (
    ConsoleIssue,
    ConsoleState,
    _ensure_console_storage,
    _post_notification,
    _require_console_state,
)

RIGHT_NOW_PLACEHOLDER = "(no right-now summary)"
STATUS_FEED_LIMIT = 30


@dataclass
class StatusTreeNode:
    issue: ConsoleIssue
    children: list["StatusTreeNode"]


def _find_issue_by_title(title: str, issues: list[ConsoleIssue]) -> ConsoleIssue | None:
    for issue in issues:
        if issue.title == title:
            return issue
    return None


def _compare_recently_updated(left: ConsoleIssue, right: ConsoleIssue) -> int:
    left_key = left.updated_at or ""
    right_key = right.updated_at or ""
    if left_key != right_key:
        return -1 if left_key > right_key else 1
    left_id = left.identifier or left.title
    right_id = right.identifier or right.title
    return -1 if left_id < right_id else (1 if left_id > right_id else 0)


def _resolve_parent_identifier(
    issue: ConsoleIssue, issues: list[ConsoleIssue]
) -> str | None:
    if not issue.parent_title:
        return None
    parent = _find_issue_by_title(issue.parent_title, issues)
    if parent is None:
        return None
    return parent.identifier


def _build_status_tree(issues: list[ConsoleIssue]) -> list[StatusTreeNode]:
    identifiers = {issue.identifier for issue in issues if issue.identifier is not None}
    children_by_parent: dict[str, list[ConsoleIssue]] = {}
    for issue in issues:
        parent_identifier = _resolve_parent_identifier(issue, issues)
        if parent_identifier is None:
            continue
        children_by_parent.setdefault(parent_identifier, []).append(issue)
    for parent_identifier, children in children_by_parent.items():
        children_by_parent[parent_identifier] = sorted(
            children, key=cmp_to_key(_compare_recently_updated)
        )

    roots = [
        issue
        for issue in issues
        if _resolve_parent_identifier(issue, issues) is None
        or _resolve_parent_identifier(issue, issues) not in identifiers
    ]
    roots = sorted(roots, key=cmp_to_key(_compare_recently_updated))

    def build_node(issue: ConsoleIssue) -> StatusTreeNode:
        issue_identifier = issue.identifier or issue.title
        child_issues = children_by_parent.get(issue_identifier, [])
        return StatusTreeNode(
            issue=issue,
            children=[build_node(child) for child in child_issues],
        )

    return [build_node(root) for root in roots]


def _status_tree_has_children(issue: ConsoleIssue, issues: list[ConsoleIssue]) -> bool:
    issue_identifier = issue.identifier or issue.title
    for candidate in issues:
        if _resolve_parent_identifier(candidate, issues) == issue_identifier:
            return True
    return False


def _status_tree_node_expanded(state: ConsoleState, issue: ConsoleIssue) -> bool:
    if issue.title in state.status_tree_expanded_overrides:
        return state.status_tree_expanded_overrides[issue.title]
    return state.default_tree_expanded


def _status_tree_visible_titles(state: ConsoleState) -> list[str]:
    if not state.status_tree_mode:
        return []

    visible_titles: list[str] = []

    def walk(node: StatusTreeNode) -> None:
        visible_titles.append(node.issue.title)
        if not _status_tree_has_children(node.issue, state.issues):
            return
        if not _status_tree_node_expanded(state, node.issue):
            return
        for child in node.children:
            walk(child)

    for root in _build_status_tree(state.issues):
        walk(root)
    return visible_titles


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


@given(
    'a status hierarchy root "{title}" of type "{issue_type}" updated at "{timestamp}"'
)
def given_status_hierarchy_root(
    context: object, title: str, issue_type: str, timestamp: str
) -> None:
    state = _require_console_state(context)
    state.issues.append(
        ConsoleIssue(
            title=title,
            issue_type=issue_type,
            updated_at=timestamp,
            identifier=f"kanbus-status-{len(state.issues) + 1}",
        )
    )


@given(
    'a status hierarchy child "{title}" of type "{issue_type}" under "{parent_title}" updated at "{timestamp}"'
)
def given_status_hierarchy_child(
    context: object,
    title: str,
    issue_type: str,
    parent_title: str,
    timestamp: str,
) -> None:
    state = _require_console_state(context)
    state.issues.append(
        ConsoleIssue(
            title=title,
            issue_type=issue_type,
            parent_title=parent_title,
            updated_at=timestamp,
            identifier=f"kanbus-status-{len(state.issues) + 1}",
        )
    )


@given("the console right now configuration has default_tree_expanded {expected}")
def given_console_default_tree_expanded(context: object, expected: str) -> None:
    state = _require_console_state(context)
    state.default_tree_expanded = expected.lower() == "true"


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


@when("I enable the status tree view")
def when_enable_status_tree_view(context: object) -> None:
    state = _require_console_state(context)
    state.status_tree_mode = True


@when("I disable the status tree view")
def when_disable_status_tree_view(context: object) -> None:
    state = _require_console_state(context)
    state.status_tree_mode = False


@when('I collapse the status tree node for "{title}"')
def when_collapse_status_tree_node(context: object, title: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    state.status_tree_expanded_overrides[title] = False


@when('I expand the status tree node for "{title}"')
def when_expand_status_tree_node(context: object, title: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    state.status_tree_expanded_overrides[title] = True


@then('the status feed should list issues in order "{order}"')
def then_status_feed_order(context: object, order: str) -> None:
    state = _require_console_state(context)
    expected_titles = [title.strip() for title in order.split(",")]
    actual_titles = [issue.title for issue in _status_feed_issues(state.issues)]
    if actual_titles != expected_titles:
        raise AssertionError(
            f"expected feed order {expected_titles}, got {actual_titles}"
        )


@then('the status tree should list issues in order "{order}"')
def then_status_tree_order(context: object, order: str) -> None:
    state = _require_console_state(context)
    expected_titles = [title.strip() for title in order.split(",")]
    actual_titles = _status_tree_visible_titles(state)
    if actual_titles != expected_titles:
        raise AssertionError(
            f"expected tree order {expected_titles}, got {actual_titles}"
        )


@then('the status tree node for "{title}" should be expanded')
def then_status_tree_node_expanded(context: object, title: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    if not _status_tree_has_children(issue, state.issues):
        raise AssertionError(f"issue has no tree children: {title}")
    if not _status_tree_node_expanded(state, issue):
        raise AssertionError(f"expected tree node expanded: {title}")


@then('the status tree node for "{title}" should be collapsed')
def then_status_tree_node_collapsed(context: object, title: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    if not _status_tree_has_children(issue, state.issues):
        raise AssertionError(f"issue has no tree children: {title}")
    if _status_tree_node_expanded(state, issue):
        raise AssertionError(f"expected tree node collapsed: {title}")


@then('the status feed row for "{title}" should show title "{expected}"')
def then_status_feed_row_title(context: object, title: str, expected: str) -> None:
    issue = _find_issue_by_title(title, _require_console_state(context).issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    if issue.title != expected:
        raise AssertionError(f"expected title {expected}, got {issue.title}")


@then('the status tree row for "{title}" should show title "{expected}"')
def then_status_tree_row_title(context: object, title: str, expected: str) -> None:
    then_status_feed_row_title(context, title, expected)


@then('the status feed row for "{title}" should show right-now summary "{expected}"')
def then_status_feed_row_summary(context: object, title: str, expected: str) -> None:
    state = _require_console_state(context)
    issue = _find_issue_by_title(title, state.issues)
    if issue is None:
        raise AssertionError(f"issue not found: {title}")
    actual = _resolve_feed_summary(issue)
    if actual != expected:
        raise AssertionError(f"expected summary {expected}, got {actual}")


@then('the status tree row for "{title}" should show right-now summary "{expected}"')
def then_status_tree_row_summary(context: object, title: str, expected: str) -> None:
    then_status_feed_row_summary(context, title, expected)


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
