"""Behave steps for user-level AI credential setup (`kanbus setup ai`)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from behave import given, then

from kanbus.config_loader import CONGREGATION_ENV_FILENAME


@given("the congregation env file is redirected to a temporary home")
def given_congregation_env_redirected(context: object) -> None:
    """Point ~ (HOME) at a scenario-local directory for the congregation file.

    :param context: Behave context object.
    :type context: object
    """
    repository = Path(context.working_directory)
    congregation_home = repository / ".test-congregation-home"
    congregation_home.mkdir(exist_ok=True)
    overrides = getattr(context, "environment_overrides", None)
    if overrides is None:
        context.environment_overrides = {}
        overrides = context.environment_overrides
    overrides["HOME"] = str(congregation_home)
    context.congregation_home = congregation_home


def _congregation_env_path(context: object) -> Path:
    congregation_home = getattr(context, "congregation_home", None)
    if congregation_home is None:
        raise RuntimeError("congregation env file was not redirected")
    return Path(congregation_home) / CONGREGATION_ENV_FILENAME


@given("{variable} is absent from the process environment")
def given_variable_absent(context: object, variable: str) -> None:
    """Ensure the named variable is unset for both this process and the CLI invocation.

    :param context: Behave context object.
    :type context: object
    :param variable: Environment variable name to remove.
    :type variable: str
    """
    overrides = getattr(context, "environment_overrides", None)
    if overrides is not None:
        overrides.pop(variable, None)
    os.environ.pop(variable, None)


@given("the congregation env file contains:")
def given_congregation_env_file_contains(context: object) -> None:
    """Write literal content into the redirected congregation env file.

    :param context: Behave context object with a docstring in context.text.
    :type context: object
    """
    content = context.text or ""
    if not content.endswith("\n"):
        content += "\n"
    path = _congregation_env_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@then('the congregation env file should contain "{text}"')
def then_congregation_env_file_should_contain(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    path = _congregation_env_path(context)
    content = path.read_text(encoding="utf-8")
    assert normalized in content, f"expected {normalized!r} in {content!r}"


@then('the congregation env file should not contain "{text}"')
def then_congregation_env_file_should_not_contain(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    path = _congregation_env_path(context)
    content = path.read_text(encoding="utf-8")
    assert normalized not in content, f"expected {normalized!r} not in {content!r}"


@then("the congregation env file should have mode 600")
def then_congregation_env_file_should_have_mode_600(context: object) -> None:
    path = _congregation_env_path(context)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"expected mode 0o600, got {oct(mode)}"
