"""Agent assignment resolution for console snapshots."""

from __future__ import annotations

from typing import Dict, List, Optional

from kanbus.models import IssueRouterConfiguration, RouterAgentProfile


def resolve_agent_assignment(
    issue_labels: List[str],
    router_config: Optional[IssueRouterConfiguration],
) -> Optional[Dict[str, object]]:
    """Resolve agent assignment from issue labels and router configuration.

    For an issue with exactly ONE label matching agent-class: or agent-provider:,
    and a valid router configuration present, returns the assignment with safe
    effective settings. Returns None if label is missing, invalid, ambiguous, or
    if no router is configured.

    :param issue_labels: List of issue labels.
    :type issue_labels: List[str]
    :param router_config: Router configuration.
    :type router_config: Optional[IssueRouterConfiguration]
    :return: Agent assignment dict or None.
    :rtype: Optional[Dict[str, object]]
    """
    if router_config is None:
        return None

    routing_labels = [
        label
        for label in issue_labels
        if label.startswith(("agent-class:", "agent-provider:"))
    ]

    if len(routing_labels) != 1:
        return None

    routing_label = routing_labels[0]

    if routing_label.startswith("agent-class:"):
        class_name = routing_label[len("agent-class:") :]
        if not class_name or class_name not in router_config.classes:
            return None

        agent_class = router_config.classes[class_name]
        if not agent_class.providers:
            return None

        provider_key = agent_class.providers[0]
        if provider_key not in router_config.providers:
            return None

        profile = router_config.providers[provider_key]
        return {
            "kind": "class",
            "name": class_name,
            "provider_profile": provider_key,
            "effective": _build_effective_settings(profile),
        }

    if routing_label.startswith("agent-provider:"):
        provider_name = routing_label[len("agent-provider:") :]
        if not provider_name or provider_name not in router_config.providers:
            return None

        profile = router_config.providers[provider_name]
        return {
            "kind": "provider",
            "name": provider_name,
            "provider_profile": provider_name,
            "effective": _build_effective_settings(profile),
        }

    return None


def _build_effective_settings(profile: RouterAgentProfile) -> Dict[str, object]:
    """Build safe effective settings from a router profile.

    Includes only platform, model (if set), and settings.service_tier (if set).
    Excludes command, args, and env (secrets).

    :param profile: Router agent profile.
    :type profile: RouterAgentProfile
    :return: Safe effective settings dict.
    :rtype: Dict[str, object]
    """
    effective: Dict[str, object] = {"platform": profile.adapter}

    if profile.model:
        effective["model"] = profile.model

    if profile.service_tier:
        effective["settings"] = {"service_tier": profile.service_tier}

    return effective


def redact_router_config(config_dump: Dict[str, object]) -> Dict[str, object]:
    """Redact router configuration secrets from a config dump.

    Sets provider args to empty list and replaces all env values with "[redacted]".
    All other config remains unchanged.

    :param config_dump: Configuration dump (from model_dump()).
    :type config_dump: Dict[str, object]
    :return: Redacted configuration dump.
    :rtype: Dict[str, object]
    """
    redacted = dict(config_dump)

    if "router" not in redacted:
        return redacted

    router = redacted["router"]
    if not isinstance(router, dict):
        return redacted

    if "providers" not in router:
        return redacted

    providers = router["providers"]
    if not isinstance(providers, dict):
        return redacted

    for provider_key, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            continue

        provider_config_copy = dict(provider_config)
        provider_config_copy["args"] = []

        if "env" in provider_config_copy and isinstance(
            provider_config_copy["env"], dict
        ):
            env_copy = dict(provider_config_copy["env"])
            for env_key in env_copy:
                env_copy[env_key] = "[redacted]"
            provider_config_copy["env"] = env_copy

        providers[provider_key] = provider_config_copy

    return redacted
