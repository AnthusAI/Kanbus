"""Tests for configuration loader validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from taskulus.config import DEFAULT_CONFIGURATION, write_default_configuration
from taskulus.config_loader import ConfigurationError, load_project_configuration


def test_load_project_configuration_success(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_default_configuration(config_path)
    config = load_project_configuration(config_path)
    assert config.prefix == DEFAULT_CONFIGURATION["prefix"]


def test_load_project_configuration_requires_hierarchy(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "prefix: tsk\nhierarchy: []\ntypes: []\nworkflows: {default: {open: []}}\ninitial_status: open\npriorities: {2: medium}\ndefault_priority: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="hierarchy must not be empty"):
        load_project_configuration(config_path)


def test_load_project_configuration_rejects_duplicate_types(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "prefix: tsk\nhierarchy: [task]\ntypes: [task]\nworkflows: {default: {open: []}}\ninitial_status: open\npriorities: {2: medium}\ndefault_priority: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="duplicate type name"):
        load_project_configuration(config_path)


def test_load_project_configuration_requires_default_workflow(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "prefix: tsk\nhierarchy: [task]\ntypes: []\nworkflows: {}\ninitial_status: open\npriorities: {2: medium}\ndefault_priority: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="default workflow is required"):
        load_project_configuration(config_path)


def test_load_project_configuration_requires_default_priority_in_map(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "prefix: tsk\nhierarchy: [task]\ntypes: []\nworkflows: {default: {open: []}}\ninitial_status: open\npriorities: {1: high}\ndefault_priority: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigurationError, match="default priority must be in priorities map"
    ):
        load_project_configuration(config_path)
