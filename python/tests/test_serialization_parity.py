"""Serialization parity tests for shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from taskulus.models import IssueData, ProjectConfiguration

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "specs" / "fixtures"


def test_issue_serialization_matches_expected() -> None:
    """Issue JSON serialization should match the shared fixture."""
    issue_path = FIXTURES_DIR / "sample_issues" / "open_task.json"
    expected_path = FIXTURES_DIR / "expected_issue.json"

    issue = IssueData.model_validate_json(issue_path.read_text(encoding="utf-8"))
    payload = issue.model_dump(by_alias=True, mode="json")
    serialized = json.dumps(payload, sort_keys=True, indent=2)

    assert serialized.strip() == expected_path.read_text(encoding="utf-8").strip()


def test_configuration_serialization_matches_expected() -> None:
    """Configuration JSON serialization should match the shared fixture."""
    config_path = FIXTURES_DIR / "default_config.yaml"
    expected_path = FIXTURES_DIR / "expected_config.json"

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    configuration = ProjectConfiguration.model_validate(data)
    payload = configuration.model_dump(mode="json")
    serialized = json.dumps(payload, sort_keys=True, indent=2)

    assert serialized.strip() == expected_path.read_text(encoding="utf-8").strip()
