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
