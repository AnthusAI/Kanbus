"""Project configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import yaml
from pydantic import ValidationError

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.models import ProjectConfiguration

SORT_PRESETS = ("fifo", "priority-first", "recently-updated")
SORT_FIELDS = ("priority", "created_at", "updated_at", "id")
SORT_DIRECTIONS = ("asc", "desc")


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

    _load_dotenv(path.parent / ".env")
    data = _load_configuration_data(path)
    _validate_canonical_config_overrides(path, data)
    override = _load_override_configuration(path.parent / ".kanbus.override.yml")
    merged = {**DEFAULT_CONFIGURATION, **data}
    # Apply overrides, merging virtual_projects additively so the override
    # adds entries rather than replacing the entire map.
    if override:
        main_vp = merged.get("virtual_projects")
        override_vp = override.get("virtual_projects")
        merged.update(override)
        if isinstance(main_vp, dict) and isinstance(override_vp, dict):
            merged["virtual_projects"] = {**main_vp, **override_vp}
    _reject_legacy_fields(merged)
    _normalize_virtual_projects(merged)
    _apply_environment_overrides(merged)

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


def _apply_environment_overrides(merged: dict) -> None:
    realtime = merged.setdefault("realtime", {})
    overlay = merged.setdefault("overlay", {})
    topics = realtime.setdefault("topics", {})

    transport = os.environ.get("KANBUS_REALTIME_TRANSPORT")
    if transport:
        realtime["transport"] = transport

    broker = os.environ.get("KANBUS_REALTIME_BROKER")
    if broker:
        realtime["broker"] = broker

    autostart = _parse_bool_env("KANBUS_REALTIME_AUTOSTART")
    if autostart is not None:
        realtime["autostart"] = autostart

    keepalive = _parse_bool_env("KANBUS_REALTIME_KEEPALIVE")
    if keepalive is not None:
        realtime["keepalive"] = keepalive

    socket_path = os.environ.get("KANBUS_REALTIME_UDS_SOCKET_PATH")
    if socket_path is not None and socket_path != "":
        realtime["uds_socket_path"] = socket_path

    mqtt_custom_authorizer_name = os.environ.get(
        "KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME"
    )
    if mqtt_custom_authorizer_name:
        realtime["mqtt_custom_authorizer_name"] = mqtt_custom_authorizer_name

    mqtt_api_token = os.environ.get("KANBUS_REALTIME_MQTT_API_TOKEN")
    if mqtt_api_token:
        realtime["mqtt_api_token"] = mqtt_api_token

    project_events = os.environ.get("KANBUS_REALTIME_TOPICS_PROJECT_EVENTS")
    if project_events:
        topics["project_events"] = project_events

    overlay_enabled = _parse_bool_env("KANBUS_OVERLAY_ENABLED")
    if overlay_enabled is not None:
        overlay["enabled"] = overlay_enabled

    overlay_ttl_s = _parse_int_env("KANBUS_OVERLAY_TTL_S")
    if overlay_ttl_s is not None:
        overlay["ttl_s"] = overlay_ttl_s


def _parse_bool_env(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_int_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return None


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


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

    if configuration.wiki_directory is not None:
        wd = configuration.wiki_directory
        if wd.startswith("/") or (len(wd) >= 2 and wd[1] == ":"):
            errors.append("wiki_directory must not escape project root")
        elif ".." in wd:
            if wd.count("..") > 1 or not wd.replace("\\", "/").startswith("../"):
                errors.append("wiki_directory must not escape project root")

    for label in configuration.virtual_projects:
        if label == configuration.project_key:
            errors.append("virtual project label conflicts with project key")
            break

    if configuration.new_issue_project is not None:
        target = configuration.new_issue_project
        if (
            target != "ask"
            and target != configuration.project_key
            and target not in configuration.virtual_projects
        ):
            errors.append("new_issue_project references unknown project")

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
        _validate_sort_order(configuration, errors)
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
        _validate_sort_order(configuration, errors)
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

    _validate_sort_order(configuration, errors)

    return errors


def _validate_sort_order(
    configuration: ProjectConfiguration,
    errors: List[str],
) -> None:
    if not configuration.sort_order:
        return

    categories = configuration.sort_order.get("categories")
    if categories is not None:
        if not isinstance(categories, dict):
            errors.append("sort_order.categories must be a mapping")
            return
        for category, rule in categories.items():
            if not isinstance(category, str):
                errors.append("sort_order.categories keys must be strings")
                continue
            _validate_sort_rule(f"sort_order.categories.{category}", rule, errors)

    for status, rule in configuration.sort_order.items():
        if status == "categories":
            continue
        _validate_sort_rule(f"sort_order.{status}", rule, errors)


def _validate_sort_rule(path: str, value: object, errors: List[str]) -> None:
    if isinstance(value, str):
        if value not in SORT_PRESETS:
            errors.append(
                f"{path} has invalid preset '{value}' "
                f"(valid presets: {', '.join(SORT_PRESETS)})"
            )
        return

    if not isinstance(value, list):
        errors.append(f"{path} must be a preset string or a list of field rules")
        return

    if not value:
        errors.append(f"{path} must not be an empty list")
        return

    for index, rule in enumerate(value):
        if not isinstance(rule, dict):
            errors.append(f"{path}[{index}] must be an object with field/direction")
            continue

        for key in rule.keys():
            if not isinstance(key, str):
                errors.append(f"{path}[{index}] contains a non-string key")
                continue
            if key not in {"field", "direction"}:
                errors.append(f"{path}[{index}] has unsupported key '{key}'")

        field = rule.get("field")
        direction = rule.get("direction")

        if isinstance(field, str):
            if field not in SORT_FIELDS:
                errors.append(
                    f"{path}[{index}] has invalid field '{field}' "
                    f"(valid fields: {', '.join(SORT_FIELDS)})"
                )
        else:
            errors.append(f"{path}[{index}] is missing 'field'")

        if isinstance(direction, str):
            if direction not in SORT_DIRECTIONS:
                errors.append(
                    f"{path}[{index}] has invalid direction '{direction}' "
                    f"(valid directions: {', '.join(SORT_DIRECTIONS)})"
                )
        else:
            errors.append(f"{path}[{index}] is missing 'direction'")


def _normalize_virtual_projects(data: dict) -> None:
    """Convert virtual_projects from a list (e.g. []) to an empty dict.

    Older configs used a list format; the model expects a dict mapping labels
    to VirtualProjectConfig.
    """
    if isinstance(data.get("virtual_projects"), list):
        data["virtual_projects"] = {}


def _reject_legacy_fields(data: dict) -> None:
    if "external_projects" in data:
        if "virtual_projects" not in data:
            data["virtual_projects"] = data["external_projects"]
        data.pop("external_projects", None)


def _has_unknown_fields(error: ValidationError) -> bool:
    return any(item.get("type") == "extra_forbidden" for item in error.errors())
