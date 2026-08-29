"""Behave steps for agent metadata."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    capture_issue_identifier,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from kanbus.agent_metadata import AgentMetadataRequest, resolve_agent_metadata
from kanbus.models import AgentMetadata, IssueComment


def _apply_env_overrides(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    original_values: dict[str, str | None] = {}
    tracked = set(getattr(context, "_tracked_env_vars", set()))
    for key, value in overrides.items():
        original_values[key] = os.environ.get(key)
        tracked.add(key)
        os.environ[key] = value
    for key in tracked:
        if key not in overrides:
            original_values.setdefault(key, os.environ.get(key))
            os.environ.pop(key, None)
    context._tracked_env_vars = tracked
    context._agent_env_original = original_values


def _restore_env_overrides(context: object) -> None:
    original_values = getattr(context, "_agent_env_original", {})
    for key, value in original_values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@given('the current user is "agent"')
def given_current_user_agent(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = "agent"
    context.environment_overrides = overrides


@given('KANBUS_AGENT_PLATFORM is set to "{value}"')
def given_kanbus_agent_platform(context: object, value: str) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_AGENT_PLATFORM"] = value
    context.environment_overrides = overrides


@given('KANBUS_AGENT_MODEL is set to "{value}"')
def given_kanbus_agent_model(context: object, value: str) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_AGENT_MODEL"] = value
    context.environment_overrides = overrides


@given('KANBUS_AGENT_SETTINGS is set to "{value}"')
def given_kanbus_agent_settings(context: object, value: str) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_AGENT_SETTINGS"] = value
    context.environment_overrides = overrides


@given("agent settings JSON is:")
def given_agent_settings_json(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_AGENT_SETTINGS"] = context.text.strip()
    context.environment_overrides = overrides


@given("KANBUS_AGENT_MODEL is unset")
def given_kanbus_agent_model_unset(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides.pop("KANBUS_AGENT_MODEL", None)
    context.environment_overrides = overrides


@given(
    'an issue "{identifier}" exists with agent metadata platform "{platform}" and model "{model}"'
)
def given_issue_with_agent_metadata(
    context: object, identifier: str, platform: str, model: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Agent tagged issue", "task", "open", None, [])
    issue = issue.model_copy(
        update={
            "agent": AgentMetadata(platform=platform, model=model),
        }
    )
    write_issue_file(project_dir, issue)


@then(
    'the created issue should have agent metadata platform "{platform}" and model "{model}"'
)
def then_created_issue_has_agent_metadata(
    context: object, platform: str, model: str
) -> None:
    identifier = capture_issue_identifier(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.agent is not None
    assert issue.agent.platform == platform
    assert issue.agent.model == model


@then('the latest comment should have agent platform "{platform}" and model "{model}"')
def then_latest_comment_has_agent_metadata(
    context: object, platform: str, model: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    latest = issue.comments[-1]
    assert latest.agent is not None
    assert latest.agent.platform == platform
    assert latest.agent.model == model


@then('the latest comment should have agent settings speed "{speed}"')
def then_latest_comment_has_agent_settings_speed(context: object, speed: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    latest = issue.comments[-1]
    assert latest.agent is not None
    assert latest.agent.settings.get("speed") == speed


@then(
    'the latest comment should have agent setting "{key}" with value "{value}"'
)
def then_latest_comment_has_agent_setting(
    context: object, key: str, value: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    latest = issue.comments[-1]
    assert latest.agent is not None
    assert str(latest.agent.settings.get(key)) == value


@given(
    'issue "{identifier}" has a comment from "{author}" with text "{text}" and agent metadata platform "{platform}" and model "{model}"'
)
def given_issue_comment_with_agent_metadata(
    context: object,
    identifier: str,
    author: str,
    text: str,
    platform: str,
    model: str,
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    comment = IssueComment(
        id="abc123def456",
        author=author,
        text=text,
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        agent=AgentMetadata(platform=platform, model=model),
    )
    issue = issue.model_copy(update={"comments": [comment]})
    write_issue_file(project_dir, issue)


@when("I resolve agent metadata with no CLI overrides")
def when_resolve_agent_metadata(context: object) -> None:
    _apply_env_overrides(context)
    try:
        context.resolved_agent_metadata = resolve_agent_metadata(AgentMetadataRequest())
    finally:
        _restore_env_overrides(context)


@then('the resolved agent platform should be "{platform}"')
def then_resolved_agent_platform(context: object, platform: str) -> None:
    metadata = getattr(context, "resolved_agent_metadata", None)
    assert metadata is not None
    assert metadata.platform == platform


@then('the resolved agent model should be "{model}"')
def then_resolved_agent_model(context: object, model: str) -> None:
    metadata = getattr(context, "resolved_agent_metadata", None)
    assert metadata is not None
    assert metadata.model == model


@then("agent metadata should be absent")
def then_agent_metadata_absent(context: object) -> None:
    metadata = getattr(context, "resolved_agent_metadata", None)
    assert metadata is None
