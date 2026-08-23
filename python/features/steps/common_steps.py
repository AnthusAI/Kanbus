"""Common Behave steps shared across scenarios."""

from __future__ import annotations

from behave import given, then
from pathlib import Path

from features.steps.shared import initialize_default_project


@given("a Kanbus project with default configuration")
def given_kanbus_project(context: object) -> None:
    initialize_default_project(context)


@then('the directory "{path}" should exist')
def then_directory_exists(context: object, path: str) -> None:
    full_path = Path(context.working_directory) / path
    assert full_path.is_dir(), f"Expected directory {full_path} to exist"


@then('the directory "{path}" should not exist')
def then_directory_not_exists(context: object, path: str) -> None:
    full_path = Path(context.working_directory) / path
    assert not full_path.is_dir(), f"Expected directory {full_path} to not exist"


@given('the directory "{path}" exists')
def given_directory_exists(context: object, path: str) -> None:
    full_path = Path(context.working_directory) / path
    full_path.mkdir(parents=True, exist_ok=True)


@given('I remove the directory "{path}"')
def given_remove_directory(context: object, path: str) -> None:
    import shutil

    full_path = Path(context.working_directory) / path
    if full_path.exists():
        shutil.rmtree(full_path)
