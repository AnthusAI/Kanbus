from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.config_loader import ConfigurationError
from kanbus.file_io import InitializationError
from kanbus.project import ProjectMarkerError


def _run_with_input(args: list[str], input_text: str | None = None) -> object:
    return CliRunner().invoke(cli.cli, args, input=input_text)


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_setup_agents_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        cli, "ensure_agents_file", lambda root, force: calls.append(("agents", force))
    )
    monkeypatch.setattr(
        cli, "_ensure_project_guard_files", lambda root: calls.append(("guards", False))
    )

    result = _run(["setup", "agents", "--force"])
    assert result.exit_code == 0
    assert calls == [("agents", True), ("guards", False)]


def test_init_command_and_setup_agents_prompt_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "ensure_git_repository", lambda _root: None)
    monkeypatch.setattr(cli, "_maybe_run_setup_agents", lambda _root: None)
    monkeypatch.setattr(cli, "_maybe_print_ai_credentials_hint", lambda _root: None)
    init_calls: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        cli,
        "initialize_project",
        lambda root, create_local: init_calls.append((root, create_local)),
    )

    cli.init.callback(True)
    assert init_calls == [(tmp_path, True)]

    monkeypatch.setattr(
        cli,
        "initialize_project",
        lambda *_a, **_k: (_ for _ in ()).throw(InitializationError("init fail")),
    )
    with pytest.raises(cli.click.ClickException, match="init fail"):
        cli.init.callback(False)


def test_maybe_run_setup_agents_prompt_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    called: list[tuple[Path, bool]] = []
    monkeypatch.setattr(
        cli,
        "ensure_agents_file",
        lambda root, force=False: called.append((root, force)),
    )
    cli._maybe_run_setup_agents(tmp_path)
    assert called == []

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: False)
    cli._maybe_run_setup_agents(tmp_path)
    assert called == []

    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: True)
    cli._maybe_run_setup_agents(tmp_path)
    assert called == [(tmp_path, False)]


def test_repair_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(ProjectMarkerError("pm fail")),
    )
    with pytest.raises(cli.click.ClickException, match="pm fail"):
        cli.repair.callback(True)

    monkeypatch.setattr(
        cli,
        "detect_repairable_project_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(ConfigurationError("cfg fail")),
    )
    with pytest.raises(cli.click.ClickException, match="cfg fail"):
        cli.repair.callback(True)

    messages: list[str] = []
    monkeypatch.setattr(cli.click, "echo", lambda message: messages.append(message))
    monkeypatch.setattr(cli, "detect_repairable_project_issues", lambda *_a, **_k: None)
    cli.repair.callback(True)
    assert "already healthy" in messages[-1]

    plan = SimpleNamespace(
        missing_project_dir=True,
        missing_issues_dir=True,
        missing_events_dir=True,
    )
    monkeypatch.setattr(cli, "detect_repairable_project_issues", lambda *_a, **_k: plan)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    with pytest.raises(cli.click.ClickException, match="re-run with --yes"):
        cli.repair.callback(False)

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: False)
    cli.repair.callback(False)
    assert "Repair cancelled." in messages[-1]

    monkeypatch.setattr(cli.click, "confirm", lambda *_a, **_k: True)
    repaired: list[Path] = []
    monkeypatch.setattr(
        cli, "repair_project_structure", lambda root, _plan: repaired.append(root)
    )
    cli.repair.callback(False)
    assert "Project structure repaired." in messages[-1]
    assert repaired == [tmp_path]


def test_resolve_beads_mode_projectmarker_and_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = cli.click.Context(cli.click.Command("kanbus"))
    context.get_parameter_source = lambda _name: cli.click.core.ParameterSource.DEFAULT

    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ProjectMarkerError("no project")),
    )
    assert cli._resolve_beads_mode(context, beads_mode=False) == (False, False)

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("bad config")),
    )
    with pytest.raises(cli.click.ClickException, match="bad config"):
        cli._resolve_beads_mode(context, beads_mode=False)


def test_setup_ai_invalid_variable_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _run(["setup", "ai", "--variable", "not-valid", "--key", "x"])
    assert result.exit_code != 0
    assert "invalid variable name" in result.output


def test_setup_ai_with_key_option_saves_and_does_not_echo_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run(["setup", "ai", "--key", "super-secret-value"])
    assert result.exit_code == 0, result.output
    assert "Saved OPENAI_API_KEY to ~/.kanbus.env" in result.output
    assert "super-secret-value" not in result.output
    congregation_file = home / ".kanbus.env"
    assert "OPENAI_API_KEY=super-secret-value" in congregation_file.read_text(
        encoding="utf-8"
    )
    import stat

    mode = stat.S_IMODE(congregation_file.stat().st_mode)
    assert mode == 0o600


def test_setup_ai_from_stdin_reads_first_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run_with_input(["setup", "ai", "--from-stdin"], "stdin-value\n")
    assert result.exit_code == 0, result.output
    congregation_file = home / ".kanbus.env"
    assert "OPENAI_API_KEY=stdin-value" in congregation_file.read_text(encoding="utf-8")


def test_setup_ai_non_interactive_without_key_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run(["setup", "ai"])
    assert result.exit_code != 0
    assert "no key provided" in result.output


def test_setup_ai_empty_key_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run(["setup", "ai", "--key", "   "])
    assert result.exit_code != 0
    assert "API key value is empty" in result.output


def test_setup_ai_prompts_interactively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli, "_terminal_is_interactive", lambda: True)
    monkeypatch.setattr(cli.click, "prompt", lambda *_a, **_k: "prompted-value")
    result = _run(["setup", "ai"])
    assert result.exit_code == 0, result.output
    congregation_file = home / ".kanbus.env"
    assert "OPENAI_API_KEY=prompted-value" in congregation_file.read_text(
        encoding="utf-8"
    )


def test_setup_ai_write_failure_is_click_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        cli,
        "write_congregation_env_value",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")),
    )
    result = _run(["setup", "ai", "--key", "value"])
    assert result.exit_code != 0
    assert "disk full" in result.output


def test_setup_ai_status_outside_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    result = _run(["setup", "ai", "--status"])
    assert result.exit_code == 0, result.output
    assert "OPENAI_API_KEY: not set" in result.output
    assert "setup ai" in result.output
    assert "Lookup order:" in result.output


def test_setup_ai_status_reports_congregation_file_without_leaking_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (home / ".kanbus.env").write_text(
        "OPENAI_API_KEY=secret-value-123\n", encoding="utf-8"
    )
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    result = _run(["setup", "ai", "--status"])
    assert result.exit_code == 0, result.output
    assert "OPENAI_API_KEY: ~/.kanbus.env" in result.output
    assert "secret-value-123" not in result.output


def test_print_ai_credential_status_falls_back_when_configuration_path_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    for exc in (ProjectMarkerError("no project"), ConfigurationError("bad config")):
        monkeypatch.setattr(
            cli,
            "get_configuration_path",
            lambda _root, exc=exc: (_ for _ in ()).throw(exc),
        )
        cli._print_credential_status(
            "OPENAI_API_KEY",
            "Run 'kbs setup ai' (or 'kanbus setup ai') to store one in ~/.kanbus.env.",
        )
        output = capsys.readouterr().out
        assert "OPENAI_API_KEY: not set" in output


def test_maybe_print_ai_credentials_hint_prints_when_no_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    messages: list[str] = []
    monkeypatch.setattr(
        cli.click,
        "echo",
        lambda message="", err=False: messages.append(message),
    )
    cli._maybe_print_ai_credentials_hint(tmp_path)
    assert any("setup ai" in message for message in messages)


def test_maybe_print_ai_credentials_hint_silent_when_key_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    messages: list[str] = []
    monkeypatch.setattr(
        cli.click,
        "echo",
        lambda message="", err=False: messages.append(message),
    )
    cli._maybe_print_ai_credentials_hint(tmp_path)
    assert messages == []


def test_setup_env_invalid_variable_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _run(["setup", "env", "not-a-variable", "--value", "x"])
    assert result.exit_code != 0
    assert "invalid variable name" in result.output


def test_setup_env_with_value_option_saves_and_preserves_other_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    congregation_file = home / ".kanbus.env"
    congregation_file.write_text(
        "# machine-wide settings\nOPENAI_API_KEY=keep-me\n"
        "KANBUS_REALTIME_BROKER=mqtt://127.0.0.1:1883\n",
        encoding="utf-8",
    )
    result = _run(
        [
            "setup",
            "env",
            "KANBUS_REALTIME_BROKER",
            "--value",
            "mqtts://broker.example.com:8883",
        ]
    )
    assert result.exit_code == 0, result.output
    assert "Saved KANBUS_REALTIME_BROKER to ~/.kanbus.env" in result.output
    content = congregation_file.read_text(encoding="utf-8")
    assert "# machine-wide settings" in content
    assert "OPENAI_API_KEY=keep-me" in content
    assert "KANBUS_REALTIME_BROKER=mqtts://broker.example.com:8883" in content
    assert "mqtt://127.0.0.1:1883" not in content
    import stat

    mode = stat.S_IMODE(congregation_file.stat().st_mode)
    assert mode == 0o600


def test_setup_env_from_stdin_reads_first_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run_with_input(
        ["setup", "env", "KANBUS_REALTIME_BROKER", "--from-stdin"],
        "mqtt://stdin-value:1883\n",
    )
    assert result.exit_code == 0, result.output
    congregation_file = home / ".kanbus.env"
    assert (
        "KANBUS_REALTIME_BROKER=mqtt://stdin-value:1883"
        in congregation_file.read_text(encoding="utf-8")
    )


def test_setup_env_non_interactive_without_value_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run(["setup", "env", "KANBUS_REALTIME_BROKER"])
    assert result.exit_code != 0
    assert "no value provided" in result.output


def test_setup_env_empty_value_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    result = _run(["setup", "env", "KANBUS_REALTIME_BROKER", "--value", "   "])
    assert result.exit_code != 0
    assert "value is empty" in result.output


def test_setup_env_prompts_interactively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli, "_terminal_is_interactive", lambda: True)
    monkeypatch.setattr(cli.click, "prompt", lambda *_a, **_k: "prompted-value")
    result = _run(["setup", "env", "KANBUS_REALTIME_BROKER"])
    assert result.exit_code == 0, result.output
    congregation_file = home / ".kanbus.env"
    assert "KANBUS_REALTIME_BROKER=prompted-value" in congregation_file.read_text(
        encoding="utf-8"
    )


def test_setup_env_status_not_set_includes_command_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KANBUS_REALTIME_BROKER", raising=False)
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    result = _run(["setup", "env", "KANBUS_REALTIME_BROKER", "--status"])
    assert result.exit_code == 0, result.output
    assert "KANBUS_REALTIME_BROKER: not set" in result.output
    assert "setup env KANBUS_REALTIME_BROKER" in result.output
    assert "Lookup order:" in result.output


def test_setup_env_status_reports_congregation_file_without_leaking_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KANBUS_REALTIME_MQTT_API_TOKEN", raising=False)
    (home / ".kanbus.env").write_text(
        "KANBUS_REALTIME_MQTT_API_TOKEN=secret-token-456\n", encoding="utf-8"
    )
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    result = _run(["setup", "env", "KANBUS_REALTIME_MQTT_API_TOKEN", "--status"])
    assert result.exit_code == 0, result.output
    assert "KANBUS_REALTIME_MQTT_API_TOKEN: ~/.kanbus.env" in result.output
    assert "secret-token-456" not in result.output


def test_setup_env_write_failure_is_click_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        cli,
        "write_congregation_env_value",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")),
    )
    result = _run(["setup", "env", "KANBUS_REALTIME_BROKER", "--value", "value"])
    assert result.exit_code != 0
    assert "disk full" in result.output
