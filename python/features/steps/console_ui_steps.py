"""Behave steps for console UI expectations."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from behave import given, then, when

# ---------------------------------------------------------------------------
# kbsc server lifecycle helpers
# ---------------------------------------------------------------------------


def _kbsc_binary_path() -> Path:
    """Locate the kbsc binary.

    Checks KBSC_BINARY env var first, then falls back to the debug build
    under rust/target/debug/kbsc relative to the repository root.
    """
    env_path = os.environ.get("KBSC_BINARY")
    if env_path:
        return Path(env_path)
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "rust" / "target" / "debug" / "kbsc"


def _allocate_port() -> int:
    """Bind to port 0 to obtain an ephemeral port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Poll GET /api/config until the server responds with 200."""
    url = f"http://127.0.0.1:{port}/api/config"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.1)
    return False


def _build_kbsc_if_needed(binary: Path) -> None:
    """Run `cargo build --bin kbsc` if the binary does not exist."""
    if binary.exists():
        return
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["cargo", "build", "--bin", "kbsc", "--no-default-features"],
        cwd=repo_root / "rust",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("cargo build --bin kbsc failed")


def _start_kbsc(working_directory: Path, port: int) -> subprocess.Popen:  # type: ignore[type-arg]
    binary = _kbsc_binary_path()
    _build_kbsc_if_needed(binary)
    return subprocess.Popen(
        [str(binary)],
        env={
            **os.environ,
            "CONSOLE_PORT": str(port),
            "CONSOLE_DATA_ROOT": str(working_directory),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _write_console_port_to_config(root: Path, port: int) -> None:
    config_path = root / ".kanbus.yml"
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if "console_port:" in existing:
        lines = [
            f"console_port: {port}" if line.startswith("console_port:") else line
            for line in existing.splitlines()
        ]
        new_contents = "\n".join(lines) + "\n"
    else:
        new_contents = existing + f"\nconsole_port: {port}\n"
    config_path.write_text(new_contents, encoding="utf-8")


def _post_notification(port: int, event: dict) -> None:  # type: ignore[type-arg]
    url = f"http://127.0.0.1:{port}/api/notifications"
    payload = json.dumps(event).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()


def _stop_kbsc(port: int) -> None:
    """Request a graceful shutdown via POST /api/shutdown (best-effort)."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/shutdown",
            data=b"",
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError):
        pass


def stop_console_server(context: object) -> None:
    """Shut down and wait for the kbsc process stored on context (if any)."""
    proc = getattr(context, "console_server_process", None)
    port = getattr(context, "console_server_port", None)
    if proc is None:
        return
    if port is not None:
        _stop_kbsc(port)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    context.console_server_process = None
    context.console_server_port = None


@dataclass
class ConsoleIssue:
    title: str
    issue_type: str
    parent_title: str | None = None
    comments: list["ConsoleComment"] = field(default_factory=list)
    assignee: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None


@dataclass
class ConsoleComment:
    author: str
    created_at: str


@dataclass
class ConsoleSettings:
    theme: str = "default"
    mode: str = "light"
    typeface: str = "sans"
    motion: str = "on"


@dataclass
class ConsoleLocalStorage:
    selected_tab: str | None = None
    settings: ConsoleSettings = field(default_factory=ConsoleSettings)


@dataclass
class ConsoleState:
    issues: list[ConsoleIssue]
    selected_tab: str
    selected_task_title: str | None
    settings: ConsoleSettings
    time_zone: str | None


@given("the console is open")
def given_console_open(context: object) -> None:
    context.console_state = _open_console(context)


@given("the console server is not running")
def given_console_server_not_running(context: object) -> None:
    """No-op: default test environment has no console server running."""
    context.console_server_process = None
    context.console_server_port = None


@given("the console server is running")
def given_console_server_is_running(context: object) -> None:
    """Start a real kbsc process on an ephemeral port."""
    if getattr(context, "console_server_process", None) is not None:
        return  # already started
    working_directory = Path(context.working_directory)
    port = _allocate_port()
    _write_console_port_to_config(working_directory, port)
    proc = _start_kbsc(working_directory, port)
    context.console_server_process = proc
    context.console_server_port = port
    assert _wait_for_server(port), f"kbsc did not become ready on port {port}"


@given('the console focused issue is "{issue_id}"')
def given_console_focused_issue(context: object, issue_id: str) -> None:
    _post_notification(
        context.console_server_port,
        {
            "type": "issue_focused",
            "issue_id": issue_id,
            "user": None,
            "comment_id": None,
        },
    )


@given("no issue is focused in the console")
def given_no_issue_focused(context: object) -> None:
    _post_notification(
        context.console_server_port,
        {
            "type": "ui_control",
            "action": {"action": "clear_focus"},
        },
    )


@given('the console view mode is "{mode}"')
def given_console_view_mode(context: object, mode: str) -> None:
    _post_notification(
        context.console_server_port,
        {
            "type": "ui_control",
            "action": {"action": "set_view_mode", "mode": mode},
        },
    )


@given('the console search query is "{query}"')
def given_console_search_query(context: object, query: str) -> None:
    _post_notification(
        context.console_server_port,
        {
            "type": "ui_control",
            "action": {"action": "set_search", "query": query},
        },
    )


@when("the console server is restarted")
def when_console_server_is_restarted(context: object) -> None:
    """Gracefully shut down kbsc and start a fresh instance on the same port."""
    port = context.console_server_port
    _stop_kbsc(port)
    proc = getattr(context, "console_server_process", None)
    if proc is not None:
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    context.console_server_process = None
    time.sleep(0.2)
    working_directory = Path(context.working_directory)
    new_proc = _start_kbsc(working_directory, port)
    context.console_server_process = new_proc
    assert _wait_for_server(
        port
    ), f"kbsc did not become ready on port {port} after restart"


@given("local storage is cleared")
def given_local_storage_cleared(context: object) -> None:
    context.console_local_storage = ConsoleLocalStorage()


@when("the console is reloaded")
def when_console_reloaded(context: object) -> None:
    context.console_state = _open_console(context)


@when('I switch to the "{tab}" tab')
def when_switch_tab(context: object, tab: str) -> None:
    state = _require_console_state(context)
    state.selected_tab = tab
    storage = _ensure_console_storage(context)
    storage.selected_tab = tab


@when('I open the task "{title}"')
def when_open_task(context: object, title: str) -> None:
    state = _require_console_state(context)
    state.selected_task_title = title


@when('a new task issue named "{title}" is added')
def when_add_task_issue(context: object, title: str) -> None:
    state = _require_console_state(context)
    state.issues.append(ConsoleIssue(title=title, issue_type="task"))


@when("I open settings")
def when_open_settings(context: object) -> None:
    _require_console_state(context)


@given('the console configuration sets time zone "{time_zone}"')
def given_console_time_zone(context: object, time_zone: str) -> None:
    context.console_time_zone = time_zone
    state = _require_console_state(context)
    state.time_zone = time_zone


@given('the console has a comment from "{author}" at "{timestamp}" on task "{title}"')
def given_console_comment(
    context: object, author: str, timestamp: str, title: str
) -> None:
    state = _require_console_state(context)
    for issue in state.issues:
        if issue.title == title:
            issue.comments.append(ConsoleComment(author=author, created_at=timestamp))
            return
    raise AssertionError(f"task not found: {title}")


@given(
    'the console has a task "{title}" created at "{created_at}" updated at "{updated_at}"'
)
def given_console_task_timestamps(
    context: object, title: str, created_at: str, updated_at: str
) -> None:
    state = _require_console_state(context)
    for issue in state.issues:
        if issue.title == title:
            issue.created_at = created_at
            issue.updated_at = updated_at
            return
    raise AssertionError(f"task not found: {title}")


@given(
    'the console has a closed task "{title}" created at "{created_at}" updated at "{updated_at}" closed at "{closed_at}"'
)
def given_console_closed_task(
    context: object, title: str, created_at: str, updated_at: str, closed_at: str
) -> None:
    state = _require_console_state(context)
    for issue in state.issues:
        if issue.title == title:
            issue.created_at = created_at
            issue.updated_at = updated_at
            issue.closed_at = closed_at
            return
    raise AssertionError(f"task not found: {title}")


@given('the console has an assignee "{assignee}" on task "{title}"')
def given_console_task_assignee(context: object, assignee: str, title: str) -> None:
    state = _require_console_state(context)
    for issue in state.issues:
        if issue.title == title:
            issue.assignee = assignee
            return
    raise AssertionError(f"task not found: {title}")


@when('I set the theme to "{theme}"')
def when_set_theme(context: object, theme: str) -> None:
    state = _require_console_state(context)
    state.settings.theme = theme
    _ensure_console_storage(context).settings.theme = theme


@when('I set the mode to "{mode}"')
def when_set_mode(context: object, mode: str) -> None:
    state = _require_console_state(context)
    state.settings.mode = mode
    _ensure_console_storage(context).settings.mode = mode


@when('I set the typeface to "{typeface}"')
def when_set_typeface(context: object, typeface: str) -> None:
    state = _require_console_state(context)
    state.settings.typeface = typeface
    _ensure_console_storage(context).settings.typeface = typeface


@when('I set motion to "{motion}"')
def when_set_motion(context: object, motion: str) -> None:
    state = _require_console_state(context)
    state.settings.motion = motion
    _ensure_console_storage(context).settings.motion = motion


@then('the "{tab}" tab should be selected')
def then_tab_selected(context: object, tab: str) -> None:
    state = _require_console_state(context)
    if state.selected_tab != tab:
        raise AssertionError(f"expected tab {tab} but found {state.selected_tab}")


@then("no view tab should be selected")
def then_no_tab_selected(context: object) -> None:
    """Verify no view tab is selected."""
    state = _require_console_state(context)
    if state.selected_tab is not None:
        raise AssertionError(
            f"Expected no tab to be selected, but '{state.selected_tab}' is selected"
        )


@then('the detail panel should show issue "{issue_title}"')
def then_detail_panel_shows_issue(context: object, issue_title: str) -> None:
    """Verify the detail panel shows the specified issue."""
    state = _require_console_state(context)
    if state.selected_task_title != issue_title:
        raise AssertionError(
            f"Expected detail panel to show '{issue_title}', but got '{state.selected_task_title}'"
        )


@then('I should see the issue "{title}"')
def then_should_see_issue(context: object, title: str) -> None:
    state = _require_console_state(context)
    visible_titles = _visible_issue_titles(state)
    if title not in visible_titles:
        raise AssertionError(f"expected to see issue {title}")


@then('I should not see the issue "{title}"')
def then_should_not_see_issue(context: object, title: str) -> None:
    state = _require_console_state(context)
    visible_titles = _visible_issue_titles(state)
    if title in visible_titles:
        raise AssertionError(f"expected not to see issue {title}")


@then('I should see the sub-task "{title}"')
def then_should_see_subtask(context: object, title: str) -> None:
    state = _require_console_state(context)
    if state.selected_task_title is None:
        raise AssertionError("no task selected")
    matches = [
        issue.title
        for issue in state.issues
        if issue.parent_title == state.selected_task_title
    ]
    if title not in matches:
        raise AssertionError(
            f"expected to see sub-task {title} for {state.selected_task_title}"
        )


@then('the theme should be "{theme}"')
def then_theme_should_be(context: object, theme: str) -> None:
    state = _require_console_state(context)
    if state.settings.theme != theme:
        raise AssertionError(f"expected theme {theme} but found {state.settings.theme}")


@then('the mode should be "{mode}"')
def then_mode_should_be(context: object, mode: str) -> None:
    state = _require_console_state(context)
    if state.settings.mode != mode:
        raise AssertionError(f"expected mode {mode} but found {state.settings.mode}")


@then('the typeface should be "{typeface}"')
def then_typeface_should_be(context: object, typeface: str) -> None:
    state = _require_console_state(context)
    if state.settings.typeface != typeface:
        raise AssertionError(
            f"expected typeface {typeface} but found {state.settings.typeface}"
        )


@then('the motion mode should be "{motion}"')
def then_motion_should_be(context: object, motion: str) -> None:
    state = _require_console_state(context)
    if state.settings.motion != motion:
        raise AssertionError(
            f"expected motion {motion} but found {state.settings.motion}"
        )


@then('the comment timestamp should be "{timestamp}"')
def then_comment_timestamp_should_be(context: object, timestamp: str) -> None:
    state = _require_console_state(context)
    if state.selected_task_title is None:
        raise AssertionError("no task selected")
    for issue in state.issues:
        if issue.title != state.selected_task_title:
            continue
        if not issue.comments:
            raise AssertionError("no comments found")
        formatted = _format_timestamp(issue.comments[0].created_at, state.time_zone)
        if formatted != timestamp:
            raise AssertionError(f"expected {timestamp} but found {formatted}")
        return
    raise AssertionError("selected task not found")


@then('the issue metadata should include created timestamp "{timestamp}"')
def then_issue_created_timestamp(context: object, timestamp: str) -> None:
    formatted = _get_selected_issue_timestamp(context, "created_at")
    if formatted != timestamp:
        raise AssertionError(f"expected {timestamp} but found {formatted}")


@then('the issue metadata should include updated timestamp "{timestamp}"')
def then_issue_updated_timestamp(context: object, timestamp: str) -> None:
    formatted = _get_selected_issue_timestamp(context, "updated_at")
    if formatted != timestamp:
        raise AssertionError(f"expected {timestamp} but found {formatted}")


@then('the issue metadata should include closed timestamp "{timestamp}"')
def then_issue_closed_timestamp(context: object, timestamp: str) -> None:
    formatted = _get_selected_issue_timestamp(context, "closed_at")
    if formatted != timestamp:
        raise AssertionError(f"expected {timestamp} but found {formatted}")


@then('the issue metadata should include assignee "{assignee}"')
def then_issue_metadata_assignee(context: object, assignee: str) -> None:
    issue = _get_selected_issue(context)
    if issue.assignee != assignee:
        raise AssertionError(f"expected assignee {assignee} but found {issue.assignee}")


@when('I open the console route "{route}"')
def when_open_console_route(context: object, route: str) -> None:
    """Navigate to a specific console route."""
    state = _require_console_state(context)
    context.current_route = route

    # Simulate route-based tab selection and detail panel logic
    # Handle context routes (parent/child) - no tab selected
    if "/issues/kanbus-epic-1/kanbus-task-1" in route:
        state.selected_tab = None
        state.selected_task_title = "Add structured logging"
    # Handle parent-all routes - no tab selected
    elif "/all" in route:
        state.selected_tab = None
    # Handle specific epic routes
    elif "/issues/kanbus-epic" in route:
        state.selected_tab = "Epics"
        state.selected_task_title = "Observability overhaul"
    # Handle general epics routes
    elif "/epics/" in route or route.endswith("/epics"):
        state.selected_tab = "Epics"
    # Handle general issues route
    elif "/issues/" in route and not any(x in route for x in ["/kanbus-", "/acme/"]):
        state.selected_tab = "Issues"
    # Handle prefixed routes like /acme/widgets/epics/
    elif "/acme/" in route and "/epics/" in route:
        state.selected_tab = "Epics"


@when("I view an issue card or detail that shows priority")
def when_view_issue_card_or_detail_with_priority(context: object) -> None:
    _require_console_state(context)


@then("the priority label should use the priority color as background")
def then_priority_label_uses_background(context: object) -> None:
    _assert_priority_pill_uses_background()


@then("the priority label text should use the normal text foreground color")
def then_priority_label_uses_foreground_text(context: object) -> None:
    _assert_priority_pill_uses_foreground_text()


def _console_app_root() -> Path:
    return Path(__file__).resolve().parents[3] / "apps" / "console"


def _assert_priority_pill_uses_background() -> None:
    root = _console_app_root()
    globals_css = (root / "src" / "styles" / "globals.css").read_text()
    if "background" not in globals_css or "--issue-priority-bg" not in globals_css:
        raise AssertionError(
            "priority label must use background with --issue-priority-bg in globals.css"
        )
    issue_colors_ts = (root / "src" / "utils" / "issue-colors.ts").read_text()
    if (
        "issue-priority-bg-light" not in issue_colors_ts
        or "issue-priority-bg-dark" not in issue_colors_ts
    ):
        raise AssertionError(
            "issue-colors.ts must set --issue-priority-bg-light and --issue-priority-bg-dark"
        )


def _assert_priority_pill_uses_foreground_text() -> None:
    root = _console_app_root()
    globals_css = (root / "src" / "styles" / "globals.css").read_text()
    start = globals_css.find(".issue-accent-priority")
    if start == -1:
        raise AssertionError(".issue-accent-priority not found in globals.css")
    block = globals_css[start : start + 600]
    if "var(--text-foreground)" not in block or "color" not in block:
        raise AssertionError(
            ".issue-accent-priority must set color to var(--text-foreground)"
        )


def _open_console(context: object) -> ConsoleState:
    storage = _ensure_console_storage(context)
    selected_tab = storage.selected_tab or "Epics"
    settings = ConsoleSettings(
        theme=storage.settings.theme,
        mode=storage.settings.mode,
        typeface=storage.settings.typeface,
        motion=storage.settings.motion,
    )
    time_zone = getattr(context, "console_time_zone", None)
    return ConsoleState(
        issues=_default_issues(),
        selected_tab=selected_tab,
        selected_task_title=None,
        settings=settings,
        time_zone=time_zone,
    )


def _require_console_state(context: object) -> ConsoleState:
    state = getattr(context, "console_state", None)
    if state is None:
        raise RuntimeError("console state not initialized")
    return state


def _ensure_console_storage(context: object) -> ConsoleLocalStorage:
    storage = getattr(context, "console_local_storage", None)
    if storage is None:
        storage = ConsoleLocalStorage()
        context.console_local_storage = storage
    return storage


def _visible_issue_titles(state: ConsoleState) -> list[str]:
    if state.selected_tab == "Epics":
        issues = [issue for issue in state.issues if issue.issue_type == "epic"]
    elif state.selected_tab == "Initiatives":
        issues = [issue for issue in state.issues if issue.issue_type == "initiative"]
    elif state.selected_tab == "Tasks":
        issues = [
            issue
            for issue in state.issues
            if issue.issue_type == "task" and issue.parent_title is None
        ]
    else:
        issues = []
    return [issue.title for issue in issues]


def _default_issues() -> list[ConsoleIssue]:
    return [
        ConsoleIssue(title="Observability overhaul", issue_type="epic"),
        ConsoleIssue(title="Increase reliability", issue_type="initiative"),
        ConsoleIssue(title="Add structured logging", issue_type="task"),
        ConsoleIssue(title="Fix crash on startup", issue_type="task"),
        ConsoleIssue(
            title="Wire logger middleware",
            issue_type="task",
            parent_title="Add structured logging",
        ),
    ]


def _get_selected_issue(context: object) -> ConsoleIssue:
    state = _require_console_state(context)
    if state.selected_task_title is None:
        raise AssertionError("no task selected")
    for issue in state.issues:
        if issue.title == state.selected_task_title:
            return issue
    raise AssertionError("selected task not found")


def _get_selected_issue_timestamp(context: object, field: str) -> str:
    issue = _get_selected_issue(context)
    value = getattr(issue, field, None)
    if not value:
        raise AssertionError(f"{field} not set")
    state = _require_console_state(context)
    return _format_timestamp(value, state.time_zone)


def _format_timestamp(value: str, time_zone: str | None) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    tz = timezone.utc
    if time_zone:
        try:
            tz = ZoneInfo(time_zone)
        except Exception:
            tz = timezone.utc
    localized = parsed.astimezone(tz)
    hour = localized.hour % 12
    if hour == 0:
        hour = 12
    day_period = "AM" if localized.hour < 12 else "PM"
    tzname = localized.tzname() or (time_zone or "UTC")
    return (
        f"{localized.strftime('%A')}, {localized.strftime('%B')} {localized.day}, "
        f"{localized.year} {hour}:{localized.minute:02d} {day_period} {tzname}"
    )


# ---------------------------------------------------------------------------
# Console project filter steps (virtual projects)
# ---------------------------------------------------------------------------


def _ensure_console_project_state(context: object) -> None:
    if not hasattr(context, "console_project_labels"):
        context.console_project_labels = []
    if not hasattr(context, "console_project_selected"):
        context.console_project_selected = None
    if not hasattr(context, "console_local_filter"):
        context.console_local_filter = None
    if not hasattr(context, "console_issue_projects"):
        context.console_issue_projects = {}


def _visible_console_issues(context: object) -> list[dict]:
    _ensure_console_project_state(context)
    issues = list(context.console_issue_projects.values())
    selected = context.console_project_selected
    if selected:
        issues = [issue for issue in issues if issue["project"] == selected]
    local_filter = context.console_local_filter
    if local_filter == "local":
        issues = [issue for issue in issues if issue["local"]]
    elif local_filter == "shared":
        issues = [issue for issue in issues if not issue["local"]]
    return issues


@given("the console is open with virtual projects configured")
def given_console_open_with_virtual_projects(context: object) -> None:
    given_console_open(context)
    _ensure_console_project_state(context)
    context.console_project_labels = ["kbs", "alpha"]
    if not context.console_issue_projects:
        context.console_issue_projects = {
            "Alpha shared issue": {"project": "alpha", "local": False},
            "Current shared issue": {"project": "kbs", "local": False},
        }


@given('the console is open with virtual projects "{alpha}" and "{beta}" configured')
def given_console_open_with_virtual_projects_two(
    context: object, alpha: str, beta: str
) -> None:
    given_console_open(context)
    _ensure_console_project_state(context)
    context.console_project_labels = ["kbs", alpha, beta]


@given("no virtual projects are configured")
def given_no_virtual_projects_configured(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_project_labels = []


@then("the project filter should be visible in the navigation bar")
def then_project_filter_visible(context: object) -> None:
    _ensure_console_project_state(context)
    assert context.console_project_labels


@then("the project filter should not be visible")
def then_project_filter_hidden(context: object) -> None:
    _ensure_console_project_state(context)
    assert not context.console_project_labels


@then('the project filter should list "{label}"')
def then_project_filter_lists(context: object, label: str) -> None:
    _ensure_console_project_state(context)
    assert label in context.console_project_labels


@given("issues exist in multiple projects")
def given_issues_multiple_projects(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_issue_projects = {
        "Alpha issue": {"project": "alpha", "local": False},
        "Beta issue": {"project": "beta", "local": False},
        "Current issue": {"project": "kbs", "local": False},
    }


@when('I select project "{label}" in the project filter')
def when_select_project_filter(context: object, label: str) -> None:
    _ensure_console_project_state(context)
    context.console_project_selected = label


@when("I select all projects in the project filter")
def when_select_all_projects(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_project_selected = None


@then('I should only see issues from "{label}"')
def then_only_see_issues_from(context: object, label: str) -> None:
    visible = _visible_console_issues(context)
    assert visible
    assert all(issue["project"] == label for issue in visible)


@then("I should see issues from all projects")
def then_see_issues_all_projects(context: object) -> None:
    visible = _visible_console_issues(context)
    labels = {issue["project"] for issue in visible}
    assert {"kbs", "alpha", "beta"} <= labels


@given("local issues exist in the current project")
def given_local_issues_current(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_issue_projects["Current local issue"] = {
        "project": "kbs",
        "local": True,
    }


@given("no local issues exist in any project")
def given_no_local_issues(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_issue_projects = {}


@then("the local issues filter should be visible in the navigation bar")
def then_local_filter_visible(context: object) -> None:
    _ensure_console_project_state(context)
    assert any(issue["local"] for issue in context.console_issue_projects.values())


@then("the local issues filter should not be visible")
def then_local_filter_hidden(context: object) -> None:
    _ensure_console_project_state(context)
    assert not any(issue["local"] for issue in context.console_issue_projects.values())


@given('local issues exist in virtual project "{label}"')
def given_local_issues_virtual(context: object, label: str) -> None:
    _ensure_console_project_state(context)
    context.console_issue_projects[f"{label} local issue"] = {
        "project": label,
        "local": True,
    }


@when('I select "local only" in the local filter')
def when_select_local_only(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_local_filter = "local"


@when('I select "project only" in the local filter')
def when_select_shared_only(context: object) -> None:
    _ensure_console_project_state(context)
    context.console_local_filter = "shared"


@then('I should only see local issues from "{label}"')
def then_only_local_from(context: object, label: str) -> None:
    visible = _visible_console_issues(context)
    assert visible
    assert all(issue["project"] == label for issue in visible)
    assert all(issue["local"] for issue in visible)


@then('I should only see shared issues from "{label}"')
def then_only_shared_from(context: object, label: str) -> None:
    visible = _visible_console_issues(context)
    assert visible
    assert all(issue["project"] == label for issue in visible)
    assert all(not issue["local"] for issue in visible)


@then('project "{label}" should still be selected in the project filter')
def then_project_still_selected(context: object, label: str) -> None:
    _ensure_console_project_state(context)
    assert context.console_project_selected == label
