from __future__ import annotations

import stat
from pathlib import Path

import pytest

from kanbus import ai_credentials


def test_missing_api_key_message_mentions_setup_ai() -> None:
    message = ai_credentials.missing_api_key_message()
    assert "OPENAI_API_KEY" in message
    assert "setup ai" in message


def test_missing_api_key_message_uses_given_variable() -> None:
    message = ai_credentials.missing_api_key_message("ANTHROPIC_API_KEY")
    assert message.startswith("ANTHROPIC_API_KEY is not set.")


def test_requires_openai_key_detects_default_and_openai_prefixed_models() -> None:
    assert ai_credentials.requires_openai_key("gpt-4o-mini") is True
    assert ai_credentials.requires_openai_key("openai/gpt-4o-mini") is True
    assert ai_credentials.requires_openai_key("anthropic/claude-3") is False
    assert ai_credentials.requires_openai_key("azure/my-deployment") is False


def test_congregation_env_display_returns_display_path() -> None:
    assert ai_credentials.congregation_env_display() == "~/.kanbus.env"


def test_describe_api_key_source_returns_enum_value() -> None:
    assert (
        ai_credentials.describe_api_key_source(ai_credentials.CredentialSource.NONE)
        == "not set"
    )


def test_read_dotenv_value_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert ai_credentials.read_dotenv_value(tmp_path / "missing.env", "KEY") is None


def test_read_dotenv_value_returns_none_when_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".env"
    path.write_text("KEY=value\n", encoding="utf-8")
    original_read_text = Path.read_text

    def patched_read_text(self: Path, *args, **kwargs) -> str:
        if self == path:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", patched_read_text)
    assert ai_credentials.read_dotenv_value(path, "KEY") is None


def test_read_dotenv_value_strips_quotes_and_uses_last_match(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        'KEY="first"\nOTHER=1\nKEY=second\n',
        encoding="utf-8",
    )
    assert ai_credentials.read_dotenv_value(path, "KEY") == "second"
    assert ai_credentials.read_dotenv_value(path, "MISSING") is None


def test_write_congregation_env_value_creates_file_with_mode_600(
    tmp_path: Path,
) -> None:
    path = tmp_path / "home" / ".kanbus.env"
    ai_credentials.write_congregation_env_value(path, "OPENAI_API_KEY", "abc123")
    assert path.read_text(encoding="utf-8") == "OPENAI_API_KEY=abc123\n"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_write_congregation_env_value_updates_in_place_preserving_other_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".kanbus.env"
    path.write_text(
        "# my keys\nOTHER_SETTING=1\nOPENAI_API_KEY=old-value\n",
        encoding="utf-8",
    )
    ai_credentials.write_congregation_env_value(path, "OPENAI_API_KEY", "new-value")
    content = path.read_text(encoding="utf-8")
    assert "# my keys" in content
    assert "OTHER_SETTING=1" in content
    assert "OPENAI_API_KEY=new-value" in content
    assert "old-value" not in content


def test_write_congregation_env_value_preserves_export_prefix(tmp_path: Path) -> None:
    path = tmp_path / ".kanbus.env"
    path.write_text("export OPENAI_API_KEY=old\n", encoding="utf-8")
    ai_credentials.write_congregation_env_value(path, "OPENAI_API_KEY", "new")
    content = path.read_text(encoding="utf-8")
    assert content == "export OPENAI_API_KEY=new\n"


def test_write_congregation_env_value_appends_when_absent_no_trailing_newline(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".kanbus.env"
    path.write_text("OTHER=1", encoding="utf-8")
    ai_credentials.write_congregation_env_value(path, "OPENAI_API_KEY", "abc")
    content = path.read_text(encoding="utf-8")
    assert content == "OTHER=1\nOPENAI_API_KEY=abc\n"


def test_write_congregation_env_value_rejects_newline_values(tmp_path: Path) -> None:
    path = tmp_path / ".kanbus.env"
    with pytest.raises(ValueError):
        ai_credentials.write_congregation_env_value(path, "KEY", "a\nb")
    with pytest.raises(ValueError):
        ai_credentials.write_congregation_env_value(path, "KEY", "a\rb")


def test_write_congregation_env_value_quotes_whitespace_and_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".kanbus.env"
    ai_credentials.write_congregation_env_value(path, "KEY", "value with space")
    ai_credentials.write_congregation_env_value(path, "OTHER", "no-space")
    ai_credentials.write_congregation_env_value(path, "HASHY", "a#b")
    content = path.read_text(encoding="utf-8")
    assert 'KEY="value with space"' in content
    assert "OTHER=no-space" in content
    assert 'HASHY="a#b"' in content


def test_write_congregation_env_value_ignores_comment_lines_with_equals(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".kanbus.env"
    path.write_text("# OPENAI_API_KEY=commented-out\n", encoding="utf-8")
    ai_credentials.write_congregation_env_value(path, "OPENAI_API_KEY", "real-value")
    content = path.read_text(encoding="utf-8")
    assert "# OPENAI_API_KEY=commented-out" in content
    assert "OPENAI_API_KEY=real-value" in content


def test_resolve_api_key_source_from_process_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "direct-value")
    source = ai_credentials.resolve_api_key_source(None)
    assert source is ai_credentials.CredentialSource.PROCESS_ENV


def test_resolve_api_key_source_from_congregation_file_matching_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (home / ".kanbus.env").write_text("OPENAI_API_KEY=congregation-value\n")
    monkeypatch.setenv("OPENAI_API_KEY", "congregation-value")
    source = ai_credentials.resolve_api_key_source(None)
    assert source is ai_credentials.CredentialSource.CONGREGATION_FILE


def test_resolve_api_key_source_from_project_file_matching_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (repo / ".env").write_text("OPENAI_API_KEY=project-value\n")
    monkeypatch.setenv("OPENAI_API_KEY", "project-value")
    source = ai_credentials.resolve_api_key_source(repo)
    assert source is ai_credentials.CredentialSource.PROJECT_FILE


def test_resolve_api_key_source_env_without_matching_file_is_process_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (home / ".kanbus.env").write_text("OPENAI_API_KEY=other-value\n")
    monkeypatch.setenv("OPENAI_API_KEY", "different-value")
    source = ai_credentials.resolve_api_key_source(repo)
    assert source is ai_credentials.CredentialSource.PROCESS_ENV


def test_resolve_api_key_source_without_env_prefers_congregation_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (home / ".kanbus.env").write_text("OPENAI_API_KEY=congregation-value\n")
    (repo / ".env").write_text("OPENAI_API_KEY=project-value\n")
    source = ai_credentials.resolve_api_key_source(repo)
    assert source is ai_credentials.CredentialSource.CONGREGATION_FILE


def test_resolve_api_key_source_without_env_falls_back_to_project_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (repo / ".env").write_text("OPENAI_API_KEY=project-value\n")
    source = ai_credentials.resolve_api_key_source(repo)
    assert source is ai_credentials.CredentialSource.PROJECT_FILE


def test_resolve_api_key_source_none_when_nothing_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = ai_credentials.resolve_api_key_source(None)
    assert source is ai_credentials.CredentialSource.NONE
