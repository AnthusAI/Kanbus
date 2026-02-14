"""Step definitions for current user resolution."""

from __future__ import annotations

import os

from behave import given, then, when

from kanbus.users import get_current_user


@given('KANBUS_USER is set to "{value}"')
def given_kanbus_user_set(context: object, value: str) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = value
    context.environment_overrides = overrides


@given("KANBUS_USER is unset")
def given_kanbus_user_unset(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides.pop("KANBUS_USER", None)
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
    original_kanbus_user = os.environ.get("KANBUS_USER")
    original_user = os.environ.get("USER")
    try:
        if "KANBUS_USER" in overrides:
            os.environ["KANBUS_USER"] = overrides["KANBUS_USER"]
        else:
            os.environ.pop("KANBUS_USER", None)
        if "USER" in overrides:
            os.environ["USER"] = overrides["USER"]
        else:
            os.environ.pop("USER", None)
        context.current_user = get_current_user()
    finally:
        if original_kanbus_user is None:
            os.environ.pop("KANBUS_USER", None)
        else:
            os.environ["KANBUS_USER"] = original_kanbus_user
        if original_user is None:
            os.environ.pop("USER", None)
        else:
            os.environ["USER"] = original_user


@then('the current user should be "{value}"')
def then_current_user_is(context: object, value: str) -> None:
    current_user = getattr(context, "current_user", None)
    assert current_user == value
