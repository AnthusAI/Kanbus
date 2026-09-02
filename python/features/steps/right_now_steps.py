"""Behave steps for right-now configuration and issue fields."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from behave import given, then, when

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.right_now import (
    LLM_USAGE_LOG,
    RIGHT_NOW_SUMMARY_OPERATION,
    RightNowError,
    build_leaf_right_now_context,
    build_right_now_context,
    generate_right_now_summary,
    get_right_now_summary,
    load_child_issues,
    mock_right_now_summary_text,
    summary_contains_status_keyword,
)

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


@given("mock AI is enabled")
def given_mock_ai_enabled(context: object) -> None:
    """Enable deterministic AI mock mode for right-now generation.

    :param context: Behave context object.
    :type context: object
    """
    context._ai_mock_env = os.environ.get("KANBUS_TEST_AI_MOCK")
    context._litellm_called_env = os.environ.get("KANBUS_RIGHT_NOW_LITELLM_CALLED")
    os.environ["KANBUS_TEST_AI_MOCK"] = "1"
    os.environ.pop("KANBUS_RIGHT_NOW_LITELLM_CALLED", None)


@given('the Kanbus configuration uses AI provider "{provider}" with model "{model}"')
def given_kanbus_configuration_uses_ai_provider(
    context: object, provider: str, model: str
) -> None:
    """Configure AI provider settings in .kanbus.yml.

    :param context: Behave context object.
    :type context: object
    :param provider: AI provider identifier.
    :type provider: str
    :param model: Model identifier.
    :type model: str
    """
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            payload.update(loaded)
    payload["ai"] = {"provider": provider, "model": model}
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@given("the Kanbus project has no AI configuration")
def given_kanbus_project_has_no_ai_configuration(context: object) -> None:
    """Remove AI configuration from the current project.

    :param context: Behave context object.
    :type context: object
    """
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload.pop("ai", None)
        config_path.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )


@given("the right now max length is set to {max_length:d}")
def given_right_now_max_length(context: object, max_length: int) -> None:
    """Set right_now.max_length in project configuration.

    :param context: Behave context object.
    :type context: object
    :param max_length: Maximum summary length.
    :type max_length: int
    """
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload.setdefault("right_now", {})
    payload["right_now"]["max_length"] = max_length
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@when('I generate the right now summary for issue "{identifier}"')
def when_generate_right_now_summary(context: object, identifier: str) -> None:
    """Generate a right-now summary for an issue.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path(context.working_directory)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    right_now_context = build_leaf_right_now_context(issue)
    context.right_now_generation_error = None
    context.generated_right_now_summary = None
    try:
        context.generated_right_now_summary = generate_right_now_summary(
            root,
            issue,
            right_now_context,
        )
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")
    except RightNowError as error:
        context.right_now_generation_error = str(error)
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )


@then("the generated right now summary should be non-empty")
def then_generated_right_now_summary_non_empty(context: object) -> None:
    """Verify generated right-now summary is non-empty.

    :param context: Behave context object.
    :type context: object
    """
    summary = getattr(context, "generated_right_now_summary", None)
    assert summary
    assert summary.strip()


@then('the generated right now summary should equal "{expected}"')
def then_generated_right_now_summary_equals(context: object, expected: str) -> None:
    """Verify generated right-now summary matches expected text.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected summary text.
    :type expected: str
    """
    assert context.generated_right_now_summary == expected


@then("the generated right now summary length should be at most {max_length:d}")
def then_generated_right_now_summary_length_at_most(
    context: object, max_length: int
) -> None:
    """Verify generated right-now summary respects max length.

    :param context: Behave context object.
    :type context: object
    :param max_length: Maximum allowed length.
    :type max_length: int
    """
    summary = context.generated_right_now_summary
    assert summary is not None
    assert len(summary) <= max_length


@then("the generated right now summary should not contain status keywords")
def then_generated_right_now_summary_no_status_keywords(context: object) -> None:
    """Verify generated right-now summary does not restate status labels.

    :param context: Behave context object.
    :type context: object
    """
    summary = context.generated_right_now_summary
    assert summary is not None
    assert not summary_contains_status_keyword(summary)


@then("the LLM usage log should contain a right_now_summary entry")
def then_llm_usage_log_contains_right_now_summary(context: object) -> None:
    """Verify llm_usage.jsonl contains a right_now_summary operation entry.

    :param context: Behave context object.
    :type context: object
    """
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


@then("the LiteLLM API should not be called")
def then_litellm_api_not_called(context: object) -> None:
    """Verify LiteLLM completion was not invoked.

    :param context: Behave context object.
    :type context: object
    """
    assert os.environ.get("KANBUS_RIGHT_NOW_LITELLM_CALLED") != "1"


@then('right now summary generation should fail with "{message}"')
def then_right_now_summary_generation_fails(context: object, message: str) -> None:
    """Verify right-now generation failed with the expected message.

    :param context: Behave context object.
    :type context: object
    :param message: Expected error message.
    :type message: str
    """
    assert context.right_now_generation_error == message


@given('issue "{identifier}" description is "{description}"')
def given_existing_issue_description(
    context: object, identifier: str, description: str
) -> None:
    """Update description on an existing issue without resetting other fields.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param description: Description text.
    :type description: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue = issue.model_copy(update={"description": description})
    write_issue_file(project_dir, issue)


@given(
    'an issue "{identifier}" of type "{issue_type}" with status "{status}" and parent "{parent}" and title "{title}"'
)
def given_issue_with_parent_and_title(
    context: object,
    identifier: str,
    issue_type: str,
    status: str,
    parent: str,
    title: str,
) -> None:
    """Create an issue with parent and title in one write.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param issue_type: Issue type.
    :type issue_type: str
    :param status: Issue status.
    :type status: str
    :param parent: Parent issue identifier.
    :type parent: str
    :param title: Issue title.
    :type title: str
    """
    from features.steps.workflow_steps import _write_issue_with_overrides

    _write_issue_with_overrides(
        context,
        identifier,
        issue_type,
        status,
        title=title,
        parent=parent,
    )


@given('issue "{identifier}" has description with {character_count:d} characters')
def given_issue_has_description_with_character_count(
    context: object, identifier: str, character_count: int
) -> None:
    """Set a long description on an issue for bounding tests.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    :param character_count: Description length in characters.
    :type character_count: int
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    issue = issue.model_copy(update={"description": "x" * character_count})
    write_issue_file(project_dir, issue)


@when('I build the right now context for issue "{identifier}"')
def when_build_right_now_context(context: object, identifier: str) -> None:
    """Build right-now context for an issue using loaded children.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    root = Path(context.working_directory)
    overrides = getattr(context, "environment_overrides", None) or {}
    previous_daemon = os.environ.get("KANBUS_NO_DAEMON")
    if "KANBUS_NO_DAEMON" in overrides:
        os.environ["KANBUS_NO_DAEMON"] = overrides["KANBUS_NO_DAEMON"]
    else:
        os.environ["KANBUS_NO_DAEMON"] = "1"
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    try:
        children = load_child_issues(root, identifier)
        context.right_now_context = build_right_now_context(issue, children)
    finally:
        if previous_daemon is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = previous_daemon


def _require_right_now_context(context: object):
    right_now_context = getattr(context, "right_now_context", None)
    assert right_now_context is not None, "right now context was not built"
    return right_now_context


def _child_summary_text(context: object, identifier: str) -> str:
    right_now_context = _require_right_now_context(context)
    child_summaries = right_now_context.child_summaries or []
    for child_summary in child_summaries:
        if child_summary.identifier == identifier:
            return child_summary.summary
    raise AssertionError(f"no child summary found for {identifier}")


@then('the right now context title should be "{expected}"')
def then_right_now_context_title(context: object, expected: str) -> None:
    """Verify right-now context title.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected title.
    :type expected: str
    """
    right_now_context = _require_right_now_context(context)
    assert right_now_context.title == expected


@then('the right now context description should be "{expected}"')
def then_right_now_context_description(context: object, expected: str) -> None:
    """Verify right-now context description.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected description.
    :type expected: str
    """
    right_now_context = _require_right_now_context(context)
    assert right_now_context.description == expected


@then('the right now context recent activity should contain "{expected}"')
def then_right_now_context_recent_activity_contains(
    context: object, expected: str
) -> None:
    """Verify right-now context recent activity contains text.

    :param context: Behave context object.
    :type context: object
    :param expected: Expected substring.
    :type expected: str
    """
    right_now_context = _require_right_now_context(context)
    assert expected in right_now_context.recent_activity


@then("the right now context should have no child summaries")
def then_right_now_context_has_no_child_summaries(context: object) -> None:
    """Verify right-now context has no child summaries.

    :param context: Behave context object.
    :type context: object
    """
    right_now_context = _require_right_now_context(context)
    assert right_now_context.child_summaries is None


@then("the right now context should have {child_count:d} child summaries")
def then_right_now_context_child_summaries_count(
    context: object, child_count: int
) -> None:
    """Verify right-now context child summary count (plural).

    :param context: Behave context object.
    :type context: object
    :param child_count: Expected child summary count.
    :type child_count: int
    """
    right_now_context = _require_right_now_context(context)
    child_summaries = right_now_context.child_summaries or []
    assert len(child_summaries) == child_count


@then("the right now context should have {child_count:d} child summary")
def then_right_now_context_child_summary_count(
    context: object, child_count: int
) -> None:
    """Verify right-now context child summary count (singular).

    :param context: Behave context object.
    :type context: object
    :param child_count: Expected child summary count.
    :type child_count: int
    """
    right_now_context = _require_right_now_context(context)
    child_summaries = right_now_context.child_summaries or []
    assert len(child_summaries) == child_count


@then('the child summary for "{identifier}" should be "{expected}"')
def then_child_summary_equals(context: object, identifier: str, expected: str) -> None:
    """Verify a child summary matches expected text.

    :param context: Behave context object.
    :type context: object
    :param identifier: Child issue identifier.
    :type identifier: str
    :param expected: Expected summary text.
    :type expected: str
    """
    assert _child_summary_text(context, identifier) == expected


@then('the child summary for "{identifier}" should contain "{expected}"')
def then_child_summary_contains(
    context: object, identifier: str, expected: str
) -> None:
    """Verify a child summary contains expected text.

    :param context: Behave context object.
    :type context: object
    :param identifier: Child issue identifier.
    :type identifier: str
    :param expected: Expected substring.
    :type expected: str
    """
    assert expected in _child_summary_text(context, identifier)


@then('the child summary for "{identifier}" length should be at most {max_length:d}')
def then_child_summary_length_at_most(
    context: object, identifier: str, max_length: int
) -> None:
    """Verify a child summary respects the character budget.

    :param context: Behave context object.
    :type context: object
    :param identifier: Child issue identifier.
    :type identifier: str
    :param max_length: Maximum allowed length.
    :type max_length: int
    """
    summary = _child_summary_text(context, identifier)
    assert len(summary) <= max_length


@then('the right now context should not have child summary for "{identifier}"')
def then_right_now_context_missing_child_summary(
    context: object, identifier: str
) -> None:
    """Verify a child identifier is absent from parent context.

    :param context: Behave context object.
    :type context: object
    :param identifier: Child issue identifier.
    :type identifier: str
    """
    right_now_context = _require_right_now_context(context)
    child_summaries = right_now_context.child_summaries or []
    identifiers = [child_summary.identifier for child_summary in child_summaries]
    assert identifier not in identifiers


@given("right now summary generation is disabled")
def given_right_now_summary_generation_disabled(context: object) -> None:
    """Disable right-now summary generation in project configuration.

    :param context: Behave context object.
    :type context: object
    """
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload.setdefault("right_now", {})
    payload["right_now"]["enabled"] = False
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@given('issue "{identifier}" right now state is recorded')
def given_issue_right_now_state_recorded(context: object, identifier: str) -> None:
    """Record the current right-now updated timestamp for refresh assertions.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    recorded = getattr(context, "recorded_right_now_updated_at", {})
    recorded[identifier] = issue.right_now_updated_at
    context.recorded_right_now_updated_at = recorded


@then('issue "{identifier}" should have a mock right now summary')
def then_issue_has_mock_right_now_summary(context: object, identifier: str) -> None:
    """Verify an issue has the deterministic mock right-now summary.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    expected = mock_right_now_summary_text(identifier)
    assert issue.right_now_summary == expected


@then('issue "{identifier}" right now summary should be refreshed')
def then_issue_right_now_summary_refreshed(context: object, identifier: str) -> None:
    """Verify an issue right-now summary timestamp advanced after a mutation.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier.
    :type identifier: str
    """
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    recorded = getattr(context, "recorded_right_now_updated_at", {})
    previous = recorded.get(identifier)
    assert issue.right_now_updated_at is not None
    if previous is not None:
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        actual = issue.right_now_updated_at
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        assert actual > previous


@then("the created issue should have a mock right now summary")
def then_created_issue_has_mock_right_now_summary(context: object) -> None:
    """Verify the last created issue has the deterministic mock summary.

    :param context: Behave context object.
    :type context: object
    """
    identifier = getattr(context, "last_issue_id", None)
    assert identifier is not None, "last issue id not set"
    then_issue_has_mock_right_now_summary(context, identifier)
