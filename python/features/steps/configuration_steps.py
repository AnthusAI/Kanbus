"""Behave steps for configuration loading."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import yaml
from behave import given, then, when

from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.config_loader import ConfigurationError, load_project_configuration

from features.steps.shared import initialize_default_project, load_project_directory


@given("a Taskulus project with an invalid configuration containing unknown fields")
def given_invalid_config_unknown_fields(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["unknown_field"] = "value"
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with a configuration file")
def given_project_with_configuration_file(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an unreadable configuration file")
def given_project_with_unreadable_configuration_file(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    config_path = project_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )
    config_path.chmod(0)


@given("a Taskulus project with an invalid configuration containing empty hierarchy")
def given_invalid_config_empty_hierarchy(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["hierarchy"] = []
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration containing duplicate types")
def given_invalid_config_duplicate_types(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["types"] = ["bug", "task"]
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration missing the default workflow")
def given_invalid_config_missing_default_workflow(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["workflows"] = {"epic": {"open": ["in_progress"]}}
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration missing the default priority")
def given_invalid_config_missing_default_priority(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["default_priority"] = 99
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration containing wrong field types")
def given_invalid_config_wrong_field_types(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["priorities"] = "high"
    (project_dir / "config.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@when("the configuration is loaded")
def when_configuration_loaded(context: object) -> None:
    project_dir = load_project_directory(context)
    config_path = project_dir / "config.yaml"
    try:
        context.configuration = load_project_configuration(config_path)
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="")
    except ConfigurationError as error:
        context.configuration = None
        context.result = SimpleNamespace(exit_code=1, stdout="", stderr=str(error))


@then("the prefix should be \"tsk\"")
def then_prefix_should_be_tsk(context: object) -> None:
    assert context.configuration.prefix == "tsk"


@then('the hierarchy should be "initiative, epic, task, sub-task"')
def then_hierarchy_should_match(context: object) -> None:
    hierarchy = ", ".join(context.configuration.hierarchy)
    assert hierarchy == "initiative, epic, task, sub-task"


@then('the non-hierarchical types should be "bug, story, chore"')
def then_types_should_match(context: object) -> None:
    types_text = ", ".join(context.configuration.types)
    assert types_text == "bug, story, chore"


@then('the initial status should be "open"')
def then_initial_status_should_match(context: object) -> None:
    assert context.configuration.initial_status == "open"


@then("the default priority should be 2")
def then_default_priority_should_match(context: object) -> None:
    assert context.configuration.default_priority == 2
