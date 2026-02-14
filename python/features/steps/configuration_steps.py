"""Behave steps for configuration loading."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import yaml
from behave import given, then, when

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.config_loader import ConfigurationError, load_project_configuration

from features.steps.shared import ensure_git_repository, initialize_default_project


@given("a Kanbus project with an invalid configuration containing unknown fields")
def given_invalid_config_unknown_fields(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["unknown_field"] = "value"
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    if getattr(context, "original_discover_kanbus_projects", None) is None:
        import kanbus.project as project

        context.original_discover_kanbus_projects = project.discover_kanbus_projects

        def fake_discover(_root: Path) -> list[Path]:
            return []

        project.discover_kanbus_projects = fake_discover


@given(
    "a Kanbus repository with a .kanbus.yml file containing the default configuration"
)
def given_repo_with_default_configuration(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus repository with an empty .kanbus.yml file")
def given_repo_with_empty_configuration(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".kanbus.yml").write_text("", encoding="utf-8")


@given("a Kanbus repository with a .kanbus.yml file containing null")
def given_repo_with_null_configuration(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".kanbus.yml").write_text("null\n", encoding="utf-8")


@given(
    "a Kanbus repository with a .kanbus.yml file containing unknown configuration fields"
)
def given_repo_with_unknown_fields(context: object) -> None:
    given_invalid_config_unknown_fields(context)


@given("a Kanbus repository with a .kanbus.yml file containing an empty hierarchy")
def given_repo_with_empty_hierarchy(context: object) -> None:
    given_invalid_config_empty_hierarchy(context)


@given("a Kanbus repository with a .kanbus.yml file that is not a mapping")
def given_repo_with_non_mapping_config(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".kanbus.yml").write_text("- not-a-map\n", encoding="utf-8")


@given(
    "a Kanbus repository with a .kanbus.yml file containing an empty project directory"
)
def given_repo_with_empty_project_directory(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = ""
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus repository with a .kanbus.yml file containing duplicate types")
def given_repo_with_duplicate_types(context: object) -> None:
    given_invalid_config_duplicate_types(context)


@given("a Kanbus repository with a .kanbus.yml file missing the default workflow")
def given_repo_missing_default_workflow(context: object) -> None:
    given_invalid_config_missing_default_workflow(context)


@given("a Kanbus repository with a .kanbus.yml file missing the default priority")
def given_repo_missing_default_priority(context: object) -> None:
    given_invalid_config_missing_default_priority(context)


@given("a Kanbus repository with a .kanbus.yml file containing wrong field types")
def given_repo_with_wrong_field_types(context: object) -> None:
    given_invalid_config_wrong_field_types(context)


@given("a Kanbus repository with an unreadable .kanbus.yml file")
def given_repo_with_unreadable_config(context: object) -> None:
    given_project_with_unreadable_configuration_file(context)


@given("a Kanbus project with a configuration file")
def given_project_with_configuration_file(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )


@given('the Kanbus configuration sets default assignee "{assignee}"')
def given_kanbus_configuration_default_assignee(
    context: object, assignee: str
) -> None:
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    payload["assignee"] = assignee
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given('a Kanbus override file sets default assignee "{assignee}"')
def given_override_default_assignee(context: object, assignee: str) -> None:
    repository = Path(context.working_directory)
    override_path = repository / ".kanbus.override.yml"
    override_path.write_text(
        yaml.safe_dump({"assignee": assignee}, sort_keys=False),
        encoding="utf-8",
    )


@given('a Kanbus override file sets time zone "{time_zone}"')
def given_override_time_zone(context: object, time_zone: str) -> None:
    repository = Path(context.working_directory)
    override_path = repository / ".kanbus.override.yml"
    override_path.write_text(
        yaml.safe_dump({"time_zone": time_zone}, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus override file that is not a mapping")
def given_override_not_mapping(context: object) -> None:
    repository = Path(context.working_directory)
    override_path = repository / ".kanbus.override.yml"
    override_path.write_text("- item\n", encoding="utf-8")


@given("a Kanbus override file containing invalid YAML")
def given_override_invalid_yaml(context: object) -> None:
    repository = Path(context.working_directory)
    override_path = repository / ".kanbus.override.yml"
    override_path.write_text("invalid: [", encoding="utf-8")


@given("an empty .kanbus.override.yml file")
def given_empty_override_file(context: object) -> None:
    repository = Path(context.working_directory)
    override_path = repository / ".kanbus.override.yml"
    override_path.write_text("", encoding="utf-8")


@given("an unreadable .kanbus.override.yml file")
def given_unreadable_override_file(context: object) -> None:
    repository = Path(context.working_directory)
    override_path = repository / ".kanbus.override.yml"
    override_path.write_text("assignee: blocked@example.com\n", encoding="utf-8")
    original_mode = override_path.stat().st_mode
    override_path.chmod(0)
    context.unreadable_path = override_path
    context.unreadable_mode = original_mode


@given(
    'a Kanbus repository with a .kanbus.yml file pointing to "tracking" as the project directory'
)
def given_project_with_custom_project_directory(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = "tracking"
    (repository / "tracking" / "issues").mkdir(parents=True, exist_ok=True)
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given(
    "a Kanbus repository with a .kanbus.yml file pointing to an absolute project directory"
)
def given_project_with_absolute_project_directory(context: object) -> None:
    initialize_default_project(context)
    abs_project = Path(context.temp_dir) / "abs-project"
    (abs_project / "issues").mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = str(abs_project)
    repository = Path(context.working_directory)
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    context.expected_project_directory = str(abs_project)


@given("a Kanbus repository without a .kanbus.yml file")
def given_project_without_configuration_file(context: object) -> None:
    repository = Path(context.temp_dir) / "missing-config"
    repository.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository)
    context.working_directory = repository


@given("a Kanbus project with an unreadable configuration file")
def given_project_with_unreadable_configuration_file(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    config_path.write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )
    config_path.chmod(0)


@given("a Kanbus project with an invalid configuration containing empty hierarchy")
def given_invalid_config_empty_hierarchy(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["hierarchy"] = []
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus project with an invalid configuration containing duplicate types")
def given_invalid_config_duplicate_types(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["types"] = ["bug", "task"]
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus project with an invalid configuration missing the default workflow")
def given_invalid_config_missing_default_workflow(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["workflows"] = {"epic": {"open": ["in_progress"]}}
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus project with an invalid configuration missing the default priority")
def given_invalid_config_missing_default_priority(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["default_priority"] = 99
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given(
    "a Kanbus repository with a .kanbus.yml file containing a bright white status color"
)
def given_repo_with_bright_white_status_color(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload.setdefault("status_colors", {})
    payload["status_colors"]["open"] = "bright_white"
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given(
    "a Kanbus repository with a .kanbus.yml file containing an invalid status color"
)
def given_repo_with_invalid_status_color(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload.setdefault("status_colors", {})
    payload["status_colors"]["open"] = "invalid-color"
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus project with an invalid configuration containing wrong field types")
def given_invalid_config_wrong_field_types(context: object) -> None:
    initialize_default_project(context)
    repository = Path(context.working_directory)
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["priorities"] = "high"
    (repository / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@when("the configuration is loaded")
def when_configuration_loaded(context: object) -> None:
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    try:
        context.configuration = load_project_configuration(config_path)
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="")
    except ConfigurationError as error:
        context.configuration = None
        context.result = SimpleNamespace(exit_code=1, stdout="", stderr=str(error))


@then('the project key should be "kanbus"')
def then_project_key_should_be_tsk(context: object) -> None:
    assert context.configuration.project_key == "kanbus"


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


@then('the default assignee should be "{assignee}"')
def then_default_assignee_should_match(context: object, assignee: str) -> None:
    assert context.configuration.assignee == assignee


@then('the time zone should be "{time_zone}"')
def then_time_zone_should_match(context: object, time_zone: str) -> None:
    assert context.configuration.time_zone == time_zone
