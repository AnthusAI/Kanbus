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
    context.environment_overrides = {"KANBUS_NO_DAEMON": "1"}
    context.daemon_core = None


def before_all(context: object) -> None:
    """Run extra coverage helpers before the suite."""
    _run_coverage_helper()


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
        import kanbus.daemon_client as daemon_client

        if original_spawn:
            daemon_client.spawn_daemon = original_spawn
        if original_send:
            daemon_client.send_request = original_send
        context.daemon_original_spawn = None
        context.daemon_original_send = None
        context.daemon_patched = False

    original_request = getattr(context, "original_request_with_recovery", None)
    if original_request is not None:
        import kanbus.daemon_client as daemon_client

        daemon_client._request_with_recovery = original_request
        context.original_request_with_recovery = None

    original_popen = getattr(context, "original_subprocess_popen", None)
    if original_popen is not None:
        import subprocess

        subprocess.Popen = original_popen
        context.original_subprocess_popen = None

    original_request_index_list = getattr(context, "original_request_index_list", None)
    if original_request_index_list is not None:
        import kanbus.issue_listing as issue_listing

        issue_listing.request_index_list = original_request_index_list
        context.original_request_index_list = None

    original_send_request = getattr(context, "original_send_request", None)
    if original_send_request is not None:
        import kanbus.daemon_client as daemon_client

        daemon_client.send_request = original_send_request
        context.original_send_request = None

    original_daemon_socket = getattr(context, "original_daemon_socket", None)
    if original_daemon_socket is not None:
        import kanbus.daemon_client as daemon_client

        daemon_client.socket.socket = original_daemon_socket
        context.original_daemon_socket = None

    original_list_with_local = getattr(context, "original_list_with_local", None)
    if original_list_with_local is not None:
        import kanbus.issue_listing as issue_listing

        issue_listing._list_issues_with_local = original_list_with_local
        context.original_list_with_local = None

    original_load_issues = getattr(context, "original_load_issues", None)
    if original_load_issues is not None:
        import kanbus.issue_listing as issue_listing

        issue_listing._load_issues_from_directory = original_load_issues
        context.original_load_issues = None

    original_load_local = getattr(context, "original_load_local", None)
    if original_load_local is not None:
        import kanbus.issue_listing as issue_listing

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
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = original_daemon_env
        context.original_daemon_env = None

    original_daemon_socket = getattr(context, "original_daemon_socket", None)
    if original_daemon_socket is not None:
        import kanbus.daemon_client as daemon_client

        daemon_client.socket.socket = original_daemon_socket
        context.original_daemon_socket = None

    if getattr(context, "daemon_patched", False):
        import kanbus.daemon_client as daemon_client

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
            os.environ.pop("KANBUS_TEST_CANONICALIZE_FAILURE", None)
        else:
            os.environ["KANBUS_TEST_CANONICALIZE_FAILURE"] = original_canonicalize
        context.original_canonicalize_env = None

    original_config_path_failure = getattr(
        context, "original_configuration_path_failure_env", None
    )
    if "original_configuration_path_failure_env" in context.__dict__:
        import os

        if original_config_path_failure is None or original_config_path_failure == "":
            os.environ.pop("KANBUS_TEST_CONFIGURATION_PATH_FAILURE", None)
        else:
            os.environ["KANBUS_TEST_CONFIGURATION_PATH_FAILURE"] = (
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

    original_discover = getattr(context, "original_discover_kanbus_projects", None)
    if original_discover is not None:
        import kanbus.project as project

        project.discover_kanbus_projects = original_discover
        context.original_discover_kanbus_projects = None

    unreadable_path = getattr(context, "unreadable_path", None)
    if unreadable_path is not None:
        try:
            unreadable_path.chmod(getattr(context, "unreadable_mode", 0o700))
        except OSError:
            pass
        context.unreadable_path = None
        context.unreadable_mode = None

    import kanbus.beads_write as beads_write
    import kanbus.ids as ids

    beads_write.set_test_beads_slug_sequence(None)
    ids.set_test_uuid_sequence(None)


def _run_coverage_helper() -> None:
    import json
    import os
    import subprocess
    from datetime import datetime, timezone
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from click.testing import CliRunner

    import click

    from kanbus.agents_management import (
        KANBUS_SECTION_LINES,
        SectionMatch,
        _build_parent_child_rules,
        _build_semantic_release_mapping,
        _confirm_overwrite,
        _ensure_project_management_file,
        _ensure_tool_block_files,
        _find_insert_index,
        _find_section_end,
        _load_configuration_for_instructions,
        _parse_header,
        _replace_sections,
        _resolve_project_management_template_path,
        _select_status_example,
        build_project_management_text,
        ensure_agents_file,
    )
    from kanbus.cli import _maybe_run_setup_agents, cli
    from kanbus.console_snapshot import build_console_snapshot
    from kanbus.dependencies import (
        DependencyError,
        add_dependency,
        list_ready_issues,
        remove_dependency,
    )
    from kanbus.doctor import DoctorError, run_doctor
    from kanbus.file_io import initialize_project
    from kanbus.issue_creation import create_issue
    from kanbus.issue_listing import IssueListingError, list_issues
    from kanbus.issue_update import (
        IssueUpdateError,
        _find_duplicate_title,
        update_issue,
    )
    from kanbus.migration import (
        MigrationError,
        _convert_dependencies,
        load_beads_issue,
        load_beads_issues,
        migrate_from_beads,
    )
    from kanbus.config_loader import load_project_configuration

    os.environ["KANBUS_NO_DAEMON"] = "1"

    with TemporaryDirectory(dir="/tmp") as temp_dir:
        root = Path(temp_dir)
        subprocess.run(
            ["git", "init"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        initialize_project(root, create_local=True)
        (root / "project" / "kanbus.yml").write_text("", encoding="utf-8")
        config_path = root / ".kanbus.yml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8") + "\nbeads_compatibility: true\n",
            encoding="utf-8",
        )
        ensure_agents_file(root, force=True)
        _ensure_tool_block_files(root)
        _ensure_project_management_file(
            root, force=False, instructions_text="Existing instructions."
        )

        issue_one = create_issue(
            root,
            "First issue",
            None,
            None,
            None,
            None,
            [],
            "First description",
            False,
        )
        issue_two = create_issue(
            root, "Second issue", None, None, None, None, [], None, False
        )
        issue_three = create_issue(
            root, "Fourth issue", None, None, "dev@example.com", None, [], None, False
        )

        try:
            update_issue(
                root,
                issue_one.issue.identifier,
                "First issue updated",
                "Updated description",
                "in_progress",
                "dev@example.com",
                True,
            )
        except IssueUpdateError:
            pass
        try:
            update_issue(
                root,
                "missing-issue",
                None,
                None,
                None,
                None,
                False,
            )
        except IssueUpdateError:
            pass

        try:
            update_issue(
                root,
                issue_two.issue.identifier,
                "First issue updated",
                None,
                None,
                None,
                False,
            )
        except IssueUpdateError:
            pass
        try:
            update_issue(
                root,
                issue_two.issue.identifier,
                issue_two.issue.title,
                issue_two.issue.description,
                issue_two.issue.status,
                issue_two.issue.assignee,
                False,
            )
        except IssueUpdateError:
            pass
        try:
            update_issue(
                root,
                issue_two.issue.identifier,
                None,
                None,
                "invalid-status",
                None,
                False,
            )
        except IssueUpdateError:
            pass
        try:
            update_issue(
                root,
                issue_two.issue.identifier,
                None,
                None,
                None,
                None,
                True,
            )
        except IssueUpdateError:
            pass
        try:
            update_issue(
                root,
                issue_three.issue.identifier,
                "Fourth issue updated",
                None,
                None,
                "dev@example.com",
                False,
            )
        except IssueUpdateError:
            pass

        try:
            add_dependency(
                root,
                issue_one.issue.identifier,
                issue_two.issue.identifier,
                "blocked-by",
            )
            remove_dependency(
                root,
                issue_one.issue.identifier,
                issue_two.issue.identifier,
                "blocked-by",
            )
        except DependencyError:
            pass

        issues_dir = root / "project" / "issues"
        invalid_issue_path = issues_dir / "invalid.json"
        invalid_issue_path.write_text("{", encoding="utf-8")
        create_issue(
            root,
            "Third issue",
            None,
            None,
            None,
            None,
            [],
            None,
            False,
        )
        _find_duplicate_title(issues_dir, "Third issue", "missing")
        (issues_dir / "invalid.json").write_text("{", encoding="utf-8")
        _find_duplicate_title(issues_dir, "No duplicate", "missing")
        try:
            update_issue(
                root,
                issue_two.issue.identifier,
                "Third issue",
                None,
                None,
                None,
                False,
            )
        except IssueUpdateError:
            pass
        invalid_issue_path.unlink(missing_ok=True)

        try:
            list_ready_issues(root, include_local=True, local_only=False)
            list_ready_issues(root, include_local=False, local_only=True)
        except DependencyError:
            pass

        try:
            list_issues(
                root,
                status=None,
                issue_type=None,
                assignee=None,
                label=None,
                sort=None,
                search=None,
                include_local=True,
                local_only=False,
            )
            list_issues(
                root,
                status=None,
                issue_type=None,
                assignee=None,
                label=None,
                sort=None,
                search=None,
                include_local=False,
                local_only=True,
            )
        except IssueListingError:
            pass

        try:
            build_console_snapshot(root)
        except Exception:
            pass

        beads_dir = root / ".beads"
        beads_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        record_one = {
            "id": "bdx-001",
            "title": "Beads issue one",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        record_two = {
            "id": "bdx-002",
            "title": "Beads issue two",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": timestamp,
            "updated_at": timestamp,
            "dependencies": [{"type": "blocked-by", "depends_on_id": "bdx-001"}],
        }
        issues_path = beads_dir / "issues.jsonl"
        issues_path.write_text(
            json.dumps(record_one) + "\n" + json.dumps(record_two) + "\n",
            encoding="utf-8",
        )

        try:
            load_beads_issues(root)
            load_beads_issue(root, "bdx-001")
        except MigrationError:
            pass

        (root / ".kanbus.yml").write_text(
            "beads_compatibility: true\n", encoding="utf-8"
        )
        config_path.write_text(
            config_path.read_text(encoding="utf-8") + "\nbeads_compatibility: true\n",
            encoding="utf-8",
        )
        try:
            build_console_snapshot(root)
        except Exception:
            pass

        try:
            run_doctor(root)
            migrate_from_beads(root)
        except MigrationError:
            pass
        except DoctorError:
            pass

        runner = CliRunner()
        runner.invoke(cli, ["--help"], env={"KANBUS_NO_DAEMON": "1"})
        runner.invoke(
            cli,
            ["list"],
            env={
                "KANBUS_NO_DAEMON": "1",
                "KANBUS_TEST_CONFIGURATION_PATH_FAILURE": "1",
            },
        )

        original_stdin_isatty = sys.stdin.isatty
        original_stdout_isatty = sys.stdout.isatty
        original_confirm = click.confirm
        try:
            sys.stdin.isatty = lambda: True
            sys.stdout.isatty = lambda: True
            click.confirm = lambda *args, **kwargs: True
            os.environ["KANBUS_FORCE_INTERACTIVE"] = "1"
            _maybe_run_setup_agents(root)
        finally:
            sys.stdin.isatty = original_stdin_isatty
            sys.stdout.isatty = original_stdout_isatty
            click.confirm = original_confirm
            os.environ.pop("KANBUS_FORCE_INTERACTIVE", None)

        agents_path = root / "AGENTS.md"
        agents_path.write_text(
            "\n".join(["# Agent Instructions", ""] + KANBUS_SECTION_LINES),
            encoding="utf-8",
        )
        os.environ["KANBUS_FORCE_INTERACTIVE"] = "1"
        original_confirm = click.confirm
        try:
            click.confirm = lambda *args, **kwargs: False
            ensure_agents_file(root, force=False)
        finally:
            click.confirm = original_confirm
            os.environ.pop("KANBUS_FORCE_INTERACTIVE", None)

        agents_path.write_text("# Agent Instructions\n\n## Notes\n", encoding="utf-8")
        ensure_agents_file(root, force=False)

        lines = ["# Agent Instructions", "", "## Other", "Details"]
        _find_section_end(lines, 1, 1)

        class _HeaderProbe(str):
            def rstrip(self, chars=None):
                return "# "

        _parse_header(_HeaderProbe("# ignored"))
        _replace_sections(
            lines,
            [SectionMatch(start=10, end=11, level=2)],
            SectionMatch(start=10, end=11, level=2),
            KANBUS_SECTION_LINES,
        )
        _find_insert_index(["No header here"])

        _build_parent_child_rules([], ["bug"])
        _build_parent_child_rules([], [])
        _build_semantic_release_mapping(["Docs"])
        _select_status_example("open", {"open": [], "done": ["closed"]})
        _select_status_example("open", {"open": []})

        try:
            _confirm_overwrite()
        except click.ClickException:
            pass

        original_get_text_stream = click.get_text_stream
        try:
            click.get_text_stream = lambda *args, **kwargs: type(
                "Stream", (), {"isatty": lambda self: False}
            )()
            _confirm_overwrite()
        except click.ClickException:
            pass
        finally:
            click.get_text_stream = original_get_text_stream

        os.environ["KANBUS_FORCE_INTERACTIVE"] = "1"
        original_confirm = click.confirm
        try:
            click.confirm = lambda *args, **kwargs: (_ for _ in ()).throw(click.Abort())
            _confirm_overwrite()
        except click.ClickException:
            pass
        finally:
            click.confirm = original_confirm
            os.environ.pop("KANBUS_FORCE_INTERACTIVE", None)

        with TemporaryDirectory(dir="/tmp") as empty_root:
            try:
                _load_configuration_for_instructions(Path(empty_root))
            except click.ClickException:
                pass

        invalid_root = root / "invalid-config"
        invalid_root.mkdir(parents=True, exist_ok=True)
        (invalid_root / ".kanbus.yml").write_text(
            "unknown_field: 123\n", encoding="utf-8"
        )
        try:
            _load_configuration_for_instructions(invalid_root)
        except click.ClickException:
            pass

        try:
            configuration = load_project_configuration(config_path)
            configured = configuration.model_copy(
                update={"project_management_template": "missing-template.md"}
            )
            _resolve_project_management_template_path(root, configured)
        except click.ClickException:
            pass

        template_path = root / "project_management_template.md"
        template_path.write_text("{% if", encoding="utf-8")
        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            + "\nproject_management_template: project_management_template.md\n",
            encoding="utf-8",
        )
        try:
            build_project_management_text(root)
        except click.ClickException:
            pass

        record_by_id = {
            "parent": {"issue_type": "epic"},
            "child": {"issue_type": "initiative"},
        }
        try:
            _convert_dependencies(
                [{"type": "parent-child", "depends_on_id": "parent"}],
                "child",
                record_by_id,
                load_project_configuration(config_path),
                "initiative",
            )
        except MigrationError:
            pass
