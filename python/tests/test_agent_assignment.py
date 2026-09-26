"""Unit tests for agent_assignment module."""

from __future__ import annotations


from kanbus.agent_assignment import (
    redact_router_config,
    resolve_agent_assignment,
)
from kanbus.models import (
    IssueRouterConfiguration,
    RouterAgentClass,
    RouterAgentProfile,
    RouterLimits,
    RouterWorkflowRoles,
)


def make_router(
    providers: dict | None = None,
    classes: dict | None = None,
) -> IssueRouterConfiguration:
    if providers is None:
        providers = {"default": RouterAgentProfile(adapter="codex")}
    if classes is None:
        classes = {}

    return IssueRouterConfiguration(
        workflow=RouterWorkflowRoles(
            pending="backlog",
            active="in_progress",
            review="review",
            blocked="blocked",
            terminal=["closed"],
        ),
        limits=RouterLimits(
            project_wip=10,
            review_wip=5,
        ),
        providers=providers,
        classes=classes,
    )


def test_resolve_class_label_with_model_and_tier() -> None:
    profile = RouterAgentProfile(
        adapter="opencode",
        model="anthropic/claude-opus",
        service_tier="flex",
    )
    router = make_router(
        providers={"codex-default": profile},
        classes={
            "implementation": RouterAgentClass(
                providers=["codex-default"],
            )
        },
    )

    labels = ["agent-class:implementation"]
    result = resolve_agent_assignment(labels, router)

    assert result is not None
    assert result["kind"] == "class"
    assert result["name"] == "implementation"
    assert result["provider_profile"] == "codex-default"
    assert result["effective"]["platform"] == "opencode"
    assert result["effective"]["model"] == "anthropic/claude-opus"
    assert result["effective"]["settings"]["service_tier"] == "flex"


def test_resolve_provider_label_with_no_model_or_tier() -> None:
    profile = RouterAgentProfile(
        adapter="codex",
    )
    router = make_router(
        providers={"plain": profile},
        classes={},
    )

    labels = ["agent-provider:plain"]
    result = resolve_agent_assignment(labels, router)

    assert result is not None
    assert result["kind"] == "provider"
    assert result["name"] == "plain"
    assert result["provider_profile"] == "plain"
    assert result["effective"]["platform"] == "codex"
    assert "model" not in result["effective"]
    assert "settings" not in result["effective"]


def test_unknown_class_returns_none() -> None:
    router = make_router()

    labels = ["agent-class:unknown"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_unknown_provider_returns_none() -> None:
    router = make_router()

    labels = ["agent-provider:unknown"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_two_routing_labels_returns_none() -> None:
    profile = RouterAgentProfile(adapter="codex")
    router = make_router(
        providers={"codex-default": profile},
        classes={
            "implementation": RouterAgentClass(
                providers=["codex-default"],
            )
        },
    )

    labels = ["agent-class:implementation", "agent-provider:codex-default"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_no_routing_labels_returns_none() -> None:
    router = make_router()

    labels = ["other-label", "another-label"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_no_router_config_returns_none() -> None:
    labels = ["agent-class:implementation"]
    result = resolve_agent_assignment(labels, None)

    assert result is None


def test_empty_class_name_returns_none() -> None:
    router = make_router()

    labels = ["agent-class:"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_empty_provider_name_returns_none() -> None:
    router = make_router()

    labels = ["agent-provider:"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_class_profile_not_found_returns_none() -> None:
    router = make_router(
        classes={
            "broken": RouterAgentClass(
                providers=["missing-profile"],
            )
        },
    )

    labels = ["agent-class:broken"]
    result = resolve_agent_assignment(labels, router)

    assert result is None


def test_deterministic_class_resolution() -> None:
    b_profile = RouterAgentProfile(adapter="codex")
    a_profile = RouterAgentProfile(adapter="codex")

    router = make_router(
        providers={"b-profile": b_profile, "a-profile": a_profile},
        classes={
            "multi": RouterAgentClass(
                providers=["b-profile", "a-profile"],
            )
        },
    )

    labels = ["agent-class:multi"]
    result = resolve_agent_assignment(labels, router)

    assert result is not None
    assert result["provider_profile"] == "b-profile"


def test_redact_router_config_args_and_env() -> None:
    config = {
        "name": "test",
        "router": {
            "providers": {
                "codex-default": {
                    "adapter": "codex",
                    "args": ["--api-key", "sk-secret"],
                    "env": {"OPENAI_API_KEY": "sk-live-secret", "OTHER_VAR": "value"},
                    "model": "gpt-5.6-luna",
                }
            }
        },
    }

    result = redact_router_config(config)

    assert result["router"]["providers"]["codex-default"]["args"] == []
    assert (
        result["router"]["providers"]["codex-default"]["env"]["OPENAI_API_KEY"]
        == "[redacted]"
    )
    assert (
        result["router"]["providers"]["codex-default"]["env"]["OTHER_VAR"]
        == "[redacted]"
    )
    assert result["router"]["providers"]["codex-default"]["model"] == "gpt-5.6-luna"


def test_redact_router_config_no_router() -> None:
    config = {"name": "test"}
    result = redact_router_config(config)
    assert result == config


def test_redact_router_config_no_providers() -> None:
    config = {"name": "test", "router": {"classes": {}}}
    result = redact_router_config(config)
    assert result == config


def test_redact_router_config_preserves_other_fields() -> None:
    config = {
        "name": "test",
        "project_key": "test-proj",
        "router": {
            "enabled": True,
            "providers": {
                "codex-default": {
                    "adapter": "codex",
                    "args": ["--api-key", "sk-secret"],
                    "env": {"OPENAI_API_KEY": "sk-live-secret"},
                }
            },
        },
    }

    result = redact_router_config(config)

    assert result["name"] == "test"
    assert result["project_key"] == "test-proj"
    assert result["router"]["enabled"] is True
    assert result["router"]["providers"]["codex-default"]["adapter"] == "codex"
    assert result["router"]["providers"]["codex-default"]["args"] == []
    assert (
        result["router"]["providers"]["codex-default"]["env"]["OPENAI_API_KEY"]
        == "[redacted]"
    )


def test_redact_router_config_with_invalid_providers_type() -> None:
    config = {"name": "test", "router": {"providers": "not-a-dict"}}
    result = redact_router_config(config)
    assert result == config


def test_redact_router_config_with_invalid_env_type() -> None:
    config = {
        "name": "test",
        "router": {
            "providers": {
                "codex-default": {
                    "adapter": "codex",
                    "args": ["--api-key", "sk-secret"],
                    "env": "not-a-dict",
                }
            }
        },
    }

    result = redact_router_config(config)

    assert result["router"]["providers"]["codex-default"]["args"] == []
    assert result["router"]["providers"]["codex-default"]["env"] == "not-a-dict"
