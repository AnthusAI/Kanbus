"""Steps for the kbsc network binding (CONSOLE_HOST) scenarios."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from behave import then

from features.steps.console_ui_steps import (
    _allocate_port,
    _kbsc_binary_path,
    _write_console_port_to_config,
)

STARTUP_TIMEOUT_SECONDS = 60.0
LISTENING_MARKER = "Console backend listening on "


@dataclass
class KbscLaunch:
    """Observable outcome of starting kbsc for a few seconds.

    :param listening_line: First stdout line announcing the listener, if any.
    :type listening_line: Optional[str]
    :param exit_code: Exit status when kbsc terminated on its own.
    :type exit_code: Optional[int]
    :param stderr_text: Everything kbsc wrote to stderr.
    :type stderr_text: str
    """

    listening_line: Optional[str]
    exit_code: Optional[int]
    stderr_text: str


def _launch_kbsc(context: object, console_host: Optional[str]) -> KbscLaunch:
    """Start kbsc with the given CONSOLE_HOST and observe its startup.

    :param context: Behave context with a temporary project.
    :type context: object
    :param console_host: Value for CONSOLE_HOST, or None to leave it unset.
    :type console_host: Optional[str]
    :return: The observed startup outcome.
    :rtype: KbscLaunch
    """
    root = Path(context.working_directory)
    port = _allocate_port()
    _write_console_port_to_config(root, port)
    environment = {
        key: value for key, value in os.environ.items() if key != "CONSOLE_HOST"
    }
    environment.update(
        CONSOLE_PORT=str(port), CONSOLE_DATA_ROOT=str(root), KANBUS_DAEMON="0"
    )
    if console_host is not None:
        environment["CONSOLE_HOST"] = console_host
    process = subprocess.Popen(
        [str(_kbsc_binary_path())],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: "queue.Queue[str]" = queue.Queue()

    def read_stdout() -> None:
        for line in process.stdout:
            lines.put(line)

    stderr_chunks: list[str] = []

    def read_stderr() -> None:
        stderr_chunks.append(process.stderr.read())

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    listening_line: Optional[str] = None
    exit_code: Optional[int] = None
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.05)
            if LISTENING_MARKER in line:
                listening_line = line
                break
        except queue.Empty:
            pass
        exit_code = process.poll()
        if exit_code is not None:
            break
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)
    stderr_thread.join(timeout=10)
    return KbscLaunch(listening_line, exit_code, "".join(stderr_chunks))


def _assert_listens_on(launch: KbscLaunch, expected_host: str) -> None:
    """Assert kbsc announced a listener on the expected host.

    :param launch: Observed startup outcome.
    :type launch: KbscLaunch
    :param expected_host: Host text expected in the announcement.
    :type expected_host: str
    """
    assert launch.listening_line is not None, (
        f"kbsc did not report listening (exit {launch.exit_code}); "
        f"stderr: {launch.stderr_text}"
    )
    expected = f"{LISTENING_MARKER}http://{expected_host}:"
    assert (
        expected in launch.listening_line
    ), f"expected '{expected}' in '{launch.listening_line}'"


@then('kbsc started without CONSOLE_HOST listens on "{expected_host}"')
def then_kbsc_default_host_listens_on(context: object, expected_host: str) -> None:
    """Verify the default bind host.

    :param context: Behave context with a temporary project.
    :type context: object
    :param expected_host: Host text expected in the announcement.
    :type expected_host: str
    """
    _assert_listens_on(_launch_kbsc(context, None), expected_host)


@then('kbsc started with CONSOLE_HOST "{console_host}" listens on "{expected_host}"')
def then_kbsc_host_listens_on(
    context: object, console_host: str, expected_host: str
) -> None:
    """Verify the bind host for an explicit CONSOLE_HOST.

    :param context: Behave context with a temporary project.
    :type context: object
    :param console_host: Value for CONSOLE_HOST.
    :type console_host: str
    :param expected_host: Host text expected in the announcement.
    :type expected_host: str
    """
    _assert_listens_on(_launch_kbsc(context, console_host), expected_host)


@then(
    'kbsc started with CONSOLE_HOST "{console_host}" exits with an error naming "{named}"'
)
def then_kbsc_invalid_host_exits(
    context: object, console_host: str, named: str
) -> None:
    """Verify an invalid CONSOLE_HOST is a startup error.

    :param context: Behave context with a temporary project.
    :type context: object
    :param console_host: Value for CONSOLE_HOST.
    :type console_host: str
    :param named: Text the error must contain.
    :type named: str
    """
    launch = _launch_kbsc(context, console_host)
    assert launch.exit_code == 1, (
        f"kbsc should exit with status 1 (got {launch.exit_code}); "
        f"stderr: {launch.stderr_text}"
    )
    assert launch.listening_line is None
    assert named in launch.stderr_text, launch.stderr_text
