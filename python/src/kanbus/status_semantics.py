"""Semantic status categories for workflow business logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from kanbus.models import ProjectConfiguration
from kanbus.status_semantic_defaults import CANONICAL_SEMANTIC_CATEGORIES

SEMANTIC_TODO = "todo"
SEMANTIC_IN_PROGRESS = "in_progress"
SEMANTIC_IN_REVIEW = "in_review"
SEMANTIC_BLOCKED = "blocked"
SEMANTIC_DONE = "done"

VALID_SEMANTIC_CATEGORIES = set(CANONICAL_SEMANTIC_CATEGORIES)

ROUTER_LIFECYCLE_TRANSITIONS = (
    (SEMANTIC_TODO, SEMANTIC_IN_PROGRESS),
    (SEMANTIC_IN_PROGRESS, SEMANTIC_IN_REVIEW),
    (SEMANTIC_IN_PROGRESS, SEMANTIC_BLOCKED),
    (SEMANTIC_IN_REVIEW, SEMANTIC_IN_PROGRESS),
    (SEMANTIC_IN_REVIEW, SEMANTIC_DONE),
)


class SemanticCategoryError(ValueError):
    """Raised when a semantic category value is invalid or missing."""


def validate_semantic_category(semantic_category: str) -> None:
    """
    Validate a semantic category value.

    :param semantic_category: Category string from configuration.
    :type semantic_category: str
    :raises SemanticCategoryError: When the value is not recognized.
    """
    if semantic_category not in VALID_SEMANTIC_CATEGORIES:
        raise SemanticCategoryError(
            f"invalid semantic_category '{semantic_category}': "
            "must be one of todo, in_progress, in_review, blocked, done"
        )


def resolve_primary_status_key_for_semantic_category(
    configuration: ProjectConfiguration, semantic_category: str
) -> str:
    """
    Return the first configured status key for a semantic category.

    When multiple statuses share a category, the first entry in the configured
    statuses list wins.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param semantic_category: Semantic category to resolve.
    :type semantic_category: str
    :return: Matching status key.
    :rtype: str
    :raises SemanticCategoryError: When no status matches the category.
    """
    validate_semantic_category(semantic_category)
    for status in configuration.statuses:
        if status.semantic_category == semantic_category:
            return status.key
    raise SemanticCategoryError(
        f"no status configured with semantic_category '{semantic_category}'"
    )


def status_keys_for_semantic_category(
    configuration: ProjectConfiguration, semantic_category: str
) -> List[str]:
    """
    Return every configured status key for a semantic category.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param semantic_category: Semantic category to resolve.
    :type semantic_category: str
    :return: Matching status keys in configuration order.
    :rtype: List[str]
    :raises SemanticCategoryError: When the category value is invalid.
    """
    validate_semantic_category(semantic_category)
    return [
        status.key
        for status in configuration.statuses
        if status.semantic_category == semantic_category
    ]


def semantic_category_for_status_key(
    configuration: ProjectConfiguration, status_key: str
) -> Optional[str]:
    """
    Return the semantic category for a configured status key.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param status_key: Status key to look up.
    :type status_key: str
    :return: Semantic category when the status exists.
    :rtype: Optional[str]
    """
    for status in configuration.statuses:
        if status.key == status_key:
            return status.semantic_category
    return None


def default_color_for_semantic_category(semantic_category: str) -> str:
    """
    Return the default terminal color name for a semantic category.

    :param semantic_category: Semantic category value.
    :type semantic_category: str
    :return: Color name suitable for CLI output.
    :rtype: str
    """
    if semantic_category == SEMANTIC_TODO:
        return "cyan"
    if semantic_category in {SEMANTIC_IN_PROGRESS, SEMANTIC_IN_REVIEW}:
        return "blue"
    if semantic_category == SEMANTIC_BLOCKED:
        return "red"
    if semantic_category == SEMANTIC_DONE:
        return "green"
    return "white"


def semantic_category_for_beads_status_key(status_key: str) -> str:
    """
    Assign a semantic category when importing Beads status keys.

    :param status_key: Normalized Kanbus status key from Beads import.
    :type status_key: str
    :return: Semantic category string for the imported status.
    :rtype: str
    """
    if status_key in {"in_progress", "blocked"}:
        return SEMANTIC_IN_PROGRESS
    if status_key in {"closed", "done"}:
        return SEMANTIC_DONE
    return SEMANTIC_TODO


def map_beads_status(configuration: ProjectConfiguration, raw_status: str) -> str:
    """
    Map a Beads status value to a Kanbus status key using semantic categories.

    :param configuration: Project configuration containing semantic categories.
    :type configuration: ProjectConfiguration
    :param raw_status: Status value from Beads.
    :type raw_status: str
    :return: Resolved Kanbus status key.
    :rtype: str
    :raises SemanticCategoryError: When a semantic category cannot be resolved.
    """
    if raw_status == "in-progress":
        return resolve_primary_status_key_for_semantic_category(
            configuration, SEMANTIC_IN_PROGRESS
        )
    return raw_status


def resolve_preferred_status_key_for_semantic_category(
    configuration: ProjectConfiguration,
    semantic_category: str,
    preferred_keys: List[str],
) -> str:
    """
    Return a configured status key within a semantic category, preferring named keys.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param semantic_category: Semantic category to resolve.
    :type semantic_category: str
    :param preferred_keys: Status keys to try in order before the primary category key.
    :type preferred_keys: List[str]
    :return: Matching status key.
    :rtype: str
    :raises SemanticCategoryError: When no status matches the category.
    """
    validate_semantic_category(semantic_category)
    for preferred_key in preferred_keys:
        for status in configuration.statuses:
            if (
                status.key == preferred_key
                and status.semantic_category == semantic_category
            ):
                return preferred_key
    return resolve_primary_status_key_for_semantic_category(
        configuration, semantic_category
    )


def map_jira_status_to_key(
    configuration: ProjectConfiguration, jira_status: str
) -> str:
    """
    Map a Jira status name to a Kanbus status key using semantic categories.

    :param configuration: Project configuration containing semantic categories.
    :type configuration: ProjectConfiguration
    :param jira_status: Status name from Jira.
    :type jira_status: str
    :return: Resolved Kanbus status key.
    :rtype: str
    :raises SemanticCategoryError: When a semantic category cannot be resolved.
    """
    normalized = jira_status.lower()
    if normalized in {"to do", "open", "new"}:
        return resolve_preferred_status_key_for_semantic_category(
            configuration, SEMANTIC_TODO, ["open"]
        )
    if normalized == "backlog":
        return resolve_preferred_status_key_for_semantic_category(
            configuration, SEMANTIC_TODO, ["backlog", "open"]
        )
    if normalized == "in review" and status_keys_for_semantic_category(
        configuration, SEMANTIC_IN_REVIEW
    ):
        return resolve_primary_status_key_for_semantic_category(
            configuration, SEMANTIC_IN_REVIEW
        )
    if normalized in {"in progress", "in review", "in development"}:
        return resolve_primary_status_key_for_semantic_category(
            configuration, SEMANTIC_IN_PROGRESS
        )
    if normalized in {"done", "closed", "resolved", "complete", "completed"}:
        return resolve_preferred_status_key_for_semantic_category(
            configuration, SEMANTIC_DONE, ["closed"]
        )
    if normalized in {"blocked", "impediment"}:
        if status_keys_for_semantic_category(configuration, SEMANTIC_BLOCKED):
            return resolve_preferred_status_key_for_semantic_category(
                configuration, SEMANTIC_BLOCKED, ["blocked"]
            )
        return resolve_preferred_status_key_for_semantic_category(
            configuration, SEMANTIC_IN_PROGRESS, ["blocked"]
        )
    return resolve_preferred_status_key_for_semantic_category(
        configuration, SEMANTIC_TODO, ["open"]
    )


@dataclass(frozen=True)
class RouterStatuses:
    """The router-marked status key for each canonical semantic category.

    :param todo: Marked intake status where work waits for a router worker.
    :param in_progress: Marked status for work owned by a router worker.
    :param in_review: Marked status for work awaiting human review.
    :param blocked: Marked status for work that cannot proceed.
    :param done: Marked status for approved, completed work.
    """

    todo: str
    in_progress: str
    in_review: str
    blocked: str
    done: str

    def for_category(self, semantic_category: str) -> str:
        """
        Return the marked status key for a semantic category.

        :param semantic_category: One of the canonical semantic categories.
        :type semantic_category: str
        :return: The marked status key.
        :rtype: str
        :raises SemanticCategoryError: When the category is not canonical.
        """
        validate_semantic_category(semantic_category)
        return getattr(self, semantic_category)


def router_marked_status_keys(
    configuration: ProjectConfiguration,
) -> Dict[str, List[str]]:
    """
    Group the router-marked status keys by semantic category.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Marked status keys per category, in configuration order.
    :rtype: Dict[str, List[str]]
    """
    marked: Dict[str, List[str]] = {}
    for status in configuration.statuses:
        if status.router:
            marked.setdefault(status.semantic_category, []).append(status.key)
    return marked


def resolve_router_statuses(configuration: ProjectConfiguration) -> RouterStatuses:
    """
    Resolve the router-marked status for every canonical semantic category.

    This is the single place the router learns which configured statuses play
    each lifecycle role. A loaded, valid router configuration always resolves.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: The marked status key for each canonical category.
    :rtype: RouterStatuses
    :raises SemanticCategoryError: When a category lacks exactly one marked status.
    """
    marked = router_marked_status_keys(configuration)
    resolved: Dict[str, str] = {}
    for category in CANONICAL_SEMANTIC_CATEGORIES:
        keys = marked.get(category, [])
        if len(keys) != 1:
            raise SemanticCategoryError(
                "router requires exactly one router-marked status for "
                f'semantic category "{category}"'
            )
        resolved[category] = keys[0]
    return RouterStatuses(**resolved)
