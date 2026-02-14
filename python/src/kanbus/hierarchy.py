"""Hierarchy validation for parent-child relationships."""

from __future__ import annotations

from typing import List

from kanbus.models import ProjectConfiguration


class InvalidHierarchyError(RuntimeError):
    """Raised when a parent-child relationship violates the hierarchy."""


def get_allowed_child_types(
    configuration: ProjectConfiguration,
    parent_type: str,
) -> List[str]:
    """Return the allowed child types for a parent issue type.

    :param configuration: Project configuration containing hierarchy rules.
    :type configuration: ProjectConfiguration
    :param parent_type: Parent issue type to validate.
    :type parent_type: str
    :return: Allowed child types.
    :rtype: List[str]
    """
    if parent_type not in configuration.hierarchy:
        return []

    parent_index = configuration.hierarchy.index(parent_type)
    if parent_index >= len(configuration.hierarchy) - 1:
        return []

    next_hierarchical = configuration.hierarchy[parent_index + 1]
    return [next_hierarchical, *configuration.types]


def validate_parent_child_relationship(
    configuration: ProjectConfiguration,
    parent_type: str,
    child_type: str,
) -> None:
    """Validate that a parent-child relationship is permitted.

    :param configuration: Project configuration containing hierarchy rules.
    :type configuration: ProjectConfiguration
    :param parent_type: Parent issue type.
    :type parent_type: str
    :param child_type: Child issue type.
    :type child_type: str
    :raises InvalidHierarchyError: If the relationship is not permitted.
    """
    allowed_child_types = get_allowed_child_types(configuration, parent_type)
    if child_type not in allowed_child_types:
        raise InvalidHierarchyError(
            f"invalid parent-child relationship: '{parent_type}' "
            f"cannot have child '{child_type}'"
        )
