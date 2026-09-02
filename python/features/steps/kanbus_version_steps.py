"""Behave steps for kanbus-version enforcement."""

from __future__ import annotations

from behave import given

from kanbus import __version__
from kanbus.kanbus_version import parse_semver_core


@given('the project requires kanbus version "{version}"')
def given_project_requires_kanbus_version(context: object, version: str) -> None:
    version_path = context.working_directory / "kanbus-version"
    version_path.write_text(f"{version}\n", encoding="utf-8")


@given("the project requires the running kanbus CLI core version")
def given_project_requires_running_core_version(context: object) -> None:
    core = parse_semver_core(__version__)
    assert core is not None, f"running CLI version is not parseable: {__version__}"
    major, minor, patch = core
    version_path = context.working_directory / "kanbus-version"
    version_path.write_text(f"{major}.{minor}.{patch}\n", encoding="utf-8")


@given("kanbus-version contains invalid contents")
def given_invalid_kanbus_version_contents(context: object) -> None:
    version_path = context.working_directory / "kanbus-version"
    version_path.write_text("not-a-version\n", encoding="utf-8")
