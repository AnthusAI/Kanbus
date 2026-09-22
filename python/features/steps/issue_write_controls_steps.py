"""Behave steps for the console issue write API (comments, status changes).

These exercise the real kbsc server over HTTP -- like the standup and
"console server is running" scenarios elsewhere in this suite -- rather
than the simulated, in-memory ConsoleState used by most other console
scenarios. "Given the console is open" only sets up that simulation, so
these steps provision a real project and a real running server on demand.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from behave import given, then, when

from features.steps.console_ui_steps import (
    _allocate_port,
    _start_kbsc,
    _wait_for_server,
    _write_console_port_to_config,
)
from features.steps.shared import (
    build_issue,
    initialize_default_project,
    write_issue_file,
)
from kanbus.project import load_project_directory as resolve_project_directory


def _ensure_real_console_server(context: object) -> str:
    """Provision a real project + running kbsc, returning its API base URL.

    Idempotent: reuses the server already started for this scenario, and
    only seeds issues from the simulated ConsoleState the first time.
    """
    if getattr(context, "issue_write_api_base", None) is not None:
        return context.issue_write_api_base

    if getattr(context, "working_directory", None) is None:
        initialize_default_project(context)

    project_dir = resolve_project_directory(Path(context.working_directory))
    for simulated in (
        getattr(getattr(context, "console_state", None), "issues", []) or []
    ):
        issue = build_issue(
            simulated.identifier,
            simulated.title,
            simulated.issue_type,
            simulated.status,
            None,
            [],
        )
        write_issue_file(project_dir, issue)

    port = _allocate_port()
    _write_console_port_to_config(Path(context.working_directory), port)
    proc = _start_kbsc(Path(context.working_directory), port, context)
    context.console_server_process = proc
    ready_port = _wait_for_server(port)
    assert ready_port is not None, f"kbsc did not become ready on port {port}"
    context.console_server_port = ready_port
    context.issue_write_api_base = f"http://127.0.0.1:{ready_port}/api"
    return context.issue_write_api_base


def _issue_write_request(
    context: object, issue_id: str, route: str, body: dict
) -> None:
    api_base = _ensure_real_console_server(context)
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}/issues/{issue_id}/{route}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            context.issue_write_status = resp.status
            context.issue_write_payload = json.loads(resp.read())
    except urllib.error.HTTPError as error:
        context.issue_write_status = error.code
        context.issue_write_payload = json.loads(error.read())


@given('the issue "{issue_id}" has a blocked router conversation')
def given_issue_has_blocked_router_conversation(context: object, issue_id: str) -> None:
    if getattr(context, "working_directory", None) is None:
        initialize_default_project(context)
    project_dir = resolve_project_directory(Path(context.working_directory))
    events_dir = project_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "router-conversation-blocked.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_id": "router-conversation-blocked",
                "issue_id": f"router:{issue_id}",
                "event_type": "router.conversation",
                "actor_id": "router",
                "occurred_at": "2026-09-19T20:00:00Z",
                "payload": {"lifecycle": "blocked", "action": "awaiting_reply"},
            }
        ),
        encoding="utf-8",
    )


@when('I add a comment through the issue write API for "{issue_id}" with text "{text}"')
def when_add_comment_through_api(context: object, issue_id: str, text: str) -> None:
    _issue_write_request(context, issue_id, "comments", {"text": text})


@when('I change status through the issue write API for "{issue_id}" to "{status}"')
def when_change_status_through_api(context: object, issue_id: str, status: str) -> None:
    _issue_write_request(context, issue_id, "status", {"status": status})


@then('the issue write API response should be successful with comment "{text}"')
def then_write_api_successful_comment(context: object, text: str) -> None:
    assert context.issue_write_status == 200, context.issue_write_payload
    assert context.issue_write_payload["issue"]["comments"][-1]["text"] == text


@then('the issue write API response should be successful with status "{status}"')
def then_write_api_successful_status(context: object, status: str) -> None:
    assert context.issue_write_status == 200, context.issue_write_payload
    assert context.issue_write_payload["issue"]["status"] == status


@then(
    'the issue write API response should fail with status {status:d} and error containing "{message}"'
)
def then_write_api_failed(context: object, status: int, message: str) -> None:
    assert context.issue_write_status == status, context.issue_write_payload
    assert message.lower() in context.issue_write_payload["error"].lower()


@then("the issue write API response should report the agent was resumed")
def then_write_api_reports_resumed(context: object) -> None:
    assert context.issue_write_payload.get("resumed") is True


@then('the issue write API response should include status "{status}"')
def then_write_api_includes_status(context: object, status: str) -> None:
    assert context.issue_write_payload["issue"]["status"] == status
