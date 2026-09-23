"""User-level AI credential storage and resolution for Kanbus.

Kanbus AI features (compaction, right-now summaries, standup rollups) need
an LLM API key. Rather than requiring a per-project ``.env`` file, users can
run ``kbs setup ai`` once to store the key in ``~/.kanbus.env``. That file is
loaded by :func:`kanbus.config_loader.load_repository_environment` before
any project ``.env`` file, and never overrides a value already present in
the process environment.
"""

from __future__ import annotations

import os
import tempfile
from enum import Enum
from pathlib import Path

from kanbus.config_loader import congregation_env_path, parse_dotenv_lines

DEFAULT_API_KEY_VARIABLE = "OPENAI_API_KEY"
SETUP_COMMAND_HINT = "kbs setup ai"


def missing_api_key_message(variable: str = DEFAULT_API_KEY_VARIABLE) -> str:
    """Return the standard message shown when an AI credential is missing.

    :param variable: Environment variable name that is missing.
    :type variable: str
    :return: User-facing guidance message.
    :rtype: str
    """
    return (
        f"{variable} is not set. Run 'kbs setup ai' (or 'kanbus setup ai') to "
        "store it once in ~/.kanbus.env, or set it in your shell environment "
        "or the project .env file."
    )


class CredentialSource(str, Enum):
    """Where an AI credential value currently resolves from."""

    PROCESS_ENV = "process environment"
    CONGREGATION_FILE = "~/.kanbus.env"
    PROJECT_FILE = "project .env"
    NONE = "not set"


def read_dotenv_value(path: Path, key: str) -> str | None:
    """Return the last value assigned to ``key`` in a dotenv file.

    :param path: Dotenv file path.
    :type path: Path
    :param key: Environment variable name to look up.
    :type key: str
    :return: The value, or ``None`` if the file is missing, unreadable, or
        does not define the key.
    :rtype: str | None
    """
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    value: str | None = None
    for parsed_key, parsed_value in parse_dotenv_lines(content):
        if parsed_key == key:
            value = parsed_value
    return value


def resolve_api_key_source(
    repository_root: Path | None, variable: str = DEFAULT_API_KEY_VARIABLE
) -> CredentialSource:
    """Determine where an AI credential currently resolves from.

    :param repository_root: Repository root, used to check the project
        ``.env`` file. May be ``None`` when there is no active project.
    :type repository_root: Path | None
    :param variable: Environment variable name to resolve.
    :type variable: str
    :return: The resolved credential source.
    :rtype: CredentialSource
    """
    congregation_value = read_dotenv_value(congregation_env_path(), variable)
    project_value: str | None = None
    if repository_root is not None:
        project_value = read_dotenv_value(repository_root / ".env", variable)

    env_value = os.environ.get(variable, "").strip()
    if env_value:
        if env_value == congregation_value:
            return CredentialSource.CONGREGATION_FILE
        if env_value == project_value:
            return CredentialSource.PROJECT_FILE
        return CredentialSource.PROCESS_ENV

    if congregation_value:
        return CredentialSource.CONGREGATION_FILE
    if project_value:
        return CredentialSource.PROJECT_FILE
    return CredentialSource.NONE


def describe_api_key_source(source: CredentialSource) -> str:
    """Return the human-readable description of a credential source.

    :param source: Resolved credential source.
    :type source: CredentialSource
    :return: Display text for the source.
    :rtype: str
    """
    return source.value


def requires_openai_key(model: str) -> bool:
    """Return whether a LiteLLM model string routes through OpenAI directly.

    LiteLLM model strings without a provider prefix (e.g. ``"gpt-4o-mini"``)
    default to the OpenAI provider, as does an explicit ``"openai/..."``
    prefix. Any other prefixed model (``"anthropic/..."``,
    ``"azure/..."``, etc.) is routed elsewhere and does not require
    ``OPENAI_API_KEY``.

    :param model: LiteLLM model identifier.
    :type model: str
    :return: True when the model requires an OpenAI API key.
    :rtype: bool
    """
    return "/" not in model or model.startswith("openai/")


def congregation_env_display() -> str:
    """Return the display form of the congregation env file path.

    :return: ``"~/.kanbus.env"``.
    :rtype: str
    """
    return "~/.kanbus.env"


def _format_dotenv_value(value: str) -> str:
    if any(character.isspace() for character in value) or "#" in value:
        return f'"{value}"'
    return value


def write_congregation_env_value(path: Path, key: str, value: str) -> None:
    """Write or update a key/value pair in the user-level congregation env file.

    Preserves every other line byte-for-byte, replacing only the first line
    whose key matches (keeping an ``export `` prefix if present), or
    appending a new line when the key is absent. The file is written
    atomically and left with mode ``0o600``.

    :param path: Congregation env file path.
    :type path: Path
    :param key: Environment variable name to set.
    :type key: str
    :param value: Value to store.
    :type value: str
    :raises ValueError: If ``value`` contains a newline character.
    :raises OSError: If the file cannot be written.
    """
    if "\n" in value or "\r" in value:
        raise ValueError("API key value must not contain newlines")

    existing_lines: list[str] = []
    if path.exists():
        content = path.read_text(encoding="utf-8")
        existing_lines = content.splitlines()

    formatted_value = _format_dotenv_value(value)
    replaced = False
    new_lines: list[str] = []
    for line in existing_lines:
        if not replaced:
            stripped = line.strip()
            working = stripped
            export_prefix = ""
            if working.lower().startswith("export "):
                export_prefix = "export "
                working = working[7:].lstrip()
            if working and not working.startswith("#") and "=" in working:
                existing_key = working.split("=", 1)[0].strip()
                if existing_key == key:
                    new_lines.append(f"{export_prefix}{key}={formatted_value}")
                    replaced = True
                    continue
        new_lines.append(line)

    if not replaced:
        new_lines.append(f"{key}={formatted_value}")

    new_content = "\n".join(new_lines) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(path.parent),
        delete=False,
        encoding="utf-8",
    )
    tmp_path = Path(tmp.name)
    try:
        tmp.write(new_content)
        tmp.flush()
        tmp.close()
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)
