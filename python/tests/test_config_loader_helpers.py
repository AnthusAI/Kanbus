from __future__ import annotations

import os
from pathlib import Path

from kanbus import config_loader


def test_parse_bool_env_supports_common_values(monkeypatch) -> None:
    monkeypatch.setenv("K_BOOL", "yes")
    assert config_loader._parse_bool_env("K_BOOL") is True
    monkeypatch.setenv("K_BOOL", "OFF")
    assert config_loader._parse_bool_env("K_BOOL") is False
    monkeypatch.setenv("K_BOOL", "maybe")
    assert config_loader._parse_bool_env("K_BOOL") is None


def test_parse_int_env_handles_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("K_INT", "42")
    assert config_loader._parse_int_env("K_INT") == 42
    monkeypatch.setenv("K_INT", "nope")
    assert config_loader._parse_int_env("K_INT") is None


def test_load_dotenv_sets_values_without_overwriting_existing(
    tmp_path: Path, monkeypatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "# comment",
                "PLAIN=one",
                "export QUOTED=\"two\"",
                "KEEP=from_file",
                "INVALID_LINE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KEEP", "already")

    config_loader._load_dotenv(dotenv)

    assert os.environ.get("PLAIN") == "one"
    assert os.environ.get("QUOTED") == "two"
    assert os.environ.get("KEEP") == "already"


def test_normalize_virtual_projects_converts_list_to_dict() -> None:
    data = {"virtual_projects": []}
    config_loader._normalize_virtual_projects(data)
    assert data["virtual_projects"] == {}


def test_reject_legacy_fields_promotes_external_projects() -> None:
    data = {"external_projects": {"team": {"project_directory": "project"}}}
    config_loader._reject_legacy_fields(data)
    assert "external_projects" not in data
    assert "virtual_projects" in data


def test_validate_sort_rule_captures_invalid_shapes() -> None:
    errors: list[str] = []
    config_loader._validate_sort_rule("sort_order.test", "bad-preset", errors)
    config_loader._validate_sort_rule(
        "sort_order.test",
        [{"field": "bad-field", "direction": "up"}],
        errors,
    )
    config_loader._validate_sort_rule("sort_order.test", [{}], errors)

    joined = " | ".join(errors)
    assert "invalid preset" in joined
    assert "invalid field" in joined
    assert "invalid direction" in joined
    assert "missing 'field'" in joined
    assert "missing 'direction'" in joined
