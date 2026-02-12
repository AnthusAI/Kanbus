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
    context.environment_overrides = {"TASKULUS_NO_DAEMON": "1"}


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
    server = getattr(context, "daemon_server", None)
    if server is not None:
        server.shutdown()
        server.server_close()
        context.daemon_server = None
    thread = getattr(context, "daemon_thread", None)
    if thread is not None:
        thread.join(timeout=1.0)
        context.daemon_thread = None
    original_spawn = getattr(context, "daemon_original_spawn", None)
    original_send = getattr(context, "daemon_original_send", None)
    if original_spawn or original_send:
        import taskulus.daemon_client as daemon_client

        if original_spawn:
            daemon_client.spawn_daemon = original_spawn
        if original_send:
            daemon_client.send_request = original_send
        context.daemon_original_spawn = None
        context.daemon_original_send = None
        context.daemon_patched = False

    original_request = getattr(context, "original_request_with_recovery", None)
    if original_request is not None:
        import taskulus.daemon_client as daemon_client

        daemon_client._request_with_recovery = original_request
        context.original_request_with_recovery = None

    original_popen = getattr(context, "original_subprocess_popen", None)
    if original_popen is not None:
        import subprocess

        subprocess.Popen = original_popen
        context.original_subprocess_popen = None

    original_request_index_list = getattr(context, "original_request_index_list", None)
    if original_request_index_list is not None:
        import taskulus.issue_listing as issue_listing

        issue_listing.request_index_list = original_request_index_list
        context.original_request_index_list = None

    original_list_with_local = getattr(context, "original_list_with_local", None)
    if original_list_with_local is not None:
        import taskulus.issue_listing as issue_listing

        issue_listing._list_issues_with_local = original_list_with_local
        context.original_list_with_local = None

    original_path = getattr(context, "original_path_env", None)
    if original_path is not None:
        import os

        os.environ["PATH"] = original_path
        context.original_path_env = None
