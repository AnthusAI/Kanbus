"""Step definitions for current user resolution."""

from __future__ import annotations

import os

from behave import given, then, when

from taskulus.users import get_current_user


@given('TASKULUS_USER is set to "{value}"')
def given_taskulus_user_set(context: object, value: str) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["TASKULUS_USER"] = value
    context.environment_overrides = overrides


@given("TASKULUS_USER is unset")
def given_taskulus_user_unset(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides.pop("TASKULUS_USER", None)
    context.environment_overrides = overrides


@given('USER is set to "{value}"')
def given_user_set(context: object, value: str) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["USER"] = value
    context.environment_overrides = overrides


@given("USER is unset")
def given_user_unset(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides.pop("USER", None)
    context.environment_overrides = overrides


@when("I resolve the current user")
def when_resolve_current_user(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    original_taskulus_user = os.environ.get("TASKULUS_USER")
    original_user = os.environ.get("USER")
    try:
        if "TASKULUS_USER" in overrides:
            os.environ["TASKULUS_USER"] = overrides["TASKULUS_USER"]
        else:
            os.environ.pop("TASKULUS_USER", None)
        if "USER" in overrides:
            os.environ["USER"] = overrides["USER"]
        else:
            os.environ.pop("USER", None)
        context.current_user = get_current_user()
    finally:
        if original_taskulus_user is None:
            os.environ.pop("TASKULUS_USER", None)
        else:
            os.environ["TASKULUS_USER"] = original_taskulus_user
        if original_user is None:
            os.environ.pop("USER", None)
        else:
            os.environ["USER"] = original_user


@then('the current user should be "{value}"')
def then_current_user_is(context: object, value: str) -> None:
    current_user = getattr(context, "current_user", None)
    assert current_user == value
