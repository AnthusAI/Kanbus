from __future__ import annotations

import os
from pathlib import Path

from pydantic import ValidationError

from kanbus import config_loader
from kanbus.models import RealtimeConfig


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


def test_load_configuration_data_handles_empty_and_invalid_mapping(tmp_path: Path) -> None:
    empty_cfg = tmp_path / "empty.yml"
    empty_cfg.write_text("", encoding="utf-8")
    assert config_loader._load_configuration_data(empty_cfg) == {}

    non_mapping_cfg = tmp_path / "list.yml"
    non_mapping_cfg.write_text("- one\n- two\n", encoding="utf-8")
    try:
        config_loader._load_configuration_data(non_mapping_cfg)
    except config_loader.ConfigurationError as error:
        assert "configuration must be a mapping" in str(error)
    else:
        raise AssertionError("expected ConfigurationError")


def test_load_override_configuration_handles_missing_invalid_and_non_mapping(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.override.yml"
    assert config_loader._load_override_configuration(missing) == {}

    invalid = tmp_path / "invalid.override.yml"
    invalid.write_text("x: [\n", encoding="utf-8")
    try:
        config_loader._load_override_configuration(invalid)
    except config_loader.ConfigurationError as error:
        assert "override configuration is invalid" in str(error)
    else:
        raise AssertionError("expected ConfigurationError")

    non_mapping = tmp_path / "list.override.yml"
    non_mapping.write_text("- one\n", encoding="utf-8")
    try:
        config_loader._load_override_configuration(non_mapping)
    except config_loader.ConfigurationError as error:
        assert "override configuration must be a mapping" in str(error)
    else:
        raise AssertionError("expected ConfigurationError")


def test_validate_canonical_config_overrides_rejects_hierarchy_override(
    tmp_path: Path,
) -> None:
    cfg = tmp_path / "kanbus.yml"
    cfg.write_text("project_key: k\n", encoding="utf-8")
    try:
        config_loader._validate_canonical_config_overrides(
            cfg, {"hierarchy": ["epic", "task"]}
        )
    except config_loader.ConfigurationError as error:
        assert "hierarchy is fixed" in str(error)
    else:
        raise AssertionError("expected ConfigurationError")


def test_apply_environment_overrides_populates_nested_realtime_overlay(monkeypatch) -> None:
    monkeypatch.setenv("KANBUS_REALTIME_TRANSPORT", "mqtt")
    monkeypatch.setenv("KANBUS_REALTIME_BROKER", "mqtt://localhost:1883")
    monkeypatch.setenv("KANBUS_REALTIME_AUTOSTART", "true")
    monkeypatch.setenv("KANBUS_REALTIME_KEEPALIVE", "false")
    monkeypatch.setenv("KANBUS_REALTIME_UDS_SOCKET_PATH", "/tmp/kanbus.sock")
    monkeypatch.setenv("KANBUS_REALTIME_TOPICS_PROJECT_EVENTS", "projects/{project}/events")
    monkeypatch.setenv("KANBUS_OVERLAY_ENABLED", "1")
    monkeypatch.setenv("KANBUS_OVERLAY_TTL_S", "42")

    merged: dict = {}
    config_loader._apply_environment_overrides(merged)
    assert merged["realtime"]["transport"] == "mqtt"
    assert merged["realtime"]["broker"] == "mqtt://localhost:1883"
    assert merged["realtime"]["autostart"] is True
    assert merged["realtime"]["keepalive"] is False
    assert merged["realtime"]["uds_socket_path"] == "/tmp/kanbus.sock"
    assert merged["realtime"]["topics"]["project_events"] == "projects/{project}/events"
    assert merged["overlay"]["enabled"] is True
    assert merged["overlay"]["ttl_s"] == 42


def test_has_unknown_fields_detects_extra_forbidden() -> None:
    try:
        RealtimeConfig.model_validate({"unknown_field": "x"})
    except ValidationError as error:
        assert config_loader._has_unknown_fields(error) is True
    else:
        raise AssertionError("expected ValidationError")
