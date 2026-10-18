"""The configuration document must stay consistent with the loader."""

from __future__ import annotations

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
