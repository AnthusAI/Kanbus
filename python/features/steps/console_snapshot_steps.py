"""Behave steps for console snapshot."""

from __future__ import annotations

from behave import given, then, when
import shutil
import json
from pathlib import Path
from types import SimpleNamespace

from features.steps.shared import build_issue, load_project_directory, write_issue_file
from kanbus.console_snapshot import ConsoleSnapshotError, build_console_snapshot


@given("the Kanbus configuration file is missing")
def given_kanbus_configuration_missing(context: object) -> None:
    project_dir = load_project_directory(context)
    config_path = project_dir.parent / ".kanbus.yml"
    if config_path.exists():
        if config_path.is_dir():
            shutil.rmtree(config_path)
        else:
            config_path.unlink()


@given("a Kanbus configuration file that is not a mapping")
def given_kanbus_configuration_not_mapping(context: object) -> None:
    project_dir = load_project_directory(context)
    config_path = project_dir.parent / ".kanbus.yml"
    config_path.write_text("- item\n- other\n", encoding="utf-8")


@given("the issues directory is a file")
def given_issues_directory_is_file(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_path = project_dir / "issues"
    if issues_path.exists():
        if issues_path.is_dir():
            shutil.rmtree(issues_path)
        else:
            issues_path.unlink()
    issues_path.write_text("not a directory", encoding="utf-8")


@given("the issues directory is unreadable")
def given_issues_directory_is_unreadable(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    original_mode = issues_dir.stat().st_mode
    issues_dir.chmod(0)
    context.unreadable_path = issues_dir
    context.unreadable_mode = original_mode


@when("I build a console snapshot directly")
def when_build_console_snapshot_directly(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    root = Path(working_directory)
    try:
        snapshot = build_console_snapshot(root)
    except ConsoleSnapshotError as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    payload = json.dumps(snapshot, indent=2, sort_keys=False)
    context.result = SimpleNamespace(
        exit_code=0,
        stdout=payload,
        stderr="",
        output=payload,
    )


def _snapshot(context: object) -> dict:
    return json.loads(context.result.stdout)


def _snapshot_issue(context: object, issue_id: str) -> dict:
    matches = [
        issue for issue in _snapshot(context)["issues"] if issue["id"] == issue_id
    ]
    assert (
        len(matches) == 1
    ), f"expected one snapshot issue {issue_id}, got {len(matches)}"
    return matches[0]


def _snapshot_provider(context: object, name: str) -> dict:
    return _snapshot(context)["config"]["router"]["providers"][name]


@then('the snapshot issue "{issue_id}" agent_assignment should equal:')
def then_snapshot_issue_agent_assignment_equals(context: object, issue_id: str) -> None:
    actual = _snapshot_issue(context, issue_id)["custom"].get("agent_assignment")
    assert actual == json.loads(context.text), f"got {actual!r}"


@then('the snapshot issue "{issue_id}" should have no agent_assignment')
def then_snapshot_issue_has_no_agent_assignment(context: object, issue_id: str) -> None:
    custom = _snapshot_issue(context, issue_id)["custom"]
    assert "agent_assignment" not in custom, f"got {custom['agent_assignment']!r}"


@then('the snapshot router provider "{name}" arguments should be empty')
def then_snapshot_provider_arguments_empty(context: object, name: str) -> None:
    assert _snapshot_provider(context, name)["args"] == []


@then(
    'the snapshot router provider "{name}" environment variable "{key}" should be "{value}"'
)
def then_snapshot_provider_environment_value(
    context: object, name: str, key: str, value: str
) -> None:
    assert _snapshot_provider(context, name)["env"][key] == value


@then('the snapshot should not contain "{text}"')
def then_snapshot_does_not_contain(context: object, text: str) -> None:
    assert text not in context.result.stdout


@given('the project has issue "{issue_id}" with labels "{labels}"')
def given_project_has_issue_with_labels(
    context: object, issue_id: str, labels: str
) -> None:
    label_list = [label.strip() for label in labels.split(",") if label.strip()]
    issue = build_issue(
        issue_id, f"Fixture {issue_id}", "task", "open", None, label_list
    )
    write_issue_file(load_project_directory(context), issue)
