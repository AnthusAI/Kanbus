"""Behave steps for lifecycle hook feature coverage."""

from __future__ import annotations

from pathlib import Path

import yaml
from behave import given, then


def _root(context: object) -> Path:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    return Path(working_directory)


@given('a lifecycle hook recorder script at "{relative_path}"')
def given_lifecycle_hook_recorder_script(context: object, relative_path: str) -> None:
    root = _root(context)
    script_path = root / relative_path
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "set -eu",
                'token=\"${1:-hook}\"',
                'log_path=\"${HOOK_LOG_PATH:-}\"',
                'if [ -z \"$log_path\" ]; then',
                "  echo \"HOOK_LOG_PATH is required\" >&2",
                "  exit 2",
                "fi",
                "cat >/dev/null",
                "printf '%s\\n' \"$token\" >> \"$log_path\"",
                'exit_code=\"${HOOK_EXIT_CODE:-0}\"',
                'if [ \"$exit_code\" != \"0\" ]; then',
                "  exit \"$exit_code\"",
                "fi",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)


@given("the Kanbus hooks configuration is")
@given("the Kanbus hooks configuration is:")
def given_kanbus_hooks_configuration(context: object) -> None:
    root = _root(context)
    config_path = root / ".kanbus.yml"
    hooks_block = yaml.safe_load(context.text or "") or {}
    if not isinstance(hooks_block, dict):
        raise AssertionError("hooks configuration must deserialize to a mapping")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise AssertionError(".kanbus.yml must deserialize to a mapping")
    config["hooks"] = hooks_block
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )


@then('hook log "{relative_path}" should contain "{token}"')
def then_hook_log_contains(context: object, relative_path: str, token: str) -> None:
    root = _root(context)
    content = (root / relative_path).read_text(encoding="utf-8")
    assert token in content


@then('hook log "{relative_path}" should not contain "{token}"')
def then_hook_log_not_contains(context: object, relative_path: str, token: str) -> None:
    root = _root(context)
    log_path = root / relative_path
    content = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    assert token not in content
