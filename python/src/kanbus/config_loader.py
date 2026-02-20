"""Project configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import List

import yaml
from pydantic import ValidationError

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.models import ProjectConfiguration


class ConfigurationError(RuntimeError):
    """Raised when configuration validation fails."""


def load_project_configuration(path: Path) -> ProjectConfiguration:
    """Load a project configuration from disk.

    :param path: Path to the .kanbus.yml file.
    :type path: Path
    :return: Loaded configuration.
    :rtype: ProjectConfiguration
    :raises ConfigurationError: If the configuration is invalid or missing.
    """
    if not path.exists():
        raise ConfigurationError("configuration file not found")

    data = _load_configuration_data(path)
    _validate_canonical_config_overrides(path, data)
    override = _load_override_configuration(path.parent / ".kanbus.override.yml")
    merged = {**DEFAULT_CONFIGURATION, **data, **override}

    try:
        configuration = ProjectConfiguration.model_validate(merged)
    except ValidationError as error:
        if _has_unknown_fields(error):
            raise ConfigurationError("unknown configuration fields") from error
        raise ConfigurationError(str(error)) from error

    errors = validate_project_configuration(configuration)
    if errors:
        raise ConfigurationError("; ".join(errors))

    if path.name == "kanbus.yml":
        workflow_errors = _validate_type_workflow_bindings(configuration)
        if workflow_errors:
            raise ConfigurationError("; ".join(workflow_errors))

    return configuration


def _validate_canonical_config_overrides(path: Path, data: dict) -> None:
    if path.name != "kanbus.yml":
        return
    if "hierarchy" in data:
        canonical = ["initiative", "epic", "issue", "subtask"]
        if data["hierarchy"] != canonical:
            raise ConfigurationError("hierarchy is fixed")


def _validate_type_workflow_bindings(
    configuration: ProjectConfiguration,
) -> List[str]:
    errors: List[str] = []
    workflows = configuration.workflows
    for issue_type in configuration.types:
        if issue_type not in workflows:
            errors.append(f"missing workflow binding for issue type '{issue_type}'")
    return errors


def _load_configuration_data(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(str(error)) from error

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError("configuration must be a mapping")
    return data


def _load_override_configuration(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(str(error)) from error
    except yaml.YAMLError as error:
        raise ConfigurationError("override configuration is invalid") from error

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigurationError("override configuration must be a mapping")
    return data


def validate_project_configuration(configuration: ProjectConfiguration) -> List[str]:
    """Validate configuration rules beyond schema validation.

    :param configuration: Loaded configuration.
    :type configuration: ProjectConfiguration
    :return: List of validation errors.
    :rtype: List[str]
    """
    errors: List[str] = []
    if not configuration.project_directory:
        errors.append("project_directory must not be empty")

    if not configuration.hierarchy:
        errors.append("hierarchy must not be empty")

    all_types = configuration.hierarchy + configuration.types
    seen = set()
    for item in all_types:
        if item in seen:
            errors.append("duplicate type name")
            break
        seen.add(item)

    if "default" not in configuration.workflows:
        errors.append("default workflow is required")

    if configuration.default_priority not in configuration.priorities:
        errors.append("default priority must be in priorities map")

    # Validate categories
    if not configuration.categories:
        errors.append("categories must not be empty")
    else:
        category_names = set()
        for category in configuration.categories:
            if category.name in category_names:
                errors.append("duplicate category name")
                break
            category_names.add(category.name)

    # Validate statuses
    if not configuration.statuses:
        errors.append("statuses must not be empty")
        return errors

    # Validate status categories
    if configuration.categories:
        category_names = {category.name for category in configuration.categories}
        for status in configuration.statuses:
            if status.category not in category_names:
                errors.append(
                    f"status '{status.key}' references undefined category '{status.category}'"
                )

    # Check for duplicate status keys
    status_keys = set()
    status_names = set()
    for status in configuration.statuses:
        if status.key in status_keys:
            errors.append("duplicate status key")
            break
        status_keys.add(status.key)
        if status.name in status_names:
            errors.append("duplicate status name")
            break
        status_names.add(status.name)

    # Build set of valid status keys
    valid_statuses = {s.key for s in configuration.statuses}

    # Validate that initial_status exists in statuses
    if configuration.initial_status not in valid_statuses:
        errors.append(
            f"initial_status '{configuration.initial_status}' must exist in statuses"
        )

    # Validate that all workflow states exist in statuses
    for workflow_name, workflow in configuration.workflows.items():
        for from_status, transitions in workflow.items():
            if from_status not in valid_statuses:
                errors.append(
                    f"workflow '{workflow_name}' references undefined status '{from_status}'"
                )
            for to_status in transitions:
                if to_status not in valid_statuses:
                    errors.append(
                        f"workflow '{workflow_name}' references undefined status '{to_status}'"
                    )

    # Validate transition labels
    if not configuration.transition_labels:
        errors.append("transition_labels must not be empty")
        return errors

    for workflow_name, workflow in configuration.workflows.items():
        workflow_labels = configuration.transition_labels.get(workflow_name)
        if not workflow_labels:
            errors.append(f"transition_labels missing workflow '{workflow_name}'")
            continue
        for from_status, transitions in workflow.items():
            from_labels = workflow_labels.get(from_status)
            if not from_labels:
                errors.append(
                    f"transition_labels missing from-status '{from_status}' in workflow '{workflow_name}'"
                )
                continue
            for to_status in transitions:
                label = from_labels.get(to_status)
                if not label:
                    errors.append(
                        f"transition_labels missing transition '{from_status}' -> '{to_status}' in workflow '{workflow_name}'"
                    )
            for labeled_target in from_labels:
                if labeled_target not in transitions:
                    errors.append(
                        f"transition_labels references invalid transition '{from_status}' -> '{labeled_target}' in workflow '{workflow_name}'"
                    )

        for labeled_from in workflow_labels:
            if labeled_from not in workflow:
                errors.append(
                    f"transition_labels references invalid from-status '{labeled_from}' in workflow '{workflow_name}'"
                )

    return errors


def _has_unknown_fields(error: ValidationError) -> bool:
    return any(item.get("type") == "extra_forbidden" for item in error.errors())
