"""Behave steps for console snapshot."""

from __future__ import annotations

from behave import given, when
import shutil
import json
from pathlib import Path
from types import SimpleNamespace

from features.steps.shared import load_project_directory
from kanbus.console_snapshot import ConsoleSnapshotError, build_console_snapshot


@given("the Kanbus configuration file is missing")
def given_kanbus_configuration_missing(context: object) -> None:
    project_dir = load_project_directory(context)
    config_path = project_dir.parent / ".kanbus.yml"
    if config_path.exists():
        if config_path.is_dir():
            shutil.rmtree(config_path)
        else:
            config_path.unlink()


@given("a Kanbus configuration file that is not a mapping")
def given_kanbus_configuration_not_mapping(context: object) -> None:
    project_dir = load_project_directory(context)
    config_path = project_dir.parent / ".kanbus.yml"
    config_path.write_text("- item\n- other\n", encoding="utf-8")


@given("the issues directory is a file")
def given_issues_directory_is_file(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_path = project_dir / "issues"
    if issues_path.exists():
        if issues_path.is_dir():
            shutil.rmtree(issues_path)
        else:
            issues_path.unlink()
    issues_path.write_text("not a directory", encoding="utf-8")


@given("the issues directory is unreadable")
def given_issues_directory_is_unreadable(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    original_mode = issues_dir.stat().st_mode
    issues_dir.chmod(0)
    context.unreadable_path = issues_dir
    context.unreadable_mode = original_mode


@when("I build a console snapshot directly")
def when_build_console_snapshot_directly(context: object) -> None:
    working_directory = getattr(context, "working_directory", None)
    if working_directory is None:
        raise RuntimeError("working directory not set")
    root = Path(working_directory)
    try:
        snapshot = build_console_snapshot(root)
    except ConsoleSnapshotError as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=str(error),
            output=str(error),
        )
        return
    payload = json.dumps(snapshot, indent=2, sort_keys=False)
    context.result = SimpleNamespace(
        exit_code=0,
        stdout=payload,
        stderr="",
        output=payload,
    )
