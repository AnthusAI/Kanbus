"""Behave steps for configuration loading."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import yaml
from behave import given, then, when

from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.config_loader import ConfigurationError, load_project_configuration

from features.steps.shared import ensure_git_repository, initialize_default_project


@given("a Taskulus project with an invalid configuration containing unknown fields")
def given_invalid_config_unknown_fields(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["unknown_field"] = "value"
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    if getattr(context, "original_discover_taskulus_projects", None) is None:
        import taskulus.project as project

        context.original_discover_taskulus_projects = project.discover_taskulus_projects

        def fake_discover(_root: Path) -> list[Path]:
            return []

        project.discover_taskulus_projects = fake_discover


@given(
    "a Taskulus repository with a .taskulus.yml file containing the default configuration"
)
def given_repo_with_default_configuration(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus repository with an empty .taskulus.yml file")
def given_repo_with_empty_configuration(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".taskulus.yml").write_text("", encoding="utf-8")


@given("a Taskulus repository with a .taskulus.yml file containing null")
def given_repo_with_null_configuration(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".taskulus.yml").write_text("null\n", encoding="utf-8")


@given(
    "a Taskulus repository with a .taskulus.yml file containing unknown configuration fields"
)
def given_repo_with_unknown_fields(context: object) -> None:
    given_invalid_config_unknown_fields(context)


@given("a Taskulus repository with a .taskulus.yml file containing an empty hierarchy")
def given_repo_with_empty_hierarchy(context: object) -> None:
    given_invalid_config_empty_hierarchy(context)


@given("a Taskulus repository with a .taskulus.yml file that is not a mapping")
def given_repo_with_non_mapping_config(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".taskulus.yml").write_text("- not-a-map\n", encoding="utf-8")


@given(
    "a Taskulus repository with a .taskulus.yml file containing an empty project directory"
)
def given_repo_with_empty_project_directory(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = ""
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus repository with a .taskulus.yml file containing duplicate types")
def given_repo_with_duplicate_types(context: object) -> None:
    given_invalid_config_duplicate_types(context)


@given("a Taskulus repository with a .taskulus.yml file missing the default workflow")
def given_repo_missing_default_workflow(context: object) -> None:
    given_invalid_config_missing_default_workflow(context)


@given("a Taskulus repository with a .taskulus.yml file missing the default priority")
def given_repo_missing_default_priority(context: object) -> None:
    given_invalid_config_missing_default_priority(context)


@given("a Taskulus repository with a .taskulus.yml file containing wrong field types")
def given_repo_with_wrong_field_types(context: object) -> None:
    given_invalid_config_wrong_field_types(context)


@given("a Taskulus repository with an unreadable .taskulus.yml file")
def given_repo_with_unreadable_config(context: object) -> None:
    given_project_with_unreadable_configuration_file(context)


@given("a Taskulus project with a configuration file")
def given_project_with_configuration_file(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )


@given(
    'a Taskulus repository with a .taskulus.yml file pointing to "tracking" as the project directory'
)
def given_project_with_custom_project_directory(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = "tracking"
    (repository / "tracking" / "issues").mkdir(parents=True, exist_ok=True)
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given(
    "a Taskulus repository with a .taskulus.yml file pointing to an absolute project directory"
)
def given_project_with_absolute_project_directory(context: object) -> None:
    initialize_default_project(context)
    abs_project = Path(context.temp_dir) / "abs-project"
    (abs_project / "issues").mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = str(abs_project)
    repository = Path(context.working_directory)
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    context.expected_project_directory = str(abs_project)


@given("a Taskulus repository without a .taskulus.yml file")
def given_project_without_configuration_file(context: object) -> None:
    repository = Path(context.temp_dir) / "missing-config"
    repository.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository)
    context.working_directory = repository


@given("a Taskulus project with an unreadable configuration file")
def given_project_with_unreadable_configuration_file(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    config_path = repository / ".taskulus.yml"
    config_path.write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )
    config_path.chmod(0)


@given("a Taskulus project with an invalid configuration containing empty hierarchy")
def given_invalid_config_empty_hierarchy(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["hierarchy"] = []
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration containing duplicate types")
def given_invalid_config_duplicate_types(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["types"] = ["bug", "task"]
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration missing the default workflow")
def given_invalid_config_missing_default_workflow(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["workflows"] = {"epic": {"open": ["in_progress"]}}
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration missing the default priority")
def given_invalid_config_missing_default_priority(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["default_priority"] = 99
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given(
    "a Taskulus repository with a .taskulus.yml file containing a bright white status color"
)
def given_repo_with_bright_white_status_color(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload.setdefault("status_colors", {})
    payload["status_colors"]["open"] = "bright_white"
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given(
    "a Taskulus repository with a .taskulus.yml file containing an invalid status color"
)
def given_repo_with_invalid_status_color(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload.setdefault("status_colors", {})
    payload["status_colors"]["open"] = "invalid-color"
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Taskulus project with an invalid configuration containing wrong field types")
def given_invalid_config_wrong_field_types(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["priorities"] = "high"
    (repository / ".taskulus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@when("the configuration is loaded")
def when_configuration_loaded(context: object) -> None:
    repository = Path(context.working_directory)
    config_path = repository / ".taskulus.yml"
    try:
        context.configuration = load_project_configuration(config_path)
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="")
    except ConfigurationError as error:
        context.configuration = None
        context.result = SimpleNamespace(exit_code=1, stdout="", stderr=str(error))


@then('the project key should be "tsk"')
def then_project_key_should_be_tsk(context: object) -> None:
    assert context.configuration.project_key == "tsk"


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


@then('the project directory should be "{value}"')
def then_project_directory_should_match(context: object, value: str) -> None:
    assert context.configuration.project_directory == value


@then("the project directory should match the configured absolute path")
def then_project_directory_should_match_absolute(context: object) -> None:
    expected = getattr(context, "expected_project_directory", None)
    assert expected is not None
    assert context.configuration.project_directory == expected


@then("beads compatibility should be false")
def then_beads_compatibility_should_be_false(context: object) -> None:
    assert context.configuration.beads_compatibility is False
