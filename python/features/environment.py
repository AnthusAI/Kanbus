"""Behave environment hooks."""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PYTHON_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PYTHON_DIR / "src"
sys.path.insert(0, str(PYTHON_DIR))
sys.path.insert(0, str(SRC_DIR))


def before_scenario(context: object, scenario: object) -> None:
    """Reset context state before each scenario.

    :param context: Behave context object.
    :type context: object
    :param scenario: Behave scenario object.
    :type scenario: object
    """
    context.temp_dir_object = TemporaryDirectory()
    context.temp_dir = context.temp_dir_object.name
    context.working_directory = None
    context.result = None
    context.last_issue_id = None


def after_scenario(context: object, scenario: object) -> None:
    """Clean up temp directories after each scenario.

    :param context: Behave context object.
    :type context: object
    :param scenario: Behave scenario object.
    :type scenario: object
    """
    temp_dir_object = getattr(context, "temp_dir_object", None)
    if temp_dir_object is not None:
        temp_dir_object.cleanup()
        context.temp_dir_object = None
        context.temp_dir = None
