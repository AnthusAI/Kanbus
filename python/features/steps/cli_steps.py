"""CLI entrypoint steps."""

from __future__ import annotations

import contextlib
import io
import os
import runpy
import sys
from types import SimpleNamespace

from behave import when


@when("I run the CLI entrypoint with --help")
def when_run_cli_entrypoint_help(context: object) -> None:
    original_argv = sys.argv[:]
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 0
    sys.argv = ["taskulus.cli", "--help"]
    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(
            stderr_buffer
        ):
            runpy.run_module("taskulus.cli", run_name="__main__")
    except SystemExit as exc:
        if exc.code is None:
            exit_code = 0
        elif isinstance(exc.code, int):
            exit_code = exc.code
        else:
            exit_code = 1
    finally:
        sys.argv = original_argv

    stdout_value = stdout_buffer.getvalue()
    stderr_value = stderr_buffer.getvalue()
    context.result = SimpleNamespace(
        exit_code=exit_code,
        stdout=stdout_value,
        stderr=stderr_value,
        output=stdout_value,
    )


@when('I run the CLI entrypoint with "{arguments}"')
def when_run_cli_entrypoint_args(context: object, arguments: str) -> None:
    original_argv = sys.argv[:]
    original_cwd = None
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 0
    sys.argv = ["taskulus.cli", *arguments.split()]
    working_directory = getattr(context, "working_directory", None)
    if working_directory is not None:
        original_cwd = os.getcwd()
        os.chdir(working_directory)
    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(
            stderr_buffer
        ):
            runpy.run_module("taskulus.cli", run_name="__main__")
    except SystemExit as exc:
        if exc.code is None:
            exit_code = 0
        elif isinstance(exc.code, int):
            exit_code = exc.code
        else:
            exit_code = 1
    finally:
        sys.argv = original_argv
        if original_cwd is not None:
            os.chdir(original_cwd)

    stdout_value = stdout_buffer.getvalue()
    stderr_value = stderr_buffer.getvalue()
    context.result = SimpleNamespace(
        exit_code=exit_code,
        stdout=stdout_value,
        stderr=stderr_value,
        output=stdout_value,
    )
