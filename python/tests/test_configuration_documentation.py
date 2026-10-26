"""The configuration document must stay consistent with the loader."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

from kanbus.config_loader import validate_project_configuration
from kanbus.models import ProjectConfiguration

CONFIGURATION_DOCUMENT = (
    Path(__file__).resolve().parents[2] / "docs" / "CONFIGURATION.md"
)


def test_minimal_configuration_example_is_valid() -> None:
    document_text = CONFIGURATION_DOCUMENT.read_text()
    example_match = re.search(
        r"## Minimal configuration\n\n```yaml\n(.*?)```", document_text, re.DOTALL
    )
    assert example_match is not None
    configuration = ProjectConfiguration.model_validate(
        yaml.safe_load(example_match.group(1))
    )
    assert validate_project_configuration(configuration) == []


def load_generator_module():
    generator_path = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "generate_configuration_reference.py"
    )
    specification = importlib.util.spec_from_file_location(
        "generate_configuration_reference", generator_path
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_every_configuration_yaml_block_loads() -> None:
    generator = load_generator_module()
    failures = generator.validate_documented_yaml_blocks(
        CONFIGURATION_DOCUMENT.read_text()
    )
    assert failures == []


def test_invalid_configuration_block_is_reported() -> None:
    generator = load_generator_module()
    invalid_document = (
        "```yaml\nproject_key: KAN\nissue_types: [bug]\n"
        "priorities: [critical, high]\n```\n"
    )
    failures = generator.validate_documented_yaml_blocks(invalid_document)
    assert len(failures) == 1
    assert "issue_types" in failures[0] or "unknown configuration" in failures[0]


def test_non_configuration_block_is_ignored() -> None:
    generator = load_generator_module()
    assert generator.validate_documented_yaml_blocks("```yaml\nfoo: bar\n```\n") == []
