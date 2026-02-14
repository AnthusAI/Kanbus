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

    return configuration


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

    return errors


def _has_unknown_fields(error: ValidationError) -> bool:
    return any(item.get("type") == "extra_forbidden" for item in error.errors())
