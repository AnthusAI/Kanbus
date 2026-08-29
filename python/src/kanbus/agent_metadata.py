"""Agent provenance metadata resolution and validation."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from kanbus.models import AgentMetadata

PLATFORM_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
SECRET_KEY_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password|credential)")
MAX_AGENT_METADATA_BYTES = 2048
MAX_AGENT_NAME_LENGTH = 128

SUGGESTED_AGENT_SETTINGS_KEYS = (
    "temperature",
    "thinking_level",
    "max_output_tokens",
    "speed",
    "reasoning_effort",
)


class AgentMetadataResolutionError(ValueError):
    """Raised when agent metadata cannot be resolved or validated."""


class AgentMetadataRequest(BaseModel):
    """Optional agent metadata inputs from CLI flags and environment."""

    model_config = ConfigDict(extra="forbid")

    platform: Optional[str] = None
    model: Optional[str] = None
    name: Optional[str] = None
    settings_json: Optional[str] = None


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _normalize_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if not PLATFORM_PATTERN.fullmatch(normalized):
        raise AgentMetadataResolutionError("invalid agent platform")
    return normalized


def _normalize_agent_name(name: Optional[str]) -> Optional[str]:
    normalized = _normalize_optional_text(name)
    if normalized is None:
        return None
    if len(normalized) > MAX_AGENT_NAME_LENGTH:
        raise AgentMetadataResolutionError("invalid agent name")
    return normalized


def _validate_settings_keys(settings: Dict[str, Any]) -> None:
    for key in settings:
        if SECRET_KEY_PATTERN.search(key):
            raise AgentMetadataResolutionError(
                "agent settings must not contain secret-like keys"
            )


def _parse_settings_json(settings_json: Optional[str]) -> Dict[str, Any]:
    normalized = _normalize_optional_text(settings_json)
    if normalized is None:
        return {}
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise AgentMetadataResolutionError(
            f"invalid agent settings JSON: {error.msg}"
        ) from error
    if not isinstance(parsed, dict):
        raise AgentMetadataResolutionError(
            "invalid agent settings JSON: expected object"
        )
    return parsed


def _serialize_agent_metadata(agent: AgentMetadata) -> Dict[str, Any]:
    payload = agent.model_dump(exclude_none=True)
    settings = payload.get("settings")
    if isinstance(settings, dict) and not settings:
        payload.pop("settings", None)
    return payload


def build_agent_metadata(
    platform: Optional[str],
    model: Optional[str],
    settings: Optional[Dict[str, Any]] = None,
    name: Optional[str] = None,
) -> Optional[AgentMetadata]:
    """Build validated agent metadata or return None when all inputs are absent.

    :param platform: Agent platform identifier.
    :type platform: Optional[str]
    :param model: Model identifier.
    :type model: Optional[str]
    :param settings: Parsed settings object.
    :type settings: Optional[Dict[str, Any]]
    :param name: Optional session or bot name.
    :type name: Optional[str]
    :return: Validated metadata or None.
    :rtype: Optional[AgentMetadata]
    :raises AgentMetadataResolutionError: If partial or invalid metadata is provided.
    """
    normalized_platform = _normalize_optional_text(platform)
    normalized_model = _normalize_optional_text(model)
    normalized_name = _normalize_agent_name(name)
    settings_payload = settings if settings is not None else {}
    if (
        normalized_platform is None
        and normalized_model is None
        and not settings_payload
        and normalized_name is None
    ):
        return None
    if normalized_platform is None or normalized_model is None:
        raise AgentMetadataResolutionError(
            "agent metadata requires both platform and model"
        )
    _validate_settings_keys(settings_payload)
    agent = AgentMetadata(
        platform=_normalize_platform(normalized_platform),
        model=normalized_model,
        name=normalized_name,
        settings=settings_payload,
    )
    serialized = json.dumps(
        _serialize_agent_metadata(agent),
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized.encode("utf-8")) > MAX_AGENT_METADATA_BYTES:
        raise AgentMetadataResolutionError("agent metadata exceeds maximum size")
    return agent


def resolve_agent_metadata(request: AgentMetadataRequest) -> Optional[AgentMetadata]:
    """Resolve agent metadata from CLI flags with environment defaults.

    :param request: CLI-provided agent metadata inputs.
    :type request: AgentMetadataRequest
    :return: Validated metadata or None.
    :rtype: Optional[AgentMetadata]
    :raises AgentMetadataResolutionError: If validation fails.
    """
    platform = _normalize_optional_text(request.platform)
    model = _normalize_optional_text(request.model)
    name = _normalize_agent_name(request.name)
    settings_json = _normalize_optional_text(request.settings_json)
    if platform is None:
        platform = _normalize_optional_text(os.getenv("KANBUS_AGENT_PLATFORM"))
    if model is None:
        model = _normalize_optional_text(os.getenv("KANBUS_AGENT_MODEL"))
    if name is None:
        name = _normalize_agent_name(os.getenv("KANBUS_AGENT_NAME"))
    if settings_json is None:
        settings_json = _normalize_optional_text(os.getenv("KANBUS_AGENT_SETTINGS"))
    settings = _parse_settings_json(settings_json)
    return build_agent_metadata(platform, model, settings, name)


def format_agent_display_line(agent: AgentMetadata) -> str:
    """Format agent metadata for compact CLI display.

    :param agent: Agent metadata to format.
    :type agent: AgentMetadata
    :return: Display string such as ``cloud-agent / cursor / composer-2.5``.
    :rtype: str
    """
    platform_model = f"{agent.platform} / {agent.model}"
    if agent.name:
        return f"{agent.name} / {platform_model}"
    return platform_model


def _format_setting_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def format_agent_settings_display(agent: AgentMetadata) -> Optional[str]:
    """Format agent settings for CLI display.

    :param agent: Agent metadata to format.
    :type agent: AgentMetadata
    :return: Comma-separated key=value pairs or None when empty.
    :rtype: Optional[str]
    """
    if not agent.settings:
        return None
    parts = [
        f"{key}={_format_setting_value(value)}"
        for key, value in sorted(agent.settings.items())
    ]
    return ", ".join(parts)


def agent_metadata_to_event_value(agent: AgentMetadata) -> Dict[str, Any]:
    """Serialize agent metadata for event payloads.

    :param agent: Agent metadata to serialize.
    :type agent: AgentMetadata
    :return: JSON-compatible payload fragment.
    :rtype: Dict[str, Any]
    """
    return _serialize_agent_metadata(agent)


def reject_agent_metadata_in_beads_mode(agent_present: bool) -> None:
    """Reject agent metadata mutations in Beads compatibility mode.

    :param agent_present: Whether agent metadata was supplied.
    :type agent_present: bool
    :raises AgentMetadataResolutionError: When agent metadata is supplied in Beads mode.
    """
    if agent_present:
        raise AgentMetadataResolutionError(
            "agent metadata requires native Kanbus issue storage"
        )
