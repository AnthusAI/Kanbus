"""Common Behave steps shared across scenarios."""

from __future__ import annotations

from behave import given

from features.steps.shared import initialize_default_project


@given("a Taskulus project with default configuration")
def given_taskulus_project(context: object) -> None:
    initialize_default_project(context)
