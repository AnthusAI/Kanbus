"""Behave steps for Jira pull synchronization."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse, parse_qs

from behave import given, then, when

from features.steps.shared import load_project_directory


def _find_free_port() -> int:
    """Find a free TCP port on localhost.

    :return: Available port number.
    :rtype: int
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _build_jira_issue(
    key: str,
    summary: str,
    issue_type: str,
    status: str,
    priority: str,
    parent_key: str = "",
) -> Dict[str, Any]:
    """Build a minimal Jira issue JSON payload.

    :param key: Jira issue key.
    :type key: str
    :param summary: Issue summary.
    :type summary: str
    :param issue_type: Jira issue type name.
    :type issue_type: str
    :param status: Jira status name.
    :type status: str
    :param priority: Jira priority name.
    :type priority: str
    :param parent_key: Optional parent Jira key.
    :type parent_key: str
    :return: Jira issue dict.
    :rtype: Dict[str, Any]
    """
    issue: Dict[str, Any] = {
        "key": key,
        "fields": {
            "summary": summary,
            "description": None,
            "issuetype": {"name": issue_type},
            "status": {"name": status},
            "priority": {"name": priority},
            "assignee": None,
            "reporter": {"displayName": "test-reporter"},
            "labels": [],
            "comment": {"comments": []},
            "created": "2026-01-01T00:00:00.000+0000",
            "updated": "2026-01-01T00:00:00.000+0000",
            "resolutiondate": None,
        },
    }
    if parent_key:
        issue["fields"]["parent"] = {"key": parent_key}
    return issue


def _start_fake_jira_server(issues: List[Dict[str, Any]], port: int) -> HTTPServer:
    """Start a fake Jira HTTP server on the given port.

    :param issues: List of Jira issue dicts to serve.
    :type issues: List[Dict[str, Any]]
    :param port: Port to listen on.
    :type port: int
    :return: Running HTTPServer instance.
    :rtype: HTTPServer
    """
    issues_snapshot = list(issues)

    class FakeJiraHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/rest/api/3/search/jql":
                params = parse_qs(parsed.query)
                start_at = int(params.get("startAt", ["0"])[0])
                max_results = int(params.get("maxResults", ["100"])[0])
                page = issues_snapshot[start_at : start_at + max_results]
                response = json.dumps(
                    {
                        "issues": page,
                        "total": len(issues_snapshot),
                        "startAt": start_at,
                        "maxResults": max_results,
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), FakeJiraHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _parse_issues_table(context: object) -> List[Dict[str, Any]]:
    """Parse the Gherkin table of issues from context.

    :param context: Behave context object.
    :type context: object
    :return: List of Jira issue dicts.
    :rtype: List[Dict[str, Any]]
    """
    issues = []
    for row in context.table:
        issues.append(
            _build_jira_issue(
                key=row["key"],
                summary=row["summary"],
                issue_type=row["type"],
                status=row["status"],
                priority=row["priority"],
                parent_key=row.get("parent", ""),
            )
        )
    return issues


@given("a fake Jira server is running with issues:")
def given_fake_jira_server(context: object) -> None:
    """Start a fake Jira HTTP server with the issues from the table.

    :param context: Behave context object.
    :type context: object
    """
    issues = _parse_issues_table(context)
    port = _find_free_port()
    server = _start_fake_jira_server(issues, port)
    context.fake_jira_server = server
    context.fake_jira_port = port
    context.fake_jira_issues = issues


@given("the Kanbus configuration includes Jira settings pointing at the fake server")
def given_jira_config(context: object) -> None:
    """Write a jira: block into the project .kanbus.yml.

    :param context: Behave context object.
    :type context: object
    """
    port = context.fake_jira_port
    config_path = Path(context.working_directory) / ".kanbus.yml"
    existing = config_path.read_text(encoding="utf-8")
    jira_config = (
        "\njira:\n"
        f"  url: http://127.0.0.1:{port}\n"
        "  project_key: AQ\n"
        "  sync_direction: pull\n"
        "  type_mappings:\n"
        "    Task: task\n"
        "    Bug: bug\n"
        "    Workstream: epic\n"
    )
    config_path.write_text(existing + jira_config, encoding="utf-8")
    context.environment_overrides["JIRA_API_TOKEN"] = "test-token"
    context.environment_overrides["JIRA_USER_EMAIL"] = "test@example.com"


@given("credentials are provided via .env file only")
def given_credentials_via_dotenv_only(context: object) -> None:
    """Create .env with JIRA credentials and remove them from environment overrides.

    The CLI must load .env automatically to succeed; credentials are not in the
    environment passed to the subprocess.
    """
    repository = Path(context.working_directory)
    dotenv_path = repository / ".env"
    dotenv_path.write_text(
        "JIRA_API_TOKEN=test-token\nJIRA_USER_EMAIL=test@example.com\n",
        encoding="utf-8",
    )
    context.environment_overrides.pop("JIRA_API_TOKEN", None)
    context.environment_overrides.pop("JIRA_USER_EMAIL", None)


@given('the environment variable "{name}" is unset')
def given_env_var_unset(context: object, name: str) -> None:
    """Remove an environment variable from the test overrides.

    :param context: Behave context object.
    :type context: object
    :param name: Environment variable name.
    :type name: str
    """
    context.environment_overrides.pop(name, None)
    import os

    context._unset_env_vars = getattr(context, "_unset_env_vars", [])
    context._unset_env_vars.append((name, os.environ.get(name)))
    os.environ.pop(name, None)


@then("{count:d} issue files should exist in the issues directory")
def then_issue_file_count(context: object, count: int) -> None:
    """Assert the number of issue JSON files in the issues directory.

    :param context: Behave context object.
    :type context: object
    :param count: Expected number of issue files.
    :type count: int
    """
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    actual = len(list(issues_dir.glob("*.json"))) if issues_dir.exists() else 0
    assert actual == count, f"Expected {count} issue files, found {actual}"


@then('an issue file with jira_key "{jira_key}" should exist with title "{title}"')
def then_issue_file_exists_with_title(
    context: object, jira_key: str, title: str
) -> None:
    """Assert an issue file with the given jira_key and title exists.

    :param context: Behave context object.
    :type context: object
    :param jira_key: Jira issue key stored in custom field.
    :type jira_key: str
    :param title: Expected issue title.
    :type title: str
    """
    issue = _find_issue_by_jira_key(context, jira_key)
    assert issue is not None, f"No issue found with jira_key {jira_key!r}"
    assert issue["title"] == title, f"Expected title {title!r}, got {issue['title']!r}"


@then('an issue file with jira_key "{jira_key}" should have type "{issue_type}"')
def then_issue_has_type(context: object, jira_key: str, issue_type: str) -> None:
    """Assert an issue file has the given type.

    :param context: Behave context object.
    :type context: object
    :param jira_key: Jira issue key.
    :type jira_key: str
    :param issue_type: Expected Kanbus issue type.
    :type issue_type: str
    """
    issue = _find_issue_by_jira_key(context, jira_key)
    assert issue is not None, f"No issue found with jira_key {jira_key!r}"
    actual = issue.get("type") or issue.get("issue_type")
    assert actual == issue_type, f"Expected type {issue_type!r}, got {actual!r}"


@then(
    'the issue with jira_key "{child_key}" should have a parent matching the issue with jira_key "{parent_key}"'
)
def then_issue_parent_matches(context: object, child_key: str, parent_key: str) -> None:
    """Assert the child issue's parent field matches the parent issue's Kanbus ID.

    :param context: Behave context object.
    :type context: object
    :param child_key: Jira key of the child issue.
    :type child_key: str
    :param parent_key: Jira key of the expected parent issue.
    :type parent_key: str
    """
    parent_issue = _find_issue_by_jira_key(context, parent_key)
    child_issue = _find_issue_by_jira_key(context, child_key)
    assert parent_issue is not None, f"No issue found with jira_key {parent_key!r}"
    assert child_issue is not None, f"No issue found with jira_key {child_key!r}"
    assert (
        child_issue.get("parent") == parent_issue["id"]
    ), f"Expected parent {parent_issue['id']!r}, got {child_issue.get('parent')!r}"


@then('the output should contain "{text}"')
def then_output_contains(context: object, text: str) -> None:
    """Assert that combined stdout+stderr contains the given text.

    :param context: Behave context object.
    :type context: object
    :param text: Expected text.
    :type text: str
    """
    import re as _re

    ansi_re = _re.compile(r"\x1b\[[0-9;]*m")
    combined = ansi_re.sub("", context.result.output or "")
    assert text in combined, f"Expected {text!r} in output, got:\n{combined}"


def _find_issue_by_jira_key(context: object, jira_key: str) -> Dict[str, Any] | None:
    """Find an issue JSON dict by its jira_key custom field.

    :param context: Behave context object.
    :type context: object
    :param jira_key: Jira issue key.
    :type jira_key: str
    :return: Issue dict or None.
    :rtype: Dict[str, Any] | None
    """
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    if not issues_dir.exists():
        return None
    for path in issues_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        custom = data.get("custom") or {}
        if custom.get("jira_key") == jira_key:
            return data
    return None
