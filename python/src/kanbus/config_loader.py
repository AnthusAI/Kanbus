"""Project configuration loading and validation."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.models import ProjectConfiguration

CONGREGATION_ENV_FILENAME = ".kanbus.env"

SORT_PRESETS = ("fifo", "priority-first", "recently-updated")
SORT_FIELDS = ("priority", "created_at", "updated_at", "id")
SORT_DIRECTIONS = ("asc", "desc")
HOOK_EVENTS = {
    "issue.create",
    "issue.update",
    "issue.close",
    "issue.delete",
    "issue.comment",
    "issue.dependency",
    "issue.promote",
    "issue.localize",
    "issue.show",
    "issue.list",
    "issue.ready",
}


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

    load_repository_environment(path.parent)
    data = _load_configuration_data(path)
    _validate_canonical_config_overrides(path, data)
    override = _load_override_configuration(path.parent / ".kanbus.override.yml")
    # Nested defaults are mutated by normalization and environment overrides;
    # keep each loaded project isolated from the process-wide template.
    merged = {**copy.deepcopy(DEFAULT_CONFIGURATION), **data}
    # Apply overrides, merging virtual_projects additively so the override
    # adds entries rather than replacing the entire map.
    if override:
        main_vp = merged.get("virtual_projects")
        override_vp = override.get("virtual_projects")
        merged.update(override)
        if isinstance(main_vp, dict) and isinstance(override_vp, dict):
            merged["virtual_projects"] = {**main_vp, **override_vp}
    if merged.get("router") is not None and not isinstance(merged["router"], dict):
        raise ConfigurationError("router must be a mapping")
    _reject_legacy_fields(merged)
    _reject_standup_lookback_hours(merged)
    _normalize_virtual_projects(merged)
    _apply_environment_overrides(merged)

    try:
        configuration = ProjectConfiguration.model_validate(merged)
    except ValidationError as error:
        router_error = _router_validation_error(error)
        if router_error is not None:
            raise ConfigurationError(router_error) from error
        if _has_standup_lookback_hours(error):
            raise ConfigurationError(
                STANDUP_LOOKBACK_HOURS_MIGRATION_MESSAGE
            ) from error
        if any(item["loc"] == ("coordination", "providers") for item in error.errors()):
            raise ConfigurationError(
                "coordination providers must be one of: git; mqtt,git; "
                "mutex_api,mqtt,git"
            ) from error
        for item in error.errors():
            location = item["loc"]
            if location == ("coordination", "mutex_api", "endpoint"):
                if "must use HTTPS unless the host is loopback" in str(
                    item.get("msg", "")
                ):
                    raise ConfigurationError(
                        "coordination.mutex_api.endpoint: must use HTTPS unless the host is loopback"
                    ) from error
                raise ConfigurationError(
                    "coordination.mutex_api.endpoint: must be an absolute http(s) URL"
                ) from error
            if (
                len(location) == 2
                and location[0] == "coordination"
                and location[1] in {"contention_window", "default_lease_ttl"}
            ):
                raise ConfigurationError(
                    f"coordination.{location[1]}: duration must be a positive integer "
                    "followed by s, m, or h"
                ) from error
        if _has_unknown_fields(error):
            raise ConfigurationError("unknown configuration fields") from error
        raise ConfigurationError(str(error)) from error

    errors = validate_project_configuration(configuration)
    if errors:
        router_error = next(
            (message for message in errors if message.startswith("router.")), None
        )
        if router_error is not None:
            raise ConfigurationError(router_error)
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
    coordination = merged.setdefault("coordination", {})
    mutex_api = coordination.setdefault("mutex_api", {})

    mutex_api_endpoint = os.environ.get("KANBUS_COORDINATION_MUTEX_API_ENDPOINT")
    if mutex_api_endpoint:
        mutex_api["endpoint"] = mutex_api_endpoint

    mutex_api_bearer_token = os.environ.get(
        "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN"
    )
    if mutex_api_bearer_token:
        mutex_api["bearer_token"] = mutex_api_bearer_token

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


def congregation_env_path() -> Path:
    """Return the user congregation env file path.

    :return: Path to ``~/.kanbus.env``.
    :rtype: Path
    """
    return Path.home() / CONGREGATION_ENV_FILENAME


def load_repository_environment(repository_root: Path) -> None:
    """Load congregation and project dotenv files into the process environment.

    Loads ``~/.kanbus.env`` first, then ``repository_root/.env``. Values already
    present in the process environment are never overwritten.

    :param repository_root: Repository root containing ``.kanbus.yml``.
    :type repository_root: Path
    """
    load_dotenv_file(congregation_env_path())
    load_dotenv_file(repository_root / ".env")


def load_dotenv_file(path: Path) -> None:
    """Load key/value pairs from a dotenv file without overriding existing env vars.

    :param path: Dotenv file path.
    :type path: Path
    """
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


def _load_dotenv(path: Path) -> None:
    load_dotenv_file(path)


def _validate_canonical_config_overrides(path: Path, data: dict) -> None:
    if path.name != "kanbus.yml":
        return
    if "hierarchy" in data:
        canonical = ["initiative", "epic", "issue", "subtask"]
        if data["hierarchy"] != canonical:
            raise ConfigurationError("hierarchy is fixed")


def _validate_type_workflow_bindings(
    configuration: ProjectConfiguration,
) -> list[str]:
    errors: list[str] = []
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


def validate_project_configuration(configuration: ProjectConfiguration) -> list[str]:
    """Validate configuration rules beyond schema validation.

    :param configuration: Loaded configuration.
    :type configuration: ProjectConfiguration
    :return: List of validation errors.
    :rtype: List[str]
    """
    errors: list[str] = []
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

    router = configuration.router
    if router is not None and router.enabled:
        if router.limits.review_wip > router.limits.project_wip:
            errors.append("router.limits.review_wip must not exceed project_wip")
        for class_name, agent_class in router.classes.items():
            for profile in agent_class.providers:
                if profile not in router.providers:
                    errors.append(
                        "router.classes."
                        f"{class_name}.providers references undefined provider profile "
                        f'"{profile}"'
                    )
        for profile in router.limits.provider_wip:
            if profile not in router.providers:
                errors.append(
                    "router.limits.provider_wip references undefined provider profile "
                    f'"{profile}"'
                )
        for class_name in router.limits.class_wip:
            if class_name not in router.classes:
                errors.append(
                    "router.limits.class_wip references undefined class "
                    f'"{class_name}"'
                )

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

    if router is not None and router.enabled and router.workflow is not None:
        for role in ("pending", "active", "review", "blocked"):
            status = getattr(router.workflow, role)
            if status not in valid_statuses:
                errors.append(
                    f'router.workflow.{role} references undefined status "{status}"'
                )
        for status in router.workflow.terminal:
            if status not in valid_statuses:
                errors.append(
                    f'router.workflow.terminal references undefined status "{status}"'
                )

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

    _validate_hooks(configuration, errors)
    _validate_sort_order(configuration, errors)
    _validate_right_now(configuration, errors)

    return errors


def _validate_hooks(configuration: ProjectConfiguration, errors: list[str]) -> None:
    hooks_config = configuration.hooks
    for phase_name, phase_map in (
        ("before", hooks_config.before),
        ("after", hooks_config.after),
    ):
        for event_name, hooks in phase_map.items():
            if event_name not in HOOK_EVENTS:
                errors.append(
                    f"hooks.{phase_name} contains unknown event '{event_name}'"
                )
                continue
            if not hooks:
                errors.append(
                    f"hooks.{phase_name}.{event_name} must define at least one hook"
                )
                continue
            seen_ids: set[str] = set()
            for hook in hooks:
                if hook.id in seen_ids:
                    errors.append(
                        f"hooks.{phase_name}.{event_name} has duplicate id '{hook.id}'"
                    )
                else:
                    seen_ids.add(hook.id)


def _validate_right_now(
    configuration: ProjectConfiguration,
    errors: list[str],
) -> None:
    if configuration.right_now.max_length <= 0:
        errors.append("right_now.max_length must be greater than 0")


def _validate_sort_order(
    configuration: ProjectConfiguration,
    errors: list[str],
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


def _validate_sort_rule(path: str, value: object, errors: list[str]) -> None:
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


STANDUP_LOOKBACK_HOURS_MIGRATION_MESSAGE = (
    "standup.lookback_hours was removed; use standup.lookback with a duration "
    "string such as 24h or 1d"
)


def _reject_legacy_fields(data: dict) -> None:
    if "external_projects" in data:
        if "virtual_projects" not in data:
            data["virtual_projects"] = data["external_projects"]
        data.pop("external_projects", None)


def _reject_standup_lookback_hours(data: dict) -> None:
    standup = data.get("standup")
    if isinstance(standup, dict) and "lookback_hours" in standup:
        raise ConfigurationError(STANDUP_LOOKBACK_HOURS_MIGRATION_MESSAGE)


def _has_standup_lookback_hours(error: ValidationError) -> bool:
    for item in error.errors():
        if item.get("type") != "extra_forbidden":
            continue
        location = item.get("loc") or ()
        if (
            len(location) >= 2
            and location[0] == "standup"
            and location[1] == "lookback_hours"
        ):
            return True
    return False


def _has_unknown_fields(error: ValidationError) -> bool:
    return any(item.get("type") == "extra_forbidden" for item in error.errors())


def _router_validation_error(error: ValidationError) -> str | None:
    """Translate router model errors to stable user-facing validation text."""
    for item in error.errors():
        location = item.get("loc") or ()
        if not location or location[0] != "router":
            continue
        error_type = item.get("type")
        if error_type == "extra_forbidden":
            field_path = ".".join(str(part) for part in location)
            return f"{field_path} is an unknown field"
        if len(location) == 1 and error_type == "model_type":
            return "router must be a mapping"
        if len(location) == 1 and error_type == "value_error":
            if "workflow, limits, and providers are required" in str(
                item.get("msg", "")
            ):
                return (
                    "router.workflow, router.limits, and router.providers are required"
                )
        if location == ("router", "workflow") and error_type == "value_error":
            return "router.workflow roles must use distinct statuses"
        if location == ("router", "workflow", "terminal") and error_type == "too_short":
            return "router.workflow.terminal must be a nonempty list"
        if location == ("router", "providers") and error_type == "too_short":
            return "router.providers must be a nonempty mapping"
        if len(location) == 2 and location[1] == "watch_interval":
            return "router.watch_interval must be a positive duration"
        if (
            len(location) == 2
            and location[1] == "forge"
            and error_type == "value_error"
        ):
            message = str(item.get("msg", ""))
            if "router forge provider must be github" in message:
                return "router.forge.provider must be github"
            if "router forge repository must use owner/repository" in message:
                return "router.forge.repository must use owner/repository format"
            if "router forge token_env" in message:
                return (
                    "router.forge.token_env must be a valid environment variable name"
                )
            if "router forge api_url must use HTTPS" in message:
                return "router.forge.api_url must use HTTPS unless the host is loopback"
            if "router forge api_url must not include URL credentials" in message:
                return "router.forge.api_url must not include URL credentials"
            if "router forge api_url" in message:
                return "router.forge.api_url must be an absolute http(s) URL"
        if (
            len(location) == 3
            and location[1] == "forge"
            and location[2] == "repository"
            and error_type == "missing"
        ):
            return "router.forge.repository is required"
        if len(location) == 3 and location[1] == "forge" and location[2] == "token_env":
            return "router.forge.token_env must be a valid environment variable name"
        if (
            len(location) == 4
            and location[1] == "providers"
            and location[3] == "adapter"
        ):
            profile = location[2]
            return f"router.providers.{profile}.adapter must be codex"
        if (
            len(location) == 4
            and location[1] == "classes"
            and location[3] == "providers"
            and error_type == "too_short"
        ):
            return f"router.classes.{location[2]}.providers must be a nonempty list"
        if (
            len(location) == 3
            and location[1] == "limits"
            and error_type in {"int_type", "greater_than_equal"}
        ):
            field_name = location[2]
            if field_name in {"project_wip", "review_wip"}:
                return f"router.limits.{field_name} must be a positive integer"
        if len(location) == 3 and location[1] == "limits":
            field_name = location[2]
            if field_name in {"project_wip", "review_wip"}:
                return f"router.limits.{field_name} must be a positive integer"
        if error_type == "value_error" and len(location) == 1:
            message = str(item.get("msg", ""))
            if "review WIP" in message:
                return "router.limits.review_wip must not exceed project_wip"
    return None


def resolve_board_name(
    configured_name: str | None,
    repository_root: Path,
    project_key: str,
) -> str:
    """Return the board title for console display.

    :param configured_name: Optional ``name`` from ``.kanbus.yml``.
    :type configured_name: Optional[str]
    :param repository_root: Repository root path.
    :type repository_root: Path
    :param project_key: Issue ID project key used when the folder name is empty.
    :type project_key: str
    :return: Configured name, repository folder name, or project key.
    :rtype: str
    """
    if configured_name is not None:
        trimmed = configured_name.strip()
        if trimmed:
            return trimmed
    folder_name = repository_root.resolve().name
    if folder_name and folder_name != ".":
        return folder_name
    return project_key
