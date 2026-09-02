"""Behave steps for right-now configuration and issue fields."""

from __future__ import annotations

from datetime import datetime, timezone

from behave import given, then, when

from kanbus.right_now import get_right_now_summary

from features.steps.shared import (
    load_project_directory,
    read_issue_file,
    write_issue_file,
)


@given('issue "{identifier}" has right now summary "{summary}"')
def given_issue_has_right_now_summary(
    context: object, identifier: str, summary: str
) -> None:
    """Set the right-now summary on an existing issue file.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param summary: Right-now summary text.
    :type summary: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue.right_now_summary = summary
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has right now updated at "{timestamp}"')
def given_issue_has_right_now_updated_at(
    context: object, identifier: str, timestamp: str
) -> None:
    """Set the right-now updated timestamp on an existing issue file.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param timestamp: RFC3339 timestamp.
    :type timestamp: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue.right_now_updated_at = datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    )
    write_issue_file(project_dir, issue)


@when('issue "{identifier}" is saved and reloaded from disk')
def when_issue_saved_and_reloaded(context: object, identifier: str) -> None:
    """Write an issue to disk and read it back.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    write_issue_file(project_dir, issue)
    context.reloaded_issue = read_issue_file(project_dir, identifier)


@when('issue "{identifier}" is loaded from disk')
def when_issue_loaded_from_disk(context: object, identifier: str) -> None:
    """Load an issue from disk into context.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    context.reloaded_issue = read_issue_file(project_dir, identifier)


@when('I read the right now summary for issue "{identifier}"')
def when_read_right_now_summary(context: object, identifier: str) -> None:
    """Call get_right_now_summary for an issue.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    context.right_now_summary_result = get_right_now_summary(issue)


@then('issue "{identifier}" should have right now summary "{expected}"')
def then_issue_has_right_now_summary(
    context: object, identifier: str, expected: str
) -> None:
    """Verify an issue has the expected right-now summary.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param expected: Expected summary text.
    :type expected: str
    """
    issue = getattr(context, "reloaded_issue", None)
    if issue is None:
        project_dir = load_project_directory(context)
        issue = read_issue_file(project_dir, identifier)
    assert issue.right_now_summary == expected


@then('issue "{identifier}" should have right now updated at "{expected}"')
def then_issue_has_right_now_updated_at(
    context: object, identifier: str, expected: str
) -> None:
    """Verify an issue has the expected right-now updated timestamp.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param expected: Expected RFC3339 timestamp.
    :type expected: str
    """
    issue = getattr(context, "reloaded_issue", None)
    if issue is None:
        project_dir = load_project_directory(context)
        issue = read_issue_file(project_dir, identifier)
    expected_timestamp = datetime.fromisoformat(expected.replace("Z", "+00:00"))
    actual = issue.right_now_updated_at
    assert actual is not None
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    assert actual == expected_timestamp


@then('issue "{identifier}" should have no right now summary')
def then_issue_has_no_right_now_summary(context: object, identifier: str) -> None:
    """Verify an issue has no right-now summary.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    issue = getattr(context, "reloaded_issue", None)
    if issue is None:
        project_dir = load_project_directory(context)
        issue = read_issue_file(project_dir, identifier)
    assert issue.right_now_summary is None


@then('issue "{identifier}" should have no right now updated at')
def then_issue_has_no_right_now_updated_at(context: object, identifier: str) -> None:
    """Verify an issue has no right-now updated timestamp.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    issue = getattr(context, "reloaded_issue", None)
    if issue is None:
        project_dir = load_project_directory(context)
        issue = read_issue_file(project_dir, identifier)
    assert issue.right_now_updated_at is None


@then("the right now configuration should have enabled {expected}")
def then_right_now_enabled(context: object, expected: str) -> None:
    """Verify right-now enabled flag.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected boolean string.
    :type expected: str
    """
    configuration = context.configuration
    assert configuration is not None
    expected_value = expected.lower() == "true"
    assert configuration.right_now.enabled == expected_value


@then("the right now configuration should have default_tree_expanded {expected}")
def then_right_now_default_tree_expanded(context: object, expected: str) -> None:
    """Verify right-now default tree expanded flag.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected boolean string.
    :type expected: str
    """
    configuration = context.configuration
    assert configuration is not None
    expected_value = expected.lower() == "true"
    assert configuration.right_now.default_tree_expanded == expected_value


@then("the right now configuration should have max_length {expected}")
def then_right_now_max_length(context: object, expected: str) -> None:
    """Verify right-now max length.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected max length.
    :type expected: str
    """
    configuration = context.configuration
    assert configuration is not None
    assert configuration.right_now.max_length == int(expected)


@then('the right now model override should be "{expected}"')
def then_right_now_model_override(context: object, expected: str) -> None:
    """Verify right-now model override value.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected model override.
    :type expected: str
    """
    configuration = context.configuration
    assert configuration is not None
    assert configuration.right_now.model == expected


@then("the right now model override should be unset")
def then_right_now_model_override_unset(context: object) -> None:
    """Verify right-now model override is unset.

    :param context: Behave context object.
    :type context: object
    """
    configuration = context.configuration
    assert configuration is not None
    assert configuration.right_now.model is None


@then('the right now summary result should be "{expected}"')
def then_right_now_summary_result(context: object, expected: str) -> None:
    """Verify get_right_now_summary returned the expected value.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected summary text.
    :type expected: str
    """
    assert context.right_now_summary_result == expected


@then("the right now summary result should be unset")
def then_right_now_summary_result_unset(context: object) -> None:
    """Verify get_right_now_summary returned None.

    :param context: Behave context object.
    :type context: object
    """
    assert context.right_now_summary_result is None
