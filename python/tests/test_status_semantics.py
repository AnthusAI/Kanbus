from __future__ import annotations

import pytest

from kanbus.status_semantics import (
    SEMANTIC_DONE,
    SEMANTIC_IN_PROGRESS,
    SEMANTIC_TODO,
    SemanticCategoryError,
    default_color_for_semantic_category,
    map_beads_status,
    map_jira_status_to_key,
    resolve_preferred_status_key_for_semantic_category,
    resolve_primary_status_key_for_semantic_category,
    semantic_category_for_beads_status_key,
    semantic_category_for_status_key,
    status_keys_for_semantic_category,
    validate_semantic_category,
)

from test_helpers import build_project_configuration


def test_validate_semantic_category_rejects_unknown() -> None:
    with pytest.raises(SemanticCategoryError, match="invalid semantic_category"):
        validate_semantic_category("unknown")


def test_resolve_primary_status_key_for_semantic_category() -> None:
    configuration = build_project_configuration()
    assert (
        resolve_primary_status_key_for_semantic_category(
            configuration, SEMANTIC_IN_PROGRESS
        )
        == "in_progress"
    )


def test_resolve_primary_status_key_raises_when_category_missing() -> None:
    configuration = build_project_configuration()
    configuration.statuses = [
        status
        for status in configuration.statuses
        if status.semantic_category != SEMANTIC_DONE
    ]
    with pytest.raises(SemanticCategoryError, match="no status configured"):
        resolve_primary_status_key_for_semantic_category(configuration, SEMANTIC_DONE)


def test_status_keys_for_semantic_category_returns_all_matches() -> None:
    configuration = build_project_configuration()
    assert status_keys_for_semantic_category(
        configuration, SEMANTIC_IN_PROGRESS
    ) == ["in_progress", "blocked"]


def test_semantic_category_for_status_key() -> None:
    configuration = build_project_configuration()
    assert semantic_category_for_status_key(configuration, "blocked") == SEMANTIC_IN_PROGRESS
    assert semantic_category_for_status_key(configuration, "missing") is None


def test_default_color_for_semantic_category() -> None:
    assert default_color_for_semantic_category(SEMANTIC_TODO) == "cyan"
    assert default_color_for_semantic_category(SEMANTIC_IN_PROGRESS) == "blue"
    assert default_color_for_semantic_category(SEMANTIC_DONE) == "green"
    assert default_color_for_semantic_category("other") == "white"


def test_semantic_category_for_beads_status_key() -> None:
    assert semantic_category_for_beads_status_key("in_progress") == SEMANTIC_IN_PROGRESS
    assert semantic_category_for_beads_status_key("blocked") == SEMANTIC_IN_PROGRESS
    assert semantic_category_for_beads_status_key("closed") == SEMANTIC_DONE
    assert semantic_category_for_beads_status_key("done") == SEMANTIC_DONE
    assert semantic_category_for_beads_status_key("open") == SEMANTIC_TODO


def test_map_beads_status_maps_in_progress_alias() -> None:
    configuration = build_project_configuration()
    assert map_beads_status(configuration, "in-progress") == "in_progress"
    assert map_beads_status(configuration, "open") == "open"


def test_resolve_preferred_status_key_falls_back_to_primary() -> None:
    configuration = build_project_configuration()
    assert (
        resolve_preferred_status_key_for_semantic_category(
            configuration, SEMANTIC_TODO, ["missing"]
        )
        == "open"
    )


def test_map_jira_status_to_key_prefers_backlog_status() -> None:
    configuration = build_project_configuration()
    configuration.statuses.insert(
        0,
        configuration.statuses[0].model_copy(
            update={"key": "backlog", "name": "Backlog"}
        ),
    )
    assert map_jira_status_to_key(configuration, "Backlog") == "backlog"
