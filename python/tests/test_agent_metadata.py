from __future__ import annotations

import pytest

from kanbus.agent_metadata import (
    AgentMetadataRequest,
    AgentMetadataResolutionError,
    build_agent_metadata,
    reject_agent_metadata_in_beads_mode,
    resolve_agent_metadata,
)


def test_build_agent_metadata_returns_none_when_absent() -> None:
    assert build_agent_metadata(None, None, {}) is None


def test_build_agent_metadata_requires_platform_and_model_together() -> None:
    with pytest.raises(AgentMetadataResolutionError) as error:
        build_agent_metadata("cursor", None, {})
    assert str(error.value) == "agent metadata requires both platform and model"


def test_reject_secret_like_settings_keys() -> None:
    with pytest.raises(AgentMetadataResolutionError) as error:
        build_agent_metadata("cursor", "composer-2.5", {"openai_api_key": "secret"})
    assert str(error.value) == "agent settings must not contain secret-like keys"


def test_resolve_agent_metadata_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KANBUS_AGENT_PLATFORM", "cursor")
    monkeypatch.setenv("KANBUS_AGENT_MODEL", "composer-2.5")
    metadata = resolve_agent_metadata(AgentMetadataRequest())
    assert metadata is not None
    assert metadata.platform == "cursor"
    assert metadata.model == "composer-2.5"


def test_reject_agent_metadata_in_beads_mode() -> None:
    with pytest.raises(AgentMetadataResolutionError) as error:
        reject_agent_metadata_in_beads_mode(True)
    assert str(error.value) == "agent metadata requires native Kanbus issue storage"


def test_invalid_agent_platform() -> None:
    with pytest.raises(AgentMetadataResolutionError) as error:
        build_agent_metadata("bad platform!", "composer-2.5", {})
    assert str(error.value) == "invalid agent platform"


def test_unknown_agent_settings_key() -> None:
    with pytest.raises(AgentMetadataResolutionError) as error:
        build_agent_metadata("cursor", "composer-2.5", {"fast": True})
    assert str(error.value) == "unknown agent settings key"


def test_invalid_agent_settings_json_not_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KANBUS_AGENT_PLATFORM", "cursor")
    monkeypatch.setenv("KANBUS_AGENT_MODEL", "composer-2.5")
    monkeypatch.setenv("KANBUS_AGENT_SETTINGS", '["not-an-object"]')
    with pytest.raises(AgentMetadataResolutionError) as error:
        resolve_agent_metadata(AgentMetadataRequest())
    assert str(error.value) == "invalid agent settings JSON: expected object"


def test_invalid_agent_settings_json_syntax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KANBUS_AGENT_PLATFORM", "cursor")
    monkeypatch.setenv("KANBUS_AGENT_MODEL", "composer-2.5")
    monkeypatch.setenv("KANBUS_AGENT_SETTINGS", "not-json")
    with pytest.raises(AgentMetadataResolutionError) as error:
        resolve_agent_metadata(AgentMetadataRequest())
    assert "invalid agent settings JSON" in str(error.value)


def test_agent_metadata_exceeds_maximum_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("kanbus.agent_metadata.MAX_AGENT_METADATA_BYTES", 10)
    with pytest.raises(AgentMetadataResolutionError) as error:
        build_agent_metadata("cursor", "composer-2.5", {})
    assert str(error.value) == "agent metadata exceeds maximum size"


def test_format_agent_settings_display() -> None:
    from kanbus.agent_metadata import format_agent_settings_display
    from kanbus.models import AgentMetadata, AgentSettings

    empty = AgentMetadata(platform="cursor", model="composer-2.5")
    assert format_agent_settings_display(empty) is None

    with_settings = AgentMetadata(
        platform="cursor",
        model="composer-2.5",
        settings=AgentSettings(thinking_level="high", temperature=0.5),
    )
    display = format_agent_settings_display(with_settings)
    assert display is not None
    assert "thinking_level=high" in display
    assert "temperature=0.5" in display
