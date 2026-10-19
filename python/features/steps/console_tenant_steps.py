"""Exercise the real kbsc tenant boundary used by both CLI implementations."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPResponse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from behave import then

from features.steps.console_ui_steps import _allocate_port, _kbsc_binary_path

TENANTS = ("alpha/project", "beta/project", "alpha/other")


def _request(base: str, path: str, event: dict | None = None) -> HTTPResponse:
    """Send a bounded HTTP request to the fixture console."""
    request = urllib.request.Request(
        base + path,
        data=json.dumps(event).encode() if event is not None else None,
        headers={"Content-Type": "application/json", "X-Kanbus-Console": "1"},
    )
    return urllib.request.urlopen(request, timeout=3)


@contextmanager
def _server(context: object, multi: bool = True) -> Iterator[str]:
    """Start an isolated console and always reap the fixture process."""
    root = Path(context.working_directory)
    if multi:
        for tenant in TENANTS:
            tenant_root = root / tenant
            (tenant_root / "project" / "issues").mkdir(parents=True, exist_ok=True)
            (tenant_root / ".kanbus.yml").write_text((root / ".kanbus.yml").read_text())
    port = _allocate_port()
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("KANBUS_", "CONSOLE_"))
    }
    environment.update(
        CONSOLE_PORT=str(port),
        CONSOLE_DATA_ROOT=str(root),
        CONSOLE_TENANT_MODE="multi" if multi else "single",
        KANBUS_NO_DAEMON="1",
    )
    process = subprocess.Popen(
        [str(_kbsc_binary_path())],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with _request(base, "/api/auth/bootstrap"):
                    break
            except (OSError, urllib.error.URLError):
                assert process.poll() is None, "kbsc exited during startup"
                time.sleep(0.05)
        else:
            raise AssertionError("kbsc did not become ready")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=5)


def _post(base: str, tenant: str, event: dict) -> None:
    """Post an event to the route-selected tenant."""
    with _request(base, f"/{tenant}/api/notifications", event) as response:
        assert response.status == 200


def _state(base: str, tenant: str) -> dict:
    """Read the state of the route-selected tenant."""
    with _request(base, f"/{tenant}/api/ui-state") as response:
        return json.load(response)


def _event(response: HTTPResponse) -> dict:
    """Read the next SSE data event with the connection's bounded timeout."""
    while line := response.readline():
        if line.startswith(b"data: "):
            return json.loads(line[6:])
    raise AssertionError("SSE stream closed without an event")


@then("focus and search state stays within its console tenant")
def tenant_state(context: object) -> None:
    """Verify focus, search, clears and persisted state for independent tenants.

    :param context: Behave scenario context with a temporary project.
    """
    with _server(context) as base:
        for index, tenant in enumerate(TENANTS):
            _post(base, tenant, {"type": "issue_focused", "issue_id": str(index)})
            _post(
                base,
                tenant,
                {
                    "type": "ui_control",
                    "action": {"action": "set_search", "query": tenant},
                },
            )
        for index, tenant in enumerate(TENANTS):
            assert _state(base, tenant)["focused_issue_id"] == str(index)
            assert _state(base, tenant)["search_query"] == tenant
        _post(
            base,
            TENANTS[0],
            {"type": "ui_control", "action": {"action": "clear_focus"}},
        )
        assert _state(base, TENANTS[0])["focused_issue_id"] is None
        assert _state(base, TENANTS[1])["focused_issue_id"] == "1"
    with _server(context) as base:
        for index, tenant in enumerate(TENANTS):
            state = _state(base, tenant)
            assert state["focused_issue_id"] == (str(index) if index else None)
            assert state["search_query"] == tenant


@then("live and replayed notifications stay within their console tenant")
def tenant_delivery(context: object) -> None:
    """Use per-tenant sentinels to detect cross-delivery without timing guesses.

    :param context: Behave scenario context with a temporary project.
    """
    with _server(context) as base:
        with (
            _request(base, "/alpha/project/api/events/realtime") as alpha,
            _request(base, "/beta/project/api/events/realtime") as beta,
            _request(base, "/alpha/other/api/events/realtime") as other,
        ):
            focus = {"type": "issue_focused", "issue_id": "alpha-focus"}
            marker = {"type": "issue_focused", "issue_id": "beta-marker"}
            other_marker = {"type": "issue_focused", "issue_id": "other-marker"}
            _post(base, TENANTS[0], {**focus, "account": "beta", "project": "project"})
            _post(base, TENANTS[1], marker)
            _post(base, TENANTS[2], other_marker)
            assert _event(alpha) == focus
            assert _event(beta) == marker
            assert _event(other) == other_marker
            issue = {
                "id": "private-alpha",
                "title": "Private alpha issue",
                "description": "",
                "type": "task",
                "status": "open",
                "priority": 2,
                "labels": [],
                "dependencies": [],
                "comments": [],
                "created_at": "2026-10-19T00:00:00Z",
                "updated_at": "2026-10-19T00:00:00Z",
            }
            update = {
                "type": "issue_updated",
                "issue_id": "private-alpha",
                "issue_data": issue,
            }
            _post(base, TENANTS[0], update)
            _post(base, TENANTS[1], marker)
            _post(base, TENANTS[2], other_marker)
            assert _event(alpha)["issue_data"]["title"] == "Private alpha issue"
            assert _event(beta) == marker
            assert _event(other) == other_marker
        for tenant, issue_id in zip(
            TENANTS, ("alpha-focus", "beta-marker", "other-marker")
        ):
            with _request(base, f"/{tenant}/api/events/realtime") as replay:
                assert _event(replay)["issue_id"] == issue_id
        _post(
            base,
            TENANTS[0],
            {"type": "ui_control", "action": {"action": "clear_focus"}},
        )
        _post(
            base,
            TENANTS[0],
            {
                "type": "ui_control",
                "action": {"action": "set_search", "query": "alpha-private"},
            },
        )
        with _request(base, "/alpha/project/api/events/realtime") as replay:
            assert _event(replay)["action"]["query"] == "alpha-private"
        with _request(base, "/beta/project/api/events/realtime") as replay:
            assert _event(replay)["issue_id"] == "beta-marker"


@then("root console notification routes require a tenant")
def tenant_required(context: object) -> None:
    """Reject unscoped, invalid and unknown tenants even with client selectors.

    :param context: Behave scenario context with a temporary project.
    """
    with _server(context) as base:
        for path, event, status in (
            ("/api/ui-state?account=alpha&project=project", None, 400),
            ("/api/events/realtime", None, 400),
            ("/api/notifications", {"type": "issue_deleted", "issue_id": "x"}, 400),
            ("/missing/project/api/ui-state", None, 404),
            ("/..%2Falpha/project/api/ui-state", None, 400),
        ):
            try:
                with _request(base, path, event):
                    raise AssertionError(f"{path} unexpectedly succeeded")
            except urllib.error.HTTPError as error:
                assert error.code == status, (path, error.code)


@then("single tenant console notifications retain their state and stream")
def single_tenant(context: object) -> None:
    """Keep root routes, alias routes and state persistence in single mode.

    :param context: Behave scenario context with a temporary project.
    """
    with _server(context, multi=False) as base:
        with _request(base, "/api/events/realtime") as stream:
            focus = {"type": "issue_focused", "issue_id": "local-focus"}
            with _request(base, "/api/notifications", focus):
                pass
            assert _event(stream) == focus
            search = {
                "type": "ui_control",
                "action": {"action": "set_search", "query": "single-search"},
            }
            _post(base, "alpha/project", search)
            assert _event(stream) == search
        with _request(base, "/api/ui-state") as response:
            state = json.load(response)
            assert state["focused_issue_id"] == "local-focus"
            assert state["search_query"] == "single-search"
    with _server(context, multi=False) as base:
        with _request(base, "/api/ui-state") as response:
            state = json.load(response)
            assert state["focused_issue_id"] == "local-focus"
            assert state["search_query"] == "single-search"


@then("tenant console persistence rejects redirected project and cache paths")
def tenant_persistence_boundary(context: object) -> None:
    """Keep disk state inside the selected tenant despite redirected paths.

    :param context: Behave scenario context with a temporary project.
    """
    import shutil

    import yaml

    with _server(context) as base:
        _post(
            base,
            "beta/project",
            {
                "type": "ui_control",
                "action": {"action": "set_search", "query": "beta-private"},
            },
        )
        root = Path(context.working_directory)
        configuration_path = root / "alpha/project/.kanbus.yml"
        configuration = yaml.safe_load(configuration_path.read_text())
        configuration["project_directory"] = "../../beta/project/project"
        configuration_path.write_text(yaml.safe_dump(configuration))
        try:
            with _request(base, "/alpha/project/api/ui-state") as response:
                state = json.load(response)
                raise AssertionError(f"redirected tenant state was readable: {state}")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        configuration["project_directory"] = "project"
        configuration_path.write_text(yaml.safe_dump(configuration))
        cache = root / "alpha/project/project/.cache"
        cache.symlink_to(root / "beta/project/project/.cache", target_is_directory=True)
        try:
            with _request(base, "/alpha/project/api/ui-state"):
                raise AssertionError("redirected tenant cache was readable")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        alias = root / "alpha/other"
        shutil.rmtree(alias)
        alias.symlink_to(root / "beta/project", target_is_directory=True)
        try:
            with _request(base, "/alpha/other/api/ui-state"):
                raise AssertionError("aliased tenant root was readable")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        cache.unlink()
        assert _state(base, "alpha/project")["search_query"] is None
        configuration["project_directory"] = "../../beta/project/project"
        configuration_path.write_text(yaml.safe_dump(configuration))
        _post(
            base,
            "alpha/project",
            {
                "type": "ui_control",
                "action": {"action": "set_search", "query": "alpha-private"},
            },
        )
        persisted = json.loads(
            (root / "beta/project/project/.cache/console_state.json").read_text()
        )
        assert persisted["search_query"] == "beta-private"
        assert _state(base, "beta/project")["search_query"] == "beta-private"
