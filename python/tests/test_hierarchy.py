"""Unit tests for hierarchy validation."""

from __future__ import annotations

import pytest

from taskulus.config import DEFAULT_CONFIGURATION
from taskulus.hierarchy import (
    InvalidHierarchyError,
    get_allowed_child_types,
    validate_parent_child_relationship,
)
from taskulus.models import ProjectConfiguration


def build_configuration() -> ProjectConfiguration:
    """Build a ProjectConfiguration from defaults.

    :return: ProjectConfiguration instance.
    :rtype: ProjectConfiguration
    """
    return ProjectConfiguration.model_validate(DEFAULT_CONFIGURATION)


def test_get_allowed_child_types_returns_next_hierarchical_and_types() -> None:
    """Allowed children should include next hierarchical and non-hierarchical types."""
    configuration = build_configuration()
    allowed = get_allowed_child_types(configuration, "epic")
    assert allowed == ["task", "bug", "story", "chore"]


def test_get_allowed_child_types_returns_empty_for_non_hierarchical_parent() -> None:
    """Non-hierarchical types should not allow children."""
    configuration = build_configuration()
    assert get_allowed_child_types(configuration, "bug") == []


def test_get_allowed_child_types_returns_empty_for_last_hierarchy() -> None:
    configuration = build_configuration()
    assert get_allowed_child_types(configuration, "sub-task") == []


def test_validate_parent_child_relationship_allows_valid_pair() -> None:
    """Valid parent-child pairs should not raise."""
    configuration = build_configuration()
    validate_parent_child_relationship(configuration, "epic", "task")


def test_validate_parent_child_relationship_rejects_invalid_pair() -> None:
    """Invalid parent-child pairs should raise InvalidHierarchyError."""
    configuration = build_configuration()
    with pytest.raises(InvalidHierarchyError) as error:
        validate_parent_child_relationship(configuration, "task", "epic")
    assert "invalid parent-child relationship" in str(error.value)
