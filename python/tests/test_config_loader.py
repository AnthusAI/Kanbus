from __future__ import annotations

from pathlib import Path

from kanbus.config_loader import load_project_configuration, resolve_board_name


def _write_minimal_config(path: Path) -> None:
    path.write_text("project_key: kanbus\n", encoding="utf-8")


def test_load_configuration_accepts_mqtt_override_fields(tmp_path: Path) -> None:
    config_path = tmp_path / ".kanbus.yml"
    _write_minimal_config(config_path)
    (tmp_path / ".kanbus.override.yml").write_text(
        "\n".join(
            [
                "realtime:",
                "  mqtt_custom_authorizer_name: token-auth",
                "  mqtt_api_token: token-value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    configuration = load_project_configuration(config_path)

    assert configuration.realtime.mqtt_custom_authorizer_name == "token-auth"
    assert configuration.realtime.mqtt_api_token == "token-value"


def test_load_configuration_applies_mqtt_environment_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / ".kanbus.yml"
    _write_minimal_config(config_path)
    monkeypatch.setenv("KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME", "env-auth")
    monkeypatch.setenv("KANBUS_REALTIME_MQTT_API_TOKEN", "env-token")

    configuration = load_project_configuration(config_path)

    assert configuration.realtime.mqtt_custom_authorizer_name == "env-auth"
    assert configuration.realtime.mqtt_api_token == "env-token"


def test_resolve_board_name_prefers_configured_name(tmp_path: Path) -> None:
    assert resolve_board_name("Chattic.us", tmp_path, "kbs") == "Chattic.us"


def test_resolve_board_name_trims_configured_name(tmp_path: Path) -> None:
    assert resolve_board_name("  Kanbus  ", tmp_path, "kbs") == "Kanbus"


def test_resolve_board_name_uses_folder_when_name_blank(tmp_path: Path) -> None:
    board_root = tmp_path / "Chattic.us"
    board_root.mkdir()
    assert resolve_board_name("  ", board_root, "chatticus") == "Chattic.us"


def test_resolve_board_name_uses_project_key_when_folder_empty() -> None:
    assert resolve_board_name(None, Path("/"), "kanbus") == "kanbus"
