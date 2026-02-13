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
    context.temp_dir_object = TemporaryDirectory(dir="/tmp")
    context.temp_dir = context.temp_dir_object.name
    context.working_directory = None
    context.result = None
    context.last_issue_id = None
    context.environment_overrides = {"TASKULUS_NO_DAEMON": "1"}
    context.daemon_core = None


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

    original_send_request = getattr(context, "original_send_request", None)
    if original_send_request is not None:
        import taskulus.daemon_client as daemon_client

        daemon_client.send_request = original_send_request
        context.original_send_request = None

    original_daemon_socket = getattr(context, "original_daemon_socket", None)
    if original_daemon_socket is not None:
        import taskulus.daemon_client as daemon_client

        daemon_client.socket.socket = original_daemon_socket
        context.original_daemon_socket = None

    original_list_with_local = getattr(context, "original_list_with_local", None)
    if original_list_with_local is not None:
        import taskulus.issue_listing as issue_listing

        issue_listing._list_issues_with_local = original_list_with_local
        context.original_list_with_local = None

    original_load_issues = getattr(context, "original_load_issues", None)
    if original_load_issues is not None:
        import taskulus.issue_listing as issue_listing

        issue_listing._load_issues_from_directory = original_load_issues
        context.original_load_issues = None

    original_load_local = getattr(context, "original_load_local", None)
    if original_load_local is not None:
        import taskulus.issue_listing as issue_listing

        issue_listing._load_issues_from_directory = original_load_local
        context.original_load_local = None

    original_path = getattr(context, "original_path_env", None)
    if original_path is not None:
        import os

        os.environ["PATH"] = original_path
        context.original_path_env = None

    original_daemon_env = getattr(context, "original_daemon_env", None)
    if "original_daemon_env" in context.__dict__:
        import os

        if original_daemon_env is None or original_daemon_env == "":
            os.environ.pop("TASKULUS_NO_DAEMON", None)
        else:
            os.environ["TASKULUS_NO_DAEMON"] = original_daemon_env
        context.original_daemon_env = None

    original_daemon_socket = getattr(context, "original_daemon_socket", None)
    if original_daemon_socket is not None:
        import taskulus.daemon_client as daemon_client

        daemon_client.socket.socket = original_daemon_socket
        context.original_daemon_socket = None

    if getattr(context, "daemon_patched", False):
        import taskulus.daemon_client as daemon_client

        daemon_client.spawn_daemon = context.daemon_original_spawn
        daemon_client.send_request = context.daemon_original_send
        context.daemon_patched = False
        context.daemon_original_spawn = None
        context.daemon_original_send = None

    original_no_color = getattr(context, "original_no_color", None)
    if "original_no_color" in context.__dict__:
        import os

        if original_no_color is None or original_no_color == "":
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = original_no_color
        context.original_no_color = None

    original_canonicalize = getattr(context, "original_canonicalize_env", None)
    if "original_canonicalize_env" in context.__dict__:
        import os

        if original_canonicalize is None or original_canonicalize == "":
            os.environ.pop("TASKULUS_TEST_CANONICALIZE_FAILURE", None)
        else:
            os.environ["TASKULUS_TEST_CANONICALIZE_FAILURE"] = original_canonicalize
        context.original_canonicalize_env = None

    original_config_path_failure = getattr(
        context, "original_configuration_path_failure_env", None
    )
    if "original_configuration_path_failure_env" in context.__dict__:
        import os

        if original_config_path_failure is None or original_config_path_failure == "":
            os.environ.pop("TASKULUS_TEST_CONFIGURATION_PATH_FAILURE", None)
        else:
            os.environ["TASKULUS_TEST_CONFIGURATION_PATH_FAILURE"] = (
                original_config_path_failure
            )
        context.original_configuration_path_failure_env = None

    empty_socket = getattr(context, "empty_daemon_socket", None)
    if empty_socket is not None:
        try:
            empty_socket.close()
        except OSError:
            pass
        context.empty_daemon_socket = None

    empty_thread = getattr(context, "empty_daemon_thread", None)
    if empty_thread is not None:
        empty_thread.join(timeout=1.0)
        context.empty_daemon_thread = None

    daemon_thread = getattr(context, "daemon_thread", None)
    if daemon_thread is not None:
        try:
            daemon_thread.join(timeout=1.0)
        except RuntimeError:
            pass
        context.daemon_thread = None
        context.real_daemon_running = False

    original_discover = getattr(context, "original_discover_taskulus_projects", None)
    if original_discover is not None:
        import taskulus.project as project

        project.discover_taskulus_projects = original_discover
        context.original_discover_taskulus_projects = None

    unreadable_path = getattr(context, "unreadable_path", None)
    if unreadable_path is not None:
        try:
            unreadable_path.chmod(getattr(context, "unreadable_mode", 0o700))
        except OSError:
            pass
        context.unreadable_path = None
        context.unreadable_mode = None

    import taskulus.beads_write as beads_write
    import taskulus.ids as ids

    beads_write.set_test_beads_slug_sequence(None)
    ids.set_test_uuid_sequence(None)
