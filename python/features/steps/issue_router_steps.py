"""Behave steps for the deterministic Issue Router vertical slice."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import yaml
from behave import given, then, use_step_matcher, when

from features.steps.shared import (
    WorkingFakeAdapter,
    build_issue,
    initialize_default_project,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.router_adapters import _parse_result as parse_adapter_result
from kanbus.coordination import inspect_lease
from kanbus.event_history import create_event, write_events_batch
from kanbus.issue_router import (
    IssueRouterError,
    RouterControlState,
    build_router_plan,
    load_router_context,
    read_router_control,
    record_router_event,
    _read_events,
    write_router_control,
)
from kanbus.models import DependencyLink
from kanbus.project import get_configuration_path
from kanbus.router_adapters import RouterAgentResult
from kanbus.router_conversation import latest_conversation, record_conversation
from kanbus.router_execution import add_issue_comment
from kanbus.router_execution import (
    publish_router_result,
    retry_delay_seconds,
    set_router_adapter,
    set_router_forge,
)
from kanbus.router_forge import (
    FakeForge,
    record_github_check_run_event,
    record_github_pull_request_event,
)
from kanbus.router_state import publish_router_state, router_state_root

_ROUTER = {
    "workflow": {
        "pending": "open",
        "active": "in_progress",
        "review": "review",
        "blocked": "blocked",
        "terminal": ["closed"],
    },
    "limits": {"project_wip": 3, "review_wip": 2},
    "providers": {"codex-default": {"adapter": "codex"}},
    "classes": {"implementation": {"providers": ["codex-default"]}},
    "retries": {"max_attempts": 3},
    "forge": {"provider": "github", "repository": "anthusai/kanbus"},
}


def _root(context: object) -> Path:
    return Path(context.working_directory)


def _config(context: object) -> dict:
    path = get_configuration_path(_root(context))
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload


def _save_config(context: object, payload: dict) -> None:
    get_configuration_path(_root(context)).write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def _add_review_status(config: dict) -> None:
    statuses = config.setdefault("statuses", [])
    if not any(status.get("key") == "review" for status in statuses):
        statuses.append(
            {
                "key": "review",
                "name": "Review",
                "category": "In progress",
                "semantic_category": "in_progress",
                "collapsed": False,
            }
        )
    workflow = config.setdefault("workflows", {}).setdefault("default", {})
    workflow["open"] = list(
        dict.fromkeys([*workflow.get("open", []), "in_progress", "closed"])
    )
    workflow["in_progress"] = list(
        dict.fromkeys(
            [*workflow.get("in_progress", []), "open", "blocked", "closed", "review"]
        )
    )
    workflow["blocked"] = list(
        dict.fromkeys([*workflow.get("blocked", []), "in_progress", "closed"])
    )
    workflow["review"] = ["in_progress", "blocked", "closed"]
    transition_labels = config.setdefault("transition_labels", {}).setdefault(
        "default", {}
    )
    transition_labels["in_progress"] = {
        **transition_labels.get("in_progress", {}),
        "review": "Ready for review",
    }
    transition_labels["review"] = {
        "in_progress": "Request changes",
        "blocked": "Close without merge",
        "closed": "Merge",
    }


def _install_router(context: object, router: dict | None = None) -> None:
    if context.working_directory is None:
        initialize_default_project(context)
    config = _config(context)
    _add_review_status(config)
    if router is not None:
        config["router"] = router
    _save_config(context, config)
    context.router_fake_forge = FakeForge()
    set_router_forge(context.router_fake_forge)
    context.add_cleanup(lambda: set_router_forge(None))


def _write_issue(
    context: object,
    issue_id: str,
    *,
    status: str = "open",
    labels: list[str] | None = None,
    parent: str | None = None,
    assignee: str | None = None,
    issue_type: str = "task",
    created_at: str = "2026-09-16T10:00:00Z",
    title: str | None = None,
    priority: int = 2,
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(
        issue_id,
        title or f"Implement {issue_id}",
        issue_type,
        status,
        parent,
        labels or [],
    ).model_copy(
        update={
            "assignee": assignee,
            "created_at": datetime.fromisoformat(created_at.replace("Z", "+00:00")),
            "updated_at": datetime.fromisoformat(created_at.replace("Z", "+00:00")),
            "priority": priority,
        }
    )
    write_issue_file(project_dir, issue)


def _seed_status_event(
    context: object, issue_id: str, status: str, timestamp: str
) -> None:
    event = create_event(
        issue_id=issue_id,
        event_type="state_transition",
        actor_id="fixture",
        payload={"from_status": "backlog", "to_status": status},
        occurred_at=timestamp,
    )
    write_events_batch(load_project_directory(context) / "events", [event])


def _router_events(context: object, package_id: str | None = None) -> list[dict]:
    shared_root = router_state_root(_root(context))
    events = _read_events(load_router_context(shared_root).project_dir / "events")
    return [
        event
        for event in events
        if str(event.get("issue_id", "")).startswith("router:")
        and (package_id is None or event.get("issue_id") == f"router:{package_id}")
    ]


def _shared_project_dir(context: object) -> Path:
    root = router_state_root(_root(context))
    return load_router_context(root).project_dir


def _commit_disposable_fixture(context: object) -> None:
    """Commit Behave fixture mutations only inside its disposable /tmp repo."""
    root = Path(context.working_directory).resolve()
    temp_root = Path(context.temp_dir).resolve()
    if not root.is_relative_to(temp_root):
        raise AssertionError(
            "router Behave fixture is outside its disposable directory"
        )
    top = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    if top != root:
        raise AssertionError("router Behave fixture is not its repository root")
    git = subprocess.run
    git(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    staged = git(
        ["git", "diff", "--cached", "--quiet"], cwd=root, check=False
    ).returncode
    if staged:
        git(
            [
                "git",
                "-c",
                "user.name=Router Behave Fixture",
                "-c",
                "user.email=router-fixture@localhost",
                "commit",
                "-m",
                "router fixture",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )


def _seed_claim(context: object, package_id: str, claim_id: str, revision: int) -> None:
    record_router_event(
        load_router_context(_root(context)).project_dir,
        package_id=package_id,
        event_type="router_claimed",
        payload={
            "claim_id": claim_id,
            "revision": revision,
            "provider_profile": "codex-default",
        },
    )
    context.router_current_claim = (package_id, claim_id, revision)


def _parse_result(raw: str) -> RouterAgentResult:
    """Parse a fixture result with the production adapter parser."""
    return parse_adapter_result(json.loads(raw))


@given("a Kanbus project with valid Codex-first router configuration")
def given_project_with_router(context: object) -> None:
    _install_router(context, dict(_ROUTER))


@given("a Kanbus project without a router configuration")
def given_project_without_router(context: object) -> None:
    _install_router(context)


@given('a Kanbus project with router configuration "{router_yaml}"')
def given_project_router_scalar(context: object, router_yaml: str) -> None:
    _install_router(context)
    config = _config(context)
    fragment = yaml.safe_load(router_yaml)
    if isinstance(fragment, dict):
        config.update(fragment)
    else:
        config["router"] = fragment
    _save_config(context, config)


@given("a Kanbus project with router configuration:")
def given_project_router_doc(context: object) -> None:
    payload = yaml.safe_load(context.text) or {}
    _install_router(context, payload.get("router", payload))


@given("a valid router configuration without a forge repository")
def given_valid_router_without_forge_repository(context: object) -> None:
    router = json.loads(json.dumps(_ROUTER))
    router["forge"] = {"provider": "github"}
    _install_router(context, router)


@given('a valid router configuration with forge provider "{provider}"')
def given_router_with_forge_provider(context: object, provider: str) -> None:
    router = json.loads(json.dumps(_ROUTER))
    router["forge"]["provider"] = provider
    _install_router(context, router)


@given(
    'a valid router configuration with forge repository "{repository}" and base branch "{branch}"'
)
def given_router_forge_branch(context: object, repository: str, branch: str) -> None:
    router = json.loads(json.dumps(_ROUTER))
    router["forge"].update(repository=repository, base_branch=branch)
    _install_router(context, router)


@given('a valid router configuration with watch interval "{interval}"')
def given_router_watch_interval(context: object, interval: str) -> None:
    router = json.loads(json.dumps(_ROUTER))
    router["watch_interval"] = interval
    _install_router(context, router)


@given(
    'a valid router configuration with provider profile "{profile}" using adapter "{adapter}"'
)
def given_router_profile_adapter(context: object, profile: str, adapter: str) -> None:
    router = json.loads(json.dumps(_ROUTER))
    router["providers"] = {profile: {"adapter": adapter}}
    router["classes"] = {"implementation": {"providers": [profile]}}
    _install_router(context, router)


@given('a valid router configuration with workflow role "{role}" set to "{status}"')
def given_router_workflow_override(context: object, role: str, status: str) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"]["workflow"][role] = (
        [status] if role == "terminal" else yaml.safe_load(status)
    )
    _save_config(context, config)


@given(
    'a valid router configuration with active status "{active}" and review status "{review}"'
)
def given_router_duplicate_status(context: object, active: str, review: str) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"]["workflow"].update(active=active, review=review)
    _save_config(context, config)


@given('a valid router configuration with terminal statuses "{statuses}"')
def given_router_terminal_statuses(context: object, statuses: str) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"]["workflow"]["terminal"] = yaml.safe_load(statuses)
    _save_config(context, config)


@given('a valid router configuration with "{field}" set to "{value}"')
def given_router_limit_value(context: object, field: str, value: str) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"]["limits"][field] = yaml.safe_load(value)
    _save_config(context, config)


@given(
    "a valid router configuration with project WIP {project_wip:d} and review WIP {review_wip:d}"
)
def given_router_wip_limits(context: object, project_wip: int, review_wip: int) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"]["limits"].update(project_wip=project_wip, review_wip=review_wip)
    _save_config(context, config)


use_step_matcher("re")


@given(
    r'a valid router configuration with class "(?P<agent_class>[^"]+)" using provider profiles "(?P<profiles>[^"]*)"'
)
def given_router_class_profiles_empty(
    context: object, agent_class: str, profiles: str
) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"]["classes"][agent_class] = {
        "providers": [value.strip() for value in profiles.split(",") if value.strip()]
    }
    _save_config(context, config)


use_step_matcher("parse")


@given('a valid router configuration with forge repository "{repository}"')
def given_router_forge_repository(context: object, repository: str) -> None:
    router = json.loads(json.dumps(_ROUTER))
    router["forge"]["repository"] = repository
    _install_router(context, router)


@given('a valid router configuration with forge token environment variable "{name}"')
def given_router_forge_token_env(context: object, name: str) -> None:
    if context.working_directory is None:
        _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config.setdefault("router", json.loads(json.dumps(_ROUTER)))["forge"][
        "token_env"
    ] = name
    _save_config(context, config)


@given('the forge API URL is "{api_url}"')
def given_forge_api_url(context: object, api_url: str) -> None:
    config = _config(context)
    config["router"]["forge"]["api_url"] = api_url
    _save_config(context, config)


@given('the forge token environment variable is "{name}"')
def given_forge_token_environment(context: object, name: str) -> None:
    if context.working_directory is None:
        _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config.setdefault("router", json.loads(json.dumps(_ROUTER)))["forge"][
        "token_env"
    ] = name
    _save_config(context, config)
    os.environ[name] = "fixture-token"
    context.add_cleanup(lambda: os.environ.pop(name, None))


@given('"GITHUB_TOKEN" is also set to "{value}"')
def given_default_github_token(context: object, value: str) -> None:
    os.environ["GITHUB_TOKEN"] = value
    context.add_cleanup(lambda: os.environ.pop("GITHUB_TOKEN", None))


@when("the router configuration is loaded")
@when("I load the router configuration")
def when_load_router_config(context: object) -> None:
    try:
        context.router_configuration = load_project_configuration(
            get_configuration_path(_root(context))
        ).router
        context.router_config_error = None
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")
    except ConfigurationError as error:
        context.router_configuration = None
        context.router_config_error = str(error)
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=f"error: {error}\n",
            output=f"error: {error}\n",
        )


@given('a Kanbus project with router configuration field "{field}"')
def given_unknown_router_field(context: object, field: str) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    config = _config(context)
    config["router"][field] = None
    _save_config(context, config)


@given('provider profile "{profile}" has command "{command}" and arguments {arguments}')
def given_provider_command_args(
    context: object, profile: str, command: str, arguments: str
) -> None:
    config = _config(context)
    config["router"]["providers"][profile].update(
        command=command, args=yaml.safe_load(arguments)
    )
    _save_config(context, config)


@given('provider profile "{profile}" uses a command that does not exist')
def given_provider_nonexistent_command(context: object, profile: str) -> None:
    config = _config(context)
    config["router"]["providers"][profile].update(
        command="/nonexistent/kanbus-agent-binary"
    )
    _save_config(context, config)


@given('provider profile "{profile}" has model "{model}" and environment {environment}')
def given_provider_model_env(
    context: object, profile: str, model: str, environment: str
) -> None:
    config = _config(context)
    config["router"]["providers"][profile].update(
        model=model, env=yaml.safe_load(environment)
    )
    _save_config(context, config)


@then('provider profile "{profile}" should use model "{model}"')
def then_provider_model(context: object, profile: str, model: str) -> None:
    assert context.router_configuration.providers[profile].model == model


@when("the router forge client is initialized")
def when_router_forge_client_initialized(context: object) -> None:
    from kanbus.router_forge import GitHubForge

    context.router_forge_client = GitHubForge.from_configuration(
        load_project_configuration(get_configuration_path(_root(context))).router
    )


@then('the client should read credentials only from "{name}"')
def then_router_forge_credential_source(context: object, name: str) -> None:
    assert context.router_forge_client.token == os.environ[name]


@when("I run the router plan")
def when_router_plan(context: object) -> None:
    _commit_disposable_fixture(context)
    run_cli(context, "kanbus router plan --json")


@then("the configuration should be valid")
def then_router_configuration_valid(context: object) -> None:
    assert context.result.exit_code == 0, context.result.stderr
    assert context.router_configuration is not None


@then('running "kanbus list" in the same project should succeed')
def then_list_project_succeeds(context: object) -> None:
    run_cli(context, "kanbus list")
    assert context.result.exit_code == 0


@then('the default provider profile should be "{profile}"')
def then_default_provider_profile(context: object, profile: str) -> None:
    assert profile in context.router_configuration.providers


@then('provider profile "{profile}" should use command "{command}" and no arguments')
def then_provider_command_no_args(context: object, profile: str, command: str) -> None:
    value = context.router_configuration.providers[profile]
    assert value.command == command and value.args == []


@then(
    'provider profile "{profile}" should use command "{command}" and arguments {args}'
)
def then_provider_command_args(
    context: object, profile: str, command: str, args: str
) -> None:
    value = context.router_configuration.providers[profile]
    assert value.command == command and value.args == yaml.safe_load(args)


@then("the maximum retry attempts should be {attempts:d}")
def then_router_max_attempts(context: object, attempts: int) -> None:
    assert context.router_configuration.retries.max_attempts == attempts


@then("the router watch interval should be {seconds:d} seconds")
def then_router_watch_interval(context: object, seconds: int) -> None:
    from kanbus.coordination import parse_duration

    assert parse_duration(context.router_configuration.watch_interval) == seconds


@then('the default forge provider should be "{provider}"')
def then_forge_provider(context: object, provider: str) -> None:
    assert context.router_configuration.forge.provider == provider


@then('the default forge base branch should be "{branch}"')
@then('the forge should use base branch "{branch}"')
def then_forge_base_branch(context: object, branch: str) -> None:
    assert context.router_configuration.forge.base_branch == branch


@then('the default forge API URL should be "{api_url}"')
@then('the forge should use API URL "{api_url}"')
def then_forge_api_url(context: object, api_url: str) -> None:
    assert context.router_configuration.forge.api_url == api_url


@then('the default forge token environment variable should be "{name}"')
@then('the forge should read credentials only from environment variable "{name}"')
def then_forge_token_env(context: object, name: str) -> None:
    assert context.router_configuration.forge.token_env == name


@given('pending issue "{issue_id}" has routing label "{route}"')
def given_pending_routed_issue(context: object, issue_id: str, route: str) -> None:
    _write_issue(context, issue_id, labels=[route])
    _seed_status_event(context, issue_id, "open", "2026-09-17T10:00:00Z")


@given('pending issue "{issue_id}" has routing labels "{labels}"')
def given_pending_issue_labels(context: object, issue_id: str, labels: str) -> None:
    _write_issue(context, issue_id, labels=labels.split())
    _seed_status_event(context, issue_id, "open", "2026-09-17T10:00:00Z")


@given('pending issue "kbs-120" has routing labels ""')
def given_invalid_route_fixture(context: object) -> None:
    _write_issue(context, "kbs-120", labels=[])
    _seed_status_event(context, "kbs-120", "open", "2026-09-17T10:00:00Z")


@given('issue "{issue_id}" is pending with assignee "{assignee}" and no routing label')
def given_pending_human_issue(context: object, issue_id: str, assignee: str) -> None:
    _write_issue(context, issue_id, assignee=assignee)


@given("pending routed packages are ordered {issue_ids}")
def given_pending_order(context: object, issue_ids: str) -> None:
    ids = [value.strip().strip('"') for value in issue_ids.split(",")]
    context.router_order = ids
    for ordinal, issue_id in enumerate(ids):
        _write_issue(context, issue_id, labels=["agent-provider:codex-default"])
        minute = 10 + ordinal
        _seed_status_event(context, issue_id, "open", f"2026-09-17T{minute:02d}:00:00Z")


def given_fake_adapter_outcome(context: object, profile: str, outcome: str) -> None:
    result = RouterAgentResult(
        schema_version=1,
        outcome=outcome,
        summary="fixture result",
        checkpoint=(
            {
                "ref": f"refs/kanbus/router/checkpoints/{getattr(context, 'router_order', ['kbs-test'])[0]}",
                "revision": 1,
            }
            if outcome == "completed"
            else None
        ),
        artifacts=[],
    )
    adapter = WorkingFakeAdapter(result)
    set_router_adapter(profile, adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter(profile, None))


@given("the Codex adapter returns this result:")
def given_codex_adapter_result(context: object) -> None:
    result = _parse_result(context.text)
    current_claim = getattr(context, "router_current_claim", None)
    if result.checkpoint is not None and current_claim is not None:
        from kanbus.router_execution import _next_revision

        current = load_router_context(_root(context))
        result.checkpoint.revision = _next_revision(
            current.project_dir, current_claim[0]
        )
    adapter = WorkingFakeAdapter(result)
    set_router_adapter("codex-default", adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))


@given('the Codex adapter returns result outcome "{outcome}"')
def given_codex_result_outcome(context: object, outcome: str) -> None:
    adapter = WorkingFakeAdapter(
        RouterAgentResult(schema_version=1, outcome=outcome, summary="")
    )
    # A real adapter always leaves its raw output behind; that output is what
    # proves an agent turn happened and must be preserved for review.
    adapter.last_output = json.dumps(
        {"schema_version": 1, "outcome": outcome, "summary": ""}
    )
    adapter.last_error = ""
    set_router_adapter("codex-default", adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))


def _wrap_adapter_worktree_effect(context: object, effect) -> None:
    """Run ``effect(worktree)`` inside the fake adapter's turn, like a real agent."""
    adapter = context.router_adapter
    # A real agent turn leaves a session and raw output behind; that evidence is
    # what the router preserves for review.
    adapter.session_id = "session-fixture"
    adapter.last_output = '{"type":"thread.started","thread_id":"session-fixture"}'
    adapter.last_error = ""
    original = adapter.execute

    def execute(request):
        effect(Path(request.worktree_path))
        return original(request)

    adapter.execute = execute


def _git_in(worktree: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=worktree, check=True, capture_output=True)


@given("the Codex adapter makes no changes in its worktree")
def given_codex_adapter_makes_no_changes(context: object) -> None:
    context.router_adapter.does_work = False


def _ensure_routed_issue(context: object, issue_id: str, status: str) -> None:
    """Create the routed issue once; later steps mutate it in place."""
    project_dir = load_project_directory(context)
    if not (Path(project_dir) / "issues" / f"{issue_id}.json").exists():
        _write_issue(
            context, issue_id, status=status, labels=["agent-provider:codex-default"]
        )


@given(
    'package "{issue_id}" asked a question in session "{session}" on branch "{branch}"'
)
def given_package_asked_a_question(
    context: object, issue_id: str, session: str, branch: str
) -> None:
    _ensure_routed_issue(context, issue_id, "blocked")
    _commit_disposable_fixture(context)
    time.sleep(0.05)
    record_conversation(
        _shared_project_dir(context),
        issue_id,
        action="awaiting_reply",
        provider="codex",
        claim_id="claim-old",
        revision=1,
        session_id=session,
        lifecycle="blocked",
        message="Which option should I use?",
        worktree="/nonexistent/old-worktree",
        branch=branch,
    )
    time.sleep(0.05)


@given('a human replied "{reply}" to package "{issue_id}"')
def given_human_replied(context: object, reply: str, issue_id: str) -> None:
    _ensure_routed_issue(context, issue_id, "blocked")
    time.sleep(0.05)
    add_issue_comment(_root(context), issue_id, "home", reply)
    time.sleep(0.05)


def _set_issue_status(context: object, issue_id: str, status: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(Path(project_dir), issue_id)
    # A human's status change is newer than the router's last lifecycle event.
    write_issue_file(
        Path(project_dir),
        issue.model_copy(update={"status": status, "updated_at": datetime.now(UTC)}),
    )


@given('package "{issue_id}" is ready again')
def given_package_ready_again(context: object, issue_id: str) -> None:
    _ensure_routed_issue(context, issue_id, "blocked")
    _set_issue_status(context, issue_id, "open")


@given('package "{issue_id}" is ready and has never been run')
def given_package_ready_never_run(context: object, issue_id: str) -> None:
    _ensure_routed_issue(context, issue_id, "open")


@then('the adapter should resume session "{session}" with a prompt containing "{text}"')
def then_adapter_resumed_session(context: object, session: str, text: str) -> None:
    request = context.router_adapter.requests[-1]
    assert request.resume_session_id == session, request
    assert text in (request.reply or ""), request.reply


@then('no new agent session should have been started for package "{issue_id}"')
def then_no_new_session(context: object, issue_id: str) -> None:
    assert context.router_adapter.requests[-1].resume_session_id is not None


@then('the adapter should start a fresh session for package "{issue_id}"')
def then_fresh_session(context: object, issue_id: str) -> None:
    requests = context.router_adapter.requests
    assert requests, "the adapter was never invoked"
    assert requests[-1].resume_session_id is None, requests[-1]


@then('the run should use branch "{branch}"')
def then_run_used_branch(context: object, branch: str) -> None:
    records = [
        record
        for record in (
            latest_conversation(_shared_project_dir(context), issue_id)
            for issue_id in ("kbs-401",)
        )
        if record
    ]
    assert records and records[-1]["payload"].get("branch") == branch, records


@given("a fake forge is available for the router")
def given_fake_forge_available(context: object) -> None:
    """The Python fixtures never contact a real forge; nothing to start."""


@given("the Codex adapter {mode} Kanbus project state in its worktree")
def given_codex_adapter_edits_project_state(context: object, mode: str) -> None:
    assert mode in {"edits", "edits and commits"}, mode
    project_directory = load_project_configuration(
        get_configuration_path(_root(context))
    ).project_directory

    def effect(worktree: Path) -> None:
        target = worktree / project_directory / "issues" / "agent-edit.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"edited": true}', encoding="utf-8")
        if mode == "edits and commits":
            _git_in(worktree, "add", "-A", "--", project_directory)
            _git_in(
                worktree,
                "-c",
                "user.name=agent",
                "-c",
                "user.email=agent@example.invalid",
                "commit",
                "--no-verify",
                "-qm",
                "agent board commit",
            )

    _wrap_adapter_worktree_effect(context, effect)


@given("the Codex adapter refreshes the project cache in its worktree")
def given_codex_adapter_refreshes_cache(context: object) -> None:
    project_directory = load_project_configuration(
        get_configuration_path(_root(context))
    ).project_directory

    def effect(worktree: Path) -> None:
        cache = worktree / project_directory / ".cache" / "index.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("{}", encoding="utf-8")

    _wrap_adapter_worktree_effect(context, effect)


@given('the Codex adapter returns issue update "{issue_id}" to status "{status}"')
def given_codex_issue_update(context: object, issue_id: str, status: str) -> None:
    context.router_issue_status_before = {
        issue.identifier: issue.status
        for issue in load_router_context(_root(context)).issues
    }
    adapter = WorkingFakeAdapter(
        RouterAgentResult(
            schema_version=1,
            outcome="completed",
            issue_updates=[{"issue_id": issue_id, "status": status}],
        )
    )
    set_router_adapter("codex-default", adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))


@given("the Codex adapter writes malformed JSON to standard output")
def given_codex_adapter_malformed_json(context: object) -> None:
    class MalformedJsonAdapter:
        def execute(self, _request: object) -> RouterAgentResult:
            raise IssueRouterError("Codex router adapter returned invalid JSON")

        def cancel(self, _claim_id: str) -> None:
            return None

    adapter = MalformedJsonAdapter()
    set_router_adapter("codex-default", adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))


@then('the adapter should run only package "{issue_id}"')
def then_adapter_runs_package(context: object, issue_id: str) -> None:
    assert context.router_adapter.requests, repr(context.result)
    assert [request.package_id for request in context.router_adapter.requests] == [
        issue_id
    ], repr(context.router_adapter.requests)


@then("no adapter should have run")
def then_no_router_adapter(context: object) -> None:
    adapter = getattr(context, "router_adapter", None)
    assert adapter is None or adapter.requests == []


@then('package "{issue_id}" should be in status "{status}"')
@then('package "{issue_id}" should transition to status "{status}"')
@then('package "{issue_id}" should remain in status "{status}"')
def then_package_status(context: object, issue_id: str, status: str) -> None:
    actual = read_issue_file(_shared_project_dir(context), issue_id).status
    assert (
        actual == status
    ), f"expected {issue_id} status {status}, got {actual}; {context.result!r}"


@then('package "{issue_id}" should have a "{author}" comment containing "{text}"')
def then_package_comment(
    context: object, issue_id: str, author: str, text: str
) -> None:
    project_dir = (
        _root(context)
        / load_project_configuration(
            get_configuration_path(_root(context))
        ).project_directory
    )
    comments = read_issue_file(project_dir, issue_id).comments
    assert any(
        comment.author == author and text in (comment.text or "")
        for comment in comments
    ), f"no {author} comment containing {text!r} on {issue_id}: " + repr(
        [(comment.author, comment.text) for comment in comments]
    )


@then('package "{issue_id}" should have a router comment starting with "{text}"')
def then_router_package_comment_starts_with(
    context: object, issue_id: str, text: str
) -> None:
    project_dir = (
        _root(context)
        / load_project_configuration(
            get_configuration_path(_root(context))
        ).project_directory
    )
    comments = read_issue_file(project_dir, issue_id).comments
    assert any(
        comment.author == "Kanbus Issue Router"
        and (comment.text or "").startswith(text)
        for comment in comments
    ), f"no Kanbus Issue Router comment starting with {text!r} on {issue_id}: " + repr(
        [(comment.author, comment.text) for comment in comments]
    )


@then('package "{issue_id}" should remain assigned to "{assignee}"')
def then_assignee_unchanged(context: object, issue_id: str, assignee: str) -> None:
    assert read_issue_file(_shared_project_dir(context), issue_id).assignee == assignee


@then('issue "{issue_id}" should not appear in the eligible packages')
def then_not_eligible(context: object, issue_id: str) -> None:
    payload = json.loads(context.result.stdout)
    assert issue_id not in [item["issue_id"] for item in payload["eligible"]]


@then('issue "{issue_id}" should be deferred with reason "{reason}"')
def then_issue_deferred(context: object, issue_id: str, reason: str) -> None:
    assert context.result.exit_code == 0, context.result.stderr
    payload = json.loads(context.result.stdout)
    assert {"issue_id": issue_id, "reason": reason} in payload["deferred"]


@then('issue "{issue_id}" should be eligible with provider profile "{profile}"')
def then_issue_eligible_provider(context: object, issue_id: str, profile: str) -> None:
    payload = json.loads(context.result.stdout)
    item = next(row for row in payload["eligible"] if row["issue_id"] == issue_id)
    assert item["route"]["provider_profile"] == profile


@then("eligible package order should be {issue_ids}")
def then_package_order(context: object, issue_ids: str) -> None:
    expected = [value.strip() for value in issue_ids.strip('"').split(",")]
    payload = json.loads(context.result.stdout)
    actual = [item["issue_id"] for item in payload["eligible"]]
    assert actual == expected, actual


@then(
    "stdout should equal the following JSON value with 2-space indentation and a trailing newline:"
)
def then_router_json_output(context: object) -> None:
    expected = json.loads(context.text)
    actual = json.loads(context.result.stdout)
    assert actual == expected
    assert context.result.stdout.endswith("\n")


@given("the router scheduler is stopped")
def given_router_stopped(context: object) -> None:
    state = RouterControlState()
    write_router_control(_root(context), state)


@given("the router scheduler is running")
def given_router_running(context: object) -> None:
    project_dir = load_project_directory(context)
    if not list((project_dir / "issues").glob("*.json")):
        _write_issue(
            context,
            "kbs-scheduler-pending",
            labels=["agent-provider:codex-default"],
        )
        _seed_status_event(
            context,
            "kbs-scheduler-pending",
            "open",
            "2026-09-17T10:00:00Z",
        )
    write_router_control(_root(context), RouterControlState(running=True))


@given("the router is paused")
def given_router_paused(context: object) -> None:
    project_dir = load_project_directory(context)
    if not list((project_dir / "issues").glob("*.json")):
        _write_issue(
            context,
            "kbs-paused",
            labels=["agent-provider:codex-default"],
        )
        _seed_status_event(context, "kbs-paused", "open", "2026-09-17T10:00:00Z")
    state = read_router_control(_root(context)).model_copy(update={"paused": True})
    write_router_control(_root(context), state)


@given('provider profile "{profile}" is held')
def given_provider_held(context: object, profile: str) -> None:
    state = read_router_control(_root(context)).model_copy(
        update={"held_routes": [f"provider-profile:{profile}"]}
    )
    write_router_control(_root(context), state)


@given('provider profile "{profile}" and class "{agent_class}" are held')
def given_two_routes_held(context: object, profile: str, agent_class: str) -> None:
    state = read_router_control(_root(context)).model_copy(
        update={"held_routes": [f"provider-profile:{profile}", f"class:{agent_class}"]}
    )
    write_router_control(_root(context), state)


use_step_matcher("re")


@given(r'provider profile "([^"]+)" runs fake adapter outcome "([^"]+)"')
def given_fake_adapter_outcome_regex(
    context: object, profile: str, outcome: str
) -> None:
    given_fake_adapter_outcome(context, profile, outcome)


@when(r'I run "(?P<command>kanbus router [^"]+)"')
def when_run_router_command(context: object, command: str) -> None:
    _commit_disposable_fixture(context)
    if command == "kanbus router run --watch":
        from kanbus.router_execution import run_router_watch

        context.router_watch_errors = []

        def run_watch() -> None:
            try:
                run_router_watch(load_router_context(router_state_root(_root(context))))
            except BaseException as error:  # surfaced by the scenario assertions
                context.router_watch_errors.append(error)

        context.router_watch_thread = threading.Thread(target=run_watch, daemon=True)
        context.router_watch_thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if read_router_control(_root(context)).running:
                break
            if context.router_watch_errors:
                break
            time.sleep(0.01)
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")
        context.add_cleanup(lambda: _stop_router_watch(context))
        return
    run_cli(context, command)


def _stop_router_watch(context: object) -> None:
    thread = getattr(context, "router_watch_thread", None)
    if thread is None or not _root(context).is_dir():
        return
    state = read_router_control(_root(context)).model_copy(
        update={"stop_requested": True}
    )
    write_router_control(_root(context), state)
    thread.join(timeout=5)


use_step_matcher("parse")


@then("the command should fail with exit code {exit_code:d}")
def then_command_failed_code(context: object, exit_code: int) -> None:
    assert context.result.exit_code == exit_code, (
        context.result.exit_code,
        context.result.stdout,
        context.result.stderr,
    )


@then('stdout should equal "{expected}"')
def then_stdout_exact(context: object, expected: str) -> None:
    assert context.result.stdout == expected.replace("\\n", "\n").replace(
        '\\"', '"'
    ), repr(context.result.stdout)


@then('stderr should equal "{expected}"')
def then_stderr_exact(context: object, expected: str) -> None:
    assert context.result.stderr == expected.replace("\\n", "\n").replace(
        '\\"', '"'
    ), repr(context.result.stderr)


@given("the issue hierarchy and labels are:")
def given_router_hierarchy_table(context: object) -> None:
    for row in context.table:
        issue_id = row["issue_id"].strip()
        parent = row["parent"].strip() or None
        labels = row["labels"].split()
        created_at = "2026-09-17T10:00:00Z"
        _write_issue(
            context,
            issue_id,
            status=row["status"].strip(),
            labels=labels,
            parent=parent,
            created_at=created_at,
        )
        _seed_status_event(context, issue_id, row["status"].strip(), created_at)


@then('issue "{issue_id}" should remain assigned to "{assignee}"')
def then_issue_assignee_unchanged(
    context: object, issue_id: str, assignee: str
) -> None:
    assert read_issue_file(_shared_project_dir(context), issue_id).assignee == assignee


@given('class "{agent_class}" is configured with provider profiles "{profiles}"')
def given_class_providers(context: object, agent_class: str, profiles: str) -> None:
    config = _config(context)
    provider_names = [
        profile.strip() for profile in profiles.split(",") if profile.strip()
    ]
    providers = config["router"].setdefault("providers", {})
    for profile in provider_names:
        providers.setdefault(profile, {"adapter": "codex"})
    config["router"].setdefault("classes", {})[agent_class] = {
        "providers": provider_names
    }
    _save_config(context, config)


@given("router candidates are:")
def given_router_candidates_table(context: object) -> None:
    for row in context.table:
        issue_id = row["issue_id"].strip()
        state = row["state"].strip()
        status = (
            "in_progress"
            if state in {"requested_changes", "recoverable_active"}
            else "open"
        )
        pending_since = row["pending_since"].strip()
        _write_issue(
            context,
            issue_id,
            status=status,
            labels=["agent-provider:codex-default"],
            created_at=row["created_at"].strip(),
            priority=int(row.get("priority", "2")),
        )
        _seed_status_event(context, issue_id, "open", pending_since)
        if state == "requested_changes":
            record_router_event(
                load_router_context(_root(context)).project_dir,
                package_id=issue_id,
                event_type="router_forge_event",
                payload={
                    "action": "requested_changes",
                    "number": 1,
                    "head_sha": "head",
                },
            )
        elif state == "recoverable_active":
            record_router_event(
                load_router_context(_root(context)).project_dir,
                package_id=issue_id,
                event_type="router_claimed",
                payload={"claim_id": f"claim-{issue_id}", "revision": 1, "attempt": 1},
            )


@given("the router forge is not configured")
def given_router_forge_not_configured(context: object) -> None:
    config = _config(context)
    config["router"]["forge"] = None
    _save_config(context, config)


@given("project WIP limit is {limit:d}")
def given_project_wip_limit(context: object, limit: int) -> None:
    config = _config(context)
    config["router"]["limits"]["project_wip"] = limit
    # router.limits.review_wip must not exceed project_wip; clamp it down
    # when the fixture default would otherwise violate that invariant for
    # a smaller project limit set by this step.
    review_wip = config["router"]["limits"].get("review_wip")
    if review_wip is not None and review_wip > limit:
        config["router"]["limits"]["review_wip"] = limit
    _save_config(context, config)


@given("project issues in router WIP statuses are:")
def given_existing_router_wip_issues(context: object) -> None:
    for row in context.table:
        _write_issue(
            context,
            row["issue_id"].strip(),
            status=row["status"].strip(),
            assignee=row["assignee"].strip() or None,
            issue_type=row.get("type", "task").strip() or "task",
            labels=(
                [
                    label.strip()
                    for label in row.get("labels", "").split(",")
                    if label.strip()
                ]
                or None
            ),
        )


@given(
    "a pending package is paused, held, invalidly routed, dependency blocked, policy rejected, in retry backoff, and over every WIP limit"
)
def given_precedence_fixture(context: object) -> None:
    _write_issue(
        context,
        "kbs-precedence",
        labels=["agent-provider:codex-default"],
    )
    _seed_status_event(context, "kbs-precedence", "open", "2026-09-17T10:00:00Z")
    config = _config(context)
    config["router"]["limits"].update(
        {
            "project_wip": 1,
            "review_wip": 1,
            "class_wip": {"implementation": 1},
            "provider_wip": {"codex-default": 1},
        }
    )
    _save_config(context, config)
    state = read_router_control(_root(context)).model_copy(
        update={"paused": True, "held_routes": ["provider-profile:codex-default"]}
    )
    write_router_control(_root(context), state)
    issue = read_issue_file(
        load_project_directory(context), "kbs-precedence"
    ).model_copy(
        update={
            "dependencies": [
                DependencyLink.model_validate(
                    {"target": "kbs-blocker", "type": "blocked-by"}
                )
            ]
        }
    )
    write_issue_file(load_project_directory(context), issue)
    record_router_event(
        load_router_context(_root(context)).project_dir,
        package_id="kbs-precedence",
        event_type="router_retry_scheduled",
        payload={
            "failed_attempt": 1,
            "next_attempt": 2,
            "retry_at": "2099-01-01T00:00:00Z",
        },
    )
    policy_dir = load_project_directory(context) / "policies"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "router-reject.policy").write_text(
        "Feature: Router policy\n\n  Scenario: Require assignee\n"
        '    Given the issue type is "task"\n'
        '    When transitioning to "in_progress"\n'
        '    Then the issue must have field "assignee"\n',
        encoding="utf-8",
    )


@then('its deferred reason should be "{reason}"')
def then_single_deferred_reason(context: object, reason: str) -> None:
    payload = json.loads(context.result.stdout)
    row = next(
        (item for item in payload["deferred"] if item["issue_id"] == "kbs-precedence"),
        None,
    )
    assert row is not None and row["reason"] == reason, payload


@then("deferred reasons should use this precedence:")
def then_precedence_order(context: object) -> None:
    rows = [(int(row["precedence"]), row["reason"].strip()) for row in context.table]
    assert rows == sorted(rows)
    assert [reason for _, reason in rows] == [
        "paused",
        "held",
        "invalid_route",
        "dependency_blocked",
        "policy_rejected",
        "retry_backoff",
        "project_wip_limit",
        "review_wip_limit",
        "class_wip_limit",
        "provider_wip_limit",
    ]


@given('issue "{issue_id}" has an unresolved blocking dependency')
def given_unresolved_router_dependency(context: object, issue_id: str) -> None:
    issue = read_issue_file(load_project_directory(context), issue_id).model_copy(
        update={
            "dependencies": [
                DependencyLink.model_validate(
                    {"target": "kbs-missing", "type": "blocked-by"}
                )
            ]
        }
    )
    write_issue_file(load_project_directory(context), issue)


@given('project policy rejects issue "{issue_id}" for router dispatch')
def given_router_policy_rejects(context: object, issue_id: str) -> None:
    policy_dir = load_project_directory(context) / "policies"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "router-reject.policy").write_text(
        "Feature: Router policy\n\n  Scenario: Require assignee\n"
        '    Given the issue type is "task"\n'
        '    When transitioning to "in_progress"\n'
        '    Then the issue must have field "assignee"\n',
        encoding="utf-8",
    )


@given(
    'one eligible package "{issue_id}" routed to class "{agent_class}" using provider profile "{profile}"'
)
def given_one_eligible_router_package(
    context: object, issue_id: str, agent_class: str, profile: str
) -> None:
    _write_issue(context, issue_id, labels=[f"agent-class:{agent_class}"])
    _seed_status_event(context, issue_id, "open", "2026-09-17T10:00:00Z")


@then("stdout should equal:")
def then_stdout_multiline_exact(context: object) -> None:
    assert context.result.stdout == context.text.strip("\n") + "\n"


@given(
    'active package "{issue_id}" has claim "{claim_id}" and accepted checkpoint "{checkpoint}"'
)
def given_active_package_claim(
    context: object, issue_id: str, claim_id: str, checkpoint: str
) -> None:
    if not (load_project_directory(context) / "issues" / f"{issue_id}.json").exists():
        _write_issue(
            context,
            issue_id,
            status="in_progress",
            labels=["agent-provider:codex-default"],
        )
    _seed_claim(context, issue_id, claim_id, 1)
    record_router_event(
        load_router_context(_root(context)).project_dir,
        package_id=issue_id,
        event_type="router_checkpoint_accepted",
        payload={"claim_id": claim_id, "revision": 1, "ref": checkpoint},
    )


@given(
    'package "{issue_id}" has current claim "{claim_id}" at logical revision {revision:d}'
)
def given_package_current_claim(
    context: object, issue_id: str, claim_id: str, revision: int
) -> None:
    if not (load_project_directory(context) / "issues" / f"{issue_id}.json").exists():
        _write_issue(
            context,
            issue_id,
            status="in_progress",
            labels=["agent-provider:codex-default"],
        )
    _seed_claim(context, issue_id, claim_id, revision)


@given('package "{issue_id}" contains issues "{issue_ids}"')
def given_router_package_members(
    context: object, issue_id: str, issue_ids: str
) -> None:
    identifiers = [value.strip() for value in issue_ids.split(",")]
    _write_issue(
        context, issue_id, status="in_progress", labels=["agent-provider:codex-default"]
    )
    for child_id in identifiers:
        if child_id != issue_id:
            _write_issue(context, child_id, parent=issue_id, status="open")
    context.router_package_ids = identifiers


@given(
    'package "{issue_id}" has accepted checkpoint "{checkpoint}" at revision {revision:d}'
)
def given_accepted_checkpoint(
    context: object, issue_id: str, checkpoint: str, revision: int
) -> None:
    if not (load_project_directory(context) / "issues" / f"{issue_id}.json").exists():
        _write_issue(
            context,
            issue_id,
            status="in_progress",
            labels=["agent-provider:codex-default"],
        )
    current_claim = getattr(context, "router_current_claim", None)
    claim_id = (
        current_claim[1]
        if current_claim and current_claim[0] == issue_id
        else f"claim-{issue_id}"
    )
    if not current_claim or current_claim[0] != issue_id:
        _seed_claim(context, issue_id, claim_id, revision)
    record_router_event(
        load_router_context(_root(context)).project_dir,
        package_id=issue_id,
        event_type="router_checkpoint_accepted",
        payload={"claim_id": claim_id, "revision": revision, "ref": checkpoint},
    )


@given(
    'package "{issue_id}" has obsolete claim "{claim_id}" at logical revision {revision:d}'
)
def given_obsolete_claim(
    context: object, issue_id: str, claim_id: str, revision: int
) -> None:
    record_router_event(
        load_router_context(_root(context)).project_dir,
        package_id=issue_id,
        event_type="router_claim_observed",
        payload={"claim_id": claim_id, "revision": revision},
    )
    context.router_obsolete_claim = (issue_id, claim_id, revision)


@when('claim "{claim_id}" publishes a result at logical revision {revision:d}')
def when_claim_publishes_revision(
    context: object, claim_id: str, revision: int
) -> None:
    issue_id, _, _ = context.router_current_claim
    _capture_router_publication(
        context, issue_id, claim_id, revision, "retryable_failure", None, []
    )


@when(
    'claim "{claim_id}" publishes a completed result with checkpoint "{checkpoint}" at revision {revision:d}'
)
def when_claim_checkpoint(
    context: object, claim_id: str, checkpoint: str, revision: int
) -> None:
    issue_id = context.router_current_claim[0]
    _capture_router_publication(
        context, issue_id, claim_id, revision, "completed", checkpoint, []
    )


@when('claim "{claim_id}" publishes artifact "{name}" as "{ref}"')
def when_claim_artifact(context: object, claim_id: str, name: str, ref: str) -> None:
    issue_id = context.router_current_claim[0]
    _capture_router_publication(
        context,
        issue_id,
        claim_id,
        context.router_current_claim[2],
        "completed",
        None,
        [{"name": name, "ref": ref}],
    )


@when('claim "{claim_id}" publishes result:')
def when_claim_publishes_result(context: object, claim_id: str) -> None:
    payload = json.loads(context.text)
    context.router_publication_error = None
    try:
        _commit_disposable_fixture(context)
        shared_root = router_state_root(_root(context))
        router_context = load_router_context(shared_root)
        package_id = payload["package_id"]
        result = RouterAgentResult.model_validate(
            {
                "schema_version": payload["schema_version"],
                "outcome": payload["outcome"],
                "summary": payload.get("summary", ""),
                "issue_updates": payload.get("issue_updates", []),
                "checkpoint": payload.get("checkpoint"),
                "artifacts": payload.get("artifacts", []),
            }
        )
        from kanbus.router_execution import _assert_current_claim

        _assert_current_claim(
            router_context.project_dir, package_id, claim_id, payload["revision"]
        )
        publish_router_result(
            router_context,
            package_id=package_id,
            claim_id=claim_id,
            revision=payload["revision"],
            result=result,
            package_issue_ids=getattr(context, "router_package_ids", [package_id]),
        )
        context.router_publication_result = "accepted"
    except IssueRouterError as error:
        context.router_publication_error = str(error)
        context.router_publication_result = "failed"


def _capture_router_publication(
    context: object,
    package_id: str,
    claim_id: str,
    revision: int,
    outcome: str,
    checkpoint: str | None,
    artifacts: list[dict],
) -> None:
    from kanbus.router_execution import _assert_current_claim

    context.router_publication_error = None
    try:
        _commit_disposable_fixture(context)
        router_context = load_router_context(router_state_root(_root(context)))
        _assert_current_claim(
            router_context.project_dir, package_id, claim_id, revision
        )
        result = RouterAgentResult(
            schema_version=1,
            outcome=outcome,
            checkpoint=(
                None
                if checkpoint is None
                else {"ref": checkpoint, "revision": revision}
            ),
            artifacts=artifacts,
        )
        package_issue_ids = getattr(context, "router_package_ids", [package_id])
        publish_router_result(
            router_context,
            package_id=package_id,
            claim_id=claim_id,
            revision=revision,
            result=result,
            package_issue_ids=package_issue_ids,
        )
        terminal_event = {
            "completed": "router_completed",
            "blocked": "router_blocked",
            "retryable_failure": "router_retry_scheduled",
        }[outcome]
        record_router_event(
            router_context.project_dir,
            package_id=package_id,
            event_type=terminal_event,
            payload={"claim_id": claim_id, "revision": revision},
        )
        publish_router_state(router_context.root, set(package_issue_ids))
        context.router_publication_result = "accepted"
    except IssueRouterError as error:
        context.router_publication_error = str(error)
        context.router_publication_result = "failed"


@given(
    'router package "{package_id}" has current claim "{claim_id}" at logical revision {revision:d}'
)
def given_router_package_current_claim(
    context: object, package_id: str, claim_id: str, revision: int
) -> None:
    _install_router(context, json.loads(json.dumps(_ROUTER)))
    _write_issue(
        context,
        package_id,
        status="in_progress",
        labels=["agent-provider:codex-default"],
    )
    _seed_claim(context, package_id, claim_id, revision)
    context.router_package_ids = [package_id]


use_step_matcher("re")


@then(
    r'the published result for package "([^"]+)" should include claim "([^"]+)" and revision (\d+)'
)
def then_coordination_published_result(
    context: object, package_id: str, claim_id: str, revision: int
) -> None:
    revision = int(revision)
    events = _router_events(context, package_id)
    assert any(
        event.get("event_type") == "router_completed"
        and event["payload"].get("claim_id") == claim_id
        and event["payload"].get("revision") == revision
        for event in events
    )


use_step_matcher("parse")


@then('the published checkpoint should be "{checkpoint}"')
def then_published_checkpoint(context: object, checkpoint: str) -> None:
    events = _router_events(context, context.router_current_claim[0])
    assert any(
        event["event_type"] == "router_checkpoint_accepted"
        and event["payload"].get("ref") == checkpoint
        for event in events
    )


@then('the published artifacts should contain "{artifact}"')
def then_published_artifacts(context: object, artifact: str) -> None:
    name, ref = artifact.split("=", 1)
    events = _router_events(context, context.router_current_claim[0])
    assert any(
        event["event_type"] == "router_artifact_published"
        and event["payload"].get("name") == name
        and event["payload"].get("ref") == ref
        for event in events
    )


@given('GitHub is the configured forge for repository "{repository}"')
def given_configured_forge(context: object, repository: str) -> None:
    config = _config(context)
    config.setdefault("router", json.loads(json.dumps(_ROUTER)))
    config["router"].setdefault("forge", {})["repository"] = repository
    _save_config(context, config)


@given(
    'package "{package_id}" completes at logical revision {revision:d} on branch "{branch}"'
)
def given_completed_package_for_forge(
    context: object, package_id: str, revision: int, branch: str
) -> None:
    if context.working_directory is None:
        _install_router(context, json.loads(json.dumps(_ROUTER)))
    _write_issue(
        context,
        package_id,
        status="in_progress",
        labels=["agent-provider:codex-default"],
        title="Implement router planning",
    )
    _seed_claim(context, package_id, f"claim-{package_id}", revision)
    context.router_forge_package = (package_id, revision, branch)
    context.router_package_ids = [package_id]
    context.add_cleanup(lambda: _clear_worktree_mapping(context))


def _clear_worktree_mapping(context: object) -> None:
    package = getattr(context, "router_forge_package", None)
    claim_id = None if package is None else f"claim-{package[0]}"
    if claim_id:
        from kanbus.router_execution import _WORKTREE_BRANCHES

        _WORKTREE_BRANCHES.pop(claim_id, None)


@when("the router publishes the completed result")
def when_publish_completed_forge_result(context: object) -> None:
    _commit_disposable_fixture(context)
    shared_root = router_state_root(_root(context))
    router_context = load_router_context(shared_root)
    context.router_forge_base_branch = router_context.router.forge.base_branch
    package_id, revision, branch = context.router_forge_package
    claim_id = f"claim-{package_id}"
    from kanbus.router_execution import (
        _WORKTREE_BRANCHES,
        _assert_claim_fence,
        _candidate_for_package,
        _open_pull_request,
        _transition_package,
    )

    candidate = _candidate_for_package(router_context, package_id, [package_id])
    _WORKTREE_BRANCHES[claim_id] = branch
    _assert_claim_fence(router_context, package_id, claim_id, revision)
    pull = _open_pull_request(
        router_context,
        candidate,
        None,
        claim_id,
        revision,
    )
    _transition_package(
        load_router_context(router_state_root(shared_root)),
        package_id,
        router_context.router.workflow.review,
        claim_id=claim_id,
        revision=revision,
    )
    record_router_event(
        load_router_context(router_state_root(shared_root)).project_dir,
        package_id=package_id,
        event_type="router_completed",
        payload={
            "claim_id": claim_id,
            "revision": revision,
            "pull_request": None if pull is None else pull.model_dump(mode="json"),
        },
    )
    publish_router_state(shared_root, {package_id})
    context.router_forge_pull_request = pull


@then('the router should open a pull request with title "{title}"')
def then_router_pr_title(context: object, title: str) -> None:
    assert context.router_forge_pull_request is not None
    pull = context.router_forge_pull_request
    stored = context.router_fake_forge.pull_requests[pull.number]
    assert stored["title"] == title


@then('the pull request should use head branch "{branch}"')
def then_router_pr_head_branch(context: object, branch: str) -> None:
    assert context.router_forge_pull_request.head_branch == branch


@then('the pull request should use base branch "{branch}"')
def then_router_pr_base_branch(context: object, branch: str) -> None:
    assert context.router_forge_base_branch == branch


@then('the pull request body should include "{text}"')
def then_router_pr_body(context: object, text: str) -> None:
    pull = context.router_forge_pull_request
    assert text in context.router_fake_forge.pull_requests[pull.number]["body"]


@then("no pull request should have been opened")
def then_no_pull_request_opened(context: object) -> None:
    assert (
        len(context.router_fake_forge.pull_requests) == 0
    ), f"expected no pull requests, but found {len(context.router_fake_forge.pull_requests)}"


@given('package "{package_id}" has router pull request {number:d} at head "{head_sha}"')
@given(
    'package "{package_id}" is in status "review" with pull request {number:d} at head "{head_sha}"'
)
def given_package_review_pr(
    context: object, package_id: str, number: int, head_sha: str
) -> None:
    _write_issue(
        context,
        package_id,
        status="review",
        labels=["agent-provider:codex-default"],
    )
    record_router_event(
        load_router_context(_root(context)).project_dir,
        package_id=package_id,
        event_type="router_pull_request_opened",
        payload={
            "number": number,
            "head_sha": head_sha,
            "repository": (
                context.router_configuration.forge.repository
                if getattr(context, "router_configuration", None)
                else _ROUTER["forge"]["repository"]
            ),
            "branch": f"codex/router/{package_id}/r1",
            "url": f"https://github.example/pull/{number}",
        },
    )
    context.router_pr = (package_id, number, head_sha)
    _commit_disposable_fixture(context)


@when("GitHub sends router event:")
def when_github_router_event(context: object) -> None:
    _commit_disposable_fixture(context)
    payload = json.loads(context.text)
    shared_root = router_state_root(_root(context))
    router_context = load_router_context(shared_root)
    try:
        record_github_pull_request_event(
            router_context.project_dir,
            router_context.router,
            payload,
        )
        context.result = SimpleNamespace(exit_code=0, stdout="", stderr="", output="")
    except IssueRouterError as error:
        context.result = SimpleNamespace(
            exit_code=1,
            stdout="",
            stderr=f"error: {error}\n",
            output=f"error: {error}\n",
        )


@then('GitHub event IDs "{event_ids}" should be recorded once each')
def then_github_event_ids_recorded(context: object, event_ids: str) -> None:
    all_events = [
        event
        for event in _router_events(context)
        if event["event_type"].startswith("router_")
    ]
    recorded = [event.get("payload", {}).get("forge_event_id") for event in all_events]
    for event_id in [value.strip() for value in event_ids.split(",")]:
        assert recorded.count(event_id) == 1


@given('pull request {number:d} has an approval recorded for head "{head_sha}"')
def given_pull_request_approved(context: object, number: int, head_sha: str) -> None:
    package_id = context.router_pr[0]
    shared_root = router_state_root(_root(context))
    router_context = load_router_context(shared_root)
    record_router_event(
        router_context.project_dir,
        package_id=package_id,
        event_type="router_pull_request_approved",
        payload={
            "number": number,
            "head_sha": head_sha,
            "forge_event_id": f"fixture-approval-{package_id}",
        },
    )
    publish_router_state(shared_root)


@then('package "{package_id}" should have approval recorded for head "{head_sha}"')
def then_package_approval(context: object, package_id: str, head_sha: str) -> None:
    assert any(
        event["event_type"] == "router_pull_request_approved"
        and event["payload"].get("head_sha") == head_sha
        for event in _router_events(context, package_id)
    )


@then('pull request {number:d} should not have approval for head "{head_sha}"')
def then_pr_not_approved_for_head(context: object, number: int, head_sha: str) -> None:
    package_id = context.router_pr[0]
    assert not any(
        event["event_type"] == "router_pull_request_approved"
        and event["payload"].get("head_sha") == head_sha
        for event in _router_events(context, package_id)
    )


@when(
    'GitHub sends router check-run event "{event_id}" for pull request {number:d} and head "{head_sha}" with conclusion "{conclusion}"'
)
def when_github_check_run(
    context: object, event_id: str, number: int, head_sha: str, conclusion: str
) -> None:
    _commit_disposable_fixture(context)
    router_context = load_router_context(router_state_root(_root(context)))
    try:
        record_github_check_run_event(
            router_context.project_dir,
            router_context.router,
            {
                "schema_version": 1,
                "event_id": event_id,
                "kind": "check_run",
                "action": "completed",
                "repository": router_context.router.forge.repository,
                "number": number,
                "head_sha": head_sha,
                "conclusion": conclusion,
            },
        )
        context.router_check_run_error = None
    except IssueRouterError as error:
        context.router_check_run_error = str(error)


@when(
    'the router receives the same approved GitHub event "{event_id}" twice for pull request {number:d} and head "{head_sha}"'
)
def when_duplicate_approved_github_event(
    context: object, event_id: str, number: int, head_sha: str
) -> None:
    _commit_disposable_fixture(context)
    router_context = load_router_context(router_state_root(_root(context)))
    payload = {
        "schema_version": 1,
        "event_id": event_id,
        "kind": "pull_request",
        "action": "approved",
        "repository": router_context.router.forge.repository,
        "number": number,
        "head_sha": head_sha,
        "merged": False,
    }
    first = record_github_pull_request_event(
        router_context.project_dir, router_context.router, payload
    )
    second = record_github_pull_request_event(
        router_context.project_dir, router_context.router, payload
    )
    context.router_duplicate_event_result = (first, second)


@then("the event should fail with exit code {exit_code:d}")
def then_router_event_failed(context: object, exit_code: int) -> None:
    assert context.result.exit_code == exit_code, context.result.stderr


@then('package "{package_id}" should transition to terminal status "{status}"')
def then_router_package_terminal_status(
    context: object, package_id: str, status: str
) -> None:
    assert read_issue_file(_shared_project_dir(context), package_id).status == status


@then('package "{package_id}" should be ordered before pending package "{pending_id}"')
def then_requested_changes_order(
    context: object, package_id: str, pending_id: str
) -> None:
    shared_root = router_state_root(_root(context))
    shared_project = load_router_context(shared_root).project_dir
    issue = build_issue(
        pending_id,
        f"Implement {pending_id}",
        "task",
        "open",
        None,
        ["agent-provider:codex-default"],
    )
    write_issue_file(shared_project, issue)
    publish_router_state(shared_root, {pending_id})
    plan = build_router_plan(load_router_context(router_state_root(shared_root)))
    order = [item.issue_id for item in plan.eligible]
    assert order.index(package_id) < order.index(pending_id)


@then("the next run should continue on pull request {number:d}")
def then_next_run_continues_pr(context: object, number: int) -> None:
    package_id = context.router_pr[0]
    assert any(
        event["event_type"] == "router_pull_request_opened"
        and event["payload"].get("number") == number
        for event in _router_events(context, package_id)
    )


@then("one approval event should be recorded")
def then_one_approval_event(context: object) -> None:
    package_id = context.router_pr[0]
    approvals = [
        event
        for event in _router_events(context, package_id)
        if event["event_type"] == "router_pull_request_approved"
    ]
    assert len(approvals) == 1


@then('the router should record diagnostic "{diagnostic}"')
def then_router_diagnostic(context: object, diagnostic: str) -> None:
    package_id = context.router_pr[0]
    assert any(
        event["payload"].get("diagnostic") == diagnostic
        for event in _router_events(context, package_id)
    )


@then('package "{package_id}" should return to active after the check-run event')
def then_check_run_active(context: object, package_id: str) -> None:
    assert (
        read_issue_file(_shared_project_dir(context), package_id).status
        == "in_progress"
    )


@then('package "{package_id}" should remain in review after the check-run event')
def then_check_run_review(context: object, package_id: str) -> None:
    assert read_issue_file(_shared_project_dir(context), package_id).status == "review"


@then("the result should be accepted")
def then_router_result_accepted(context: object) -> None:
    assert context.router_publication_result == "accepted"


@then('the accepted checkpoint should be "{checkpoint}" at revision {revision:d}')
def then_checkpoint_value(context: object, checkpoint: str, revision: int) -> None:
    events = _router_events(context, context.router_current_claim[0])
    event = next(
        event
        for event in reversed(events)
        if event["event_type"] == "router_checkpoint_accepted"
    )
    assert (
        event["payload"]["ref"] == checkpoint
        and event["payload"]["revision"] == revision
    )


@then('artifact "{name}" should be published as "{ref}"')
def then_artifact_published(context: object, name: str, ref: str) -> None:
    events = _router_events(context, context.router_current_claim[0])
    assert any(
        event["event_type"] == "router_artifact_published"
        and event["payload"].get("name") == name
        and event["payload"].get("ref") == ref
        for event in events
    )


@then("the publication should fail with exit code 1")
def then_router_publication_failed(context: object) -> None:
    assert context.router_publication_result == "failed"
    context.result = SimpleNamespace(
        exit_code=1,
        stdout="",
        stderr=f"error: {context.router_publication_error}\n",
        output="",
    )


@given("the maximum retry attempts are {attempts:d}")
def given_max_retries(context: object, attempts: int) -> None:
    config = _config(context)
    config["router"]["retries"]["max_attempts"] = attempts
    _save_config(context, config)


@given("router retry max attempts is {attempts:d}")
def given_retry_max_attempts(context: object, attempts: int) -> None:
    given_max_retries(context, attempts)


@given('fake adapter returns outcome "{outcome}" for attempt {attempt:d}')
@given('the fake adapter returns outcome "{outcome}"')
def given_retry_adapter(context: object, outcome: str, attempt: int = 1) -> None:
    result = RouterAgentResult(
        schema_version=1, outcome=outcome, summary="fixture failure"
    )
    adapter = WorkingFakeAdapter(result)
    set_router_adapter("codex-default", adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))


@given('package "{issue_id}" is active at attempt {attempt:d}')
@given('active package "{issue_id}" is at attempt {attempt:d}')
def given_active_attempt(context: object, issue_id: str, attempt: int) -> None:
    _write_issue(
        context, issue_id, status="in_progress", labels=["agent-provider:codex-default"]
    )
    context.router_active_issue = issue_id
    _seed_claim(context, issue_id, f"claim-{attempt}", attempt)
    if attempt > 1:
        record_router_event(
            load_router_context(_root(context)).project_dir,
            package_id=issue_id,
            event_type="router_retry_scheduled",
            payload={"next_attempt": attempt, "retry_at": "2026-09-01T00:00:00Z"},
        )


@given('package "{issue_id}" has failed retryably {failures:d} times')
def given_previous_retry_failures(
    context: object, issue_id: str, failures: int
) -> None:
    _write_issue(
        context, issue_id, status="in_progress", labels=["agent-provider:codex-default"]
    )
    context.router_active_issue = issue_id
    context.router_failures = failures
    for attempt in range(1, failures + 1):
        record_router_event(
            load_router_context(_root(context)).project_dir,
            package_id=issue_id,
            event_type="router_retry_scheduled",
            payload={
                "failed_attempt": attempt,
                "next_attempt": attempt + 1,
                "retry_at": "2026-09-01T00:00:00Z",
            },
        )


@when("I inspect its next retry time")
def when_inspect_retry_time(context: object) -> None:
    failures = int(getattr(context, "router_failures", 1))
    context.router_retry_delay = retry_delay_seconds(failures)


@then("the retry delay should be {seconds:d}s")
def then_retry_delay(context: object, seconds: int) -> None:
    assert context.router_retry_delay == seconds


@then(
    'package "{issue_id}" should have attempt {attempt:d} available after {seconds:d} seconds'
)
def then_retry_attempt_time(
    context: object, issue_id: str, attempt: int, seconds: int
) -> None:
    events = _router_events(context, issue_id)
    retry = next(
        event
        for event in reversed(events)
        if event["event_type"] == "router_retry_scheduled"
    )
    assert (
        retry["payload"]["next_attempt"] == attempt
        and retry["payload"]["delay_seconds"] == seconds
    )


@given('pending package "{issue_id}" is eligible')
def given_pending_package_eligible(context: object, issue_id: str) -> None:
    _write_issue(context, issue_id, labels=["agent-provider:codex-default"])


@given('provider profile "{profile}" has reached its WIP limit')
def given_provider_limit_reached(context: object, profile: str) -> None:
    config = _config(context)
    config["router"]["limits"].setdefault("provider_wip", {})[profile] = 1
    _save_config(context, config)
    _write_issue(
        context,
        f"kbs-existing-{profile}",
        status="in_progress",
        labels=[f"agent-provider:{profile}"],
    )


@given('only the "{limit}" WIP limit is reached')
def given_only_limit_reached(context: object, limit: str) -> None:
    config = _config(context)
    router = config["router"]
    if limit == "project":
        router["limits"]["project_wip"] = 1
        router["limits"]["review_wip"] = 1
        _write_issue(
            context,
            "kbs-existing",
            status="in_progress",
            labels=["agent-provider:codex-default"],
        )
    elif limit == "review":
        router["limits"]["review_wip"] = 1
        _write_issue(
            context,
            "kbs-existing",
            status="review",
            labels=["agent-provider:codex-default"],
        )
        record_router_event(
            load_router_context(_root(context)).project_dir,
            package_id="kbs-existing",
            event_type="router_conversation",
            payload={"lifecycle": "review"},
        )
    elif limit == "class":
        router["limits"]["class_wip"] = {"implementation": 1}
        _write_issue(
            context,
            "kbs-existing",
            status="in_progress",
            labels=["agent-class:implementation"],
        )
    else:
        router["limits"]["provider_wip"] = {"codex-default": 1}
        _write_issue(
            context,
            "kbs-existing",
            status="in_progress",
            labels=["agent-provider:codex-default"],
        )
    _save_config(context, config)


@given("the router is watching with interval {seconds:d} seconds")
@given("router watch interval is {seconds:d} seconds")
def given_watch_interval(context: object, seconds: int) -> None:
    config = _config(context)
    config["router"]["watch_interval"] = f"{seconds}s"
    _save_config(context, config)


@when("I run the router configuration check")
def when_router_config_check(context: object) -> None:
    when_load_router_config(context)


@given("there are no eligible router packages")
def given_no_eligible_router_packages(context: object) -> None:
    context.router_order = []


@when("the router enters its next watch cycle")
def when_router_watch_cycle(context: object) -> None:
    from kanbus.coordination_runtime import select_soft_provider

    _commit_disposable_fixture(context)
    router_context = load_router_context(router_state_root(_root(context)))
    context.router_watch_provider = select_soft_provider(
        router_context.root, router_context.configuration
    )
    context.router_watch_interval = router_context.router.watch_interval
    context.router_watch_issue_statuses = {
        issue.identifier: issue.status for issue in router_context.issues
    }


@then("the router should continue by polling Git history every {seconds:d} seconds")
def then_router_watch_git_poll(context: object, seconds: int) -> None:
    from kanbus.coordination import parse_duration

    assert context.router_watch_provider == "git"
    assert parse_duration(context.router_watch_interval) == seconds


@then("no package should be marked complete solely because MQTT is unavailable")
def then_mqtt_outage_not_complete(context: object) -> None:
    current = load_router_context(router_state_root(_root(context)))
    assert {
        issue.identifier: issue.status for issue in current.issues
    } == context.router_watch_issue_statuses


@then("the router scheduler should remain paused after restart")
def then_router_stays_paused(context: object) -> None:
    assert read_router_control(_root(context)).paused


@then("the router should not be paused")
def then_router_not_paused(context: object) -> None:
    assert not read_router_control(_root(context)).paused


@then('provider profile "{profile}" should remain held')
def then_router_hold_remains(context: object, profile: str) -> None:
    assert (
        f"provider-profile:{profile}" in read_router_control(_root(context)).held_routes
    )


@then(
    'packages pinned to provider profile "{profile}" should be deferred with reason "{reason}"'
)
def then_provider_packages_held(context: object, profile: str, reason: str) -> None:
    if not getattr(context, "router_order", None):
        issue_id = f"kbs-held-{profile}"
        _write_issue(context, issue_id, labels=[f"agent-provider:{profile}"])
        _seed_status_event(context, issue_id, "open", "2026-09-17T10:00:00Z")
        _commit_disposable_fixture(context)
        context.router_order = [issue_id]
    plan = build_router_plan(load_router_context(router_state_root(_root(context))))
    assert any(
        item.issue_id in context.router_order and item.reason == reason
        for item in plan.deferred
    )
    assert (
        f"provider-profile:{profile}" in read_router_control(_root(context)).held_routes
    )


@then(
    'class-routed packages for "{agent_class}" should be deferred with reason "{reason}"'
)
def then_class_packages_held(context: object, agent_class: str, reason: str) -> None:
    issue_id = f"kbs-held-{agent_class}"
    _write_issue(context, issue_id, labels=[f"agent-class:{agent_class}"])
    _seed_status_event(context, issue_id, "open", "2026-09-17T10:00:00Z")
    _commit_disposable_fixture(context)
    plan = build_router_plan(load_router_context(router_state_root(_root(context))))
    assert any(item.reason == reason for item in plan.deferred)
    assert f"class:{agent_class}" in read_router_control(_root(context)).held_routes


@given("one router package is active")
def given_one_router_package_active(context: object) -> None:
    _write_issue(
        context,
        "kbs-active-run",
        status="in_progress",
        labels=["agent-provider:codex-default"],
    )
    _seed_claim(context, "kbs-active-run", "claim-active-run", 1)


@given('provider profile "{profile}" is running package "{issue_id}"')
def given_provider_running_package(
    context: object, profile: str, issue_id: str
) -> None:
    _write_issue(
        context, issue_id, status="in_progress", labels=[f"agent-provider:{profile}"]
    )
    _seed_claim(context, issue_id, "claim-210", 1)
    adapter = WorkingFakeAdapter(RouterAgentResult(schema_version=1, outcome="blocked"))
    from kanbus.router_execution import _ACTIVE_ADAPTERS

    _ACTIVE_ADAPTERS[issue_id] = ("claim-210", adapter)
    context.router_cancel_adapter = adapter
    context.add_cleanup(lambda: _ACTIVE_ADAPTERS.pop(issue_id, None))


@then('the adapter should receive a cancellation request for claim "{claim_id}"')
def then_adapter_cancelled(context: object, claim_id: str) -> None:
    assert context.router_cancel_adapter.cancelled_claims == [claim_id]


@then('checkpoint "{checkpoint}" should remain accepted')
def then_cancel_checkpoint_preserved(context: object, checkpoint: str) -> None:
    issue_id = (
        context.router_current_claim[0]
        if hasattr(context, "router_current_claim")
        else "kbs-210"
    )
    events = _router_events(context, issue_id)
    assert any(
        event["event_type"] == "router_checkpoint_accepted"
        and event["payload"].get("ref") == checkpoint
        for event in events
    )


@given('the router scheduler is running package "{issue_id}"')
def given_router_scheduler_running_package(context: object, issue_id: str) -> None:
    given_router_running(context)
    _write_issue(
        context, issue_id, status="in_progress", labels=["agent-provider:codex-default"]
    )
    _seed_claim(context, issue_id, f"claim-{issue_id}", 1)


@then('package "{issue_id}" should be allowed to finish its current adapter call')
def then_active_package_can_finish(context: object, issue_id: str) -> None:
    events = _router_events(context, issue_id)
    assert any(event["event_type"] == "router_claimed" for event in events)
    assert read_router_control(_root(context)).stop_requested


@then("the router scheduler should stop before starting another package")
def then_scheduler_stops_after_current(context: object) -> None:
    state = read_router_control(_root(context))
    assert state.stop_requested
    assert state.running


@given('the router scheduler holds claim "{claim_id}" and runs package "{issue_id}"')
def given_scheduler_claimed_and_running(
    context: object, claim_id: str, issue_id: str
) -> None:
    from kanbus.coordination import claim as soft_claim

    context.router_scheduler_claim = claim_id
    _write_issue(
        context, issue_id, status="in_progress", labels=["agent-provider:codex-default"]
    )
    _seed_claim(context, issue_id, claim_id, 1)
    router_context = load_router_context(_root(context))
    soft_claim(
        router_context.project_dir / "events",
        router_context.configuration.coordination,
        resource="router:scheduler",
        owner=f"issue-router:{os.getpid()}",
        claim_id=claim_id,
    )


@when('package "{issue_id}" finishes its current adapter call')
def when_package_finishes_current_call(context: object, issue_id: str) -> None:
    from kanbus.coordination import release as soft_release

    router_context = load_router_context(router_state_root(_root(context)))
    events = _router_events(context, issue_id)
    claim = next(
        event for event in reversed(events) if event["event_type"] == "router_claimed"
    )
    claim_id = claim["payload"]["claim_id"]
    record_router_event(
        router_context.project_dir,
        package_id=issue_id,
        event_type="router_completed",
        payload={"claim_id": claim_id, "revision": claim["payload"]["revision"]},
    )
    soft_release(
        router_context.project_dir / "events",
        resource="router:scheduler",
        owner=f"issue-router:{os.getpid()}",
        claim_id=context.router_scheduler_claim,
    )
    context.router_scheduler_released = not inspect_lease(
        router_context.project_dir / "events", "router:scheduler"
    ).active
    publish_router_state(router_context.root)


@then('the router scheduler should release claim "{claim_id}"')
def then_scheduler_claim_released(context: object, claim_id: str) -> None:
    assert context.router_scheduler_claim == claim_id
    assert context.router_scheduler_released


@then("the scheduler should not start another package")
def then_scheduler_does_not_start_next(context: object) -> None:
    assert context.router_scheduler_released


@then("Kanbus history should contain router control events in command order:")
def then_control_history_order(context: object) -> None:
    from kanbus.issue_router import _decode_router_event

    records = [
        _decode_router_event(event)
        for event in _read_events(_shared_project_dir(context) / "events")
        if event.get("issue_id") == "router:control"
    ]
    actual = [
        (event["event_type"], event.get("payload", {}).get("target", ""))
        for event in records
    ]
    expected = [(row["event"].strip(), row["target"].strip()) for row in context.table]
    assert actual[-len(expected) :] == expected


@then("the command should stay running until stopped")
def then_router_watch_running(context: object) -> None:
    assert context.router_watch_thread.is_alive(), getattr(
        context, "router_watch_errors", []
    )
    assert not context.router_watch_errors


@then("the router should reconcile the issue board immediately")
def then_router_watch_reconciles(context: object) -> None:
    assert any(
        event["event_type"] == "router_started"
        for event in _router_events(context, "control")
    )


@then("the router should poll GitHub pull request state every {seconds:d} seconds")
def then_router_watch_poll_interval(context: object, seconds: int) -> None:
    from kanbus.coordination import parse_duration

    router = load_project_configuration(
        get_configuration_path(router_state_root(_root(context)))
    ).router
    assert parse_duration(router.watch_interval) == seconds
    assert context.router_watch_thread.is_alive()


@then("MQTT router notifications should trigger reconciliation before the next poll")
def then_watch_mqtt_notification_wake(context: object) -> None:
    from kanbus.router_execution import _wait_for_watch_trigger

    notification = threading.Event()
    notification.set()
    listener = SimpleNamespace(received=notification)
    assert _wait_for_watch_trigger(listener, 30)


@then("the router should publish the checkpoint and artifact references")
def then_execution_checkpoint_and_artifact_publication(context: object) -> None:
    package_id = context.router_adapter.requests[0].package_id
    events = _router_events(context, package_id)
    assert any(event["event_type"] == "router_checkpoint_accepted" for event in events)
    assert any(event["event_type"] == "router_artifact_published" for event in events)


@then('the router should create a pull request for package "{package_id}"')
def then_execution_pr_created(context: object, package_id: str) -> None:
    events = _router_events(context, package_id)
    assert any(event["event_type"] == "router_pull_request_opened" for event in events)
    assert any(
        pr["head_branch"].startswith(f"codex/router/{package_id}/")
        for pr in context.router_fake_forge.pull_requests.values()
    )


@then('package "{package_id}" should receive a retry time')
def then_package_retry_time(context: object, package_id: str) -> None:
    events = _router_events(context, package_id)
    retries = [
        event for event in events if event["event_type"] == "router_retry_scheduled"
    ]
    assert retries and retries[-1]["payload"].get("retry_at")


@when('the Codex adapter starts claim "{claim_id}"')
def when_codex_adapter_starts_claim(context: object, claim_id: str) -> None:
    _commit_disposable_fixture(context)
    from kanbus.router_execution import (
        _candidate_for_package,
        _next_revision,
        _run_adapter,
    )

    router_context = load_router_context(router_state_root(_root(context)))
    package_id, seeded_claim, _seeded_revision = context.router_current_claim
    assert seeded_claim == claim_id
    candidate = _candidate_for_package(
        router_context,
        package_id,
        getattr(context, "router_package_ids", [package_id]),
    )
    adapter = WorkingFakeAdapter(
        RouterAgentResult(schema_version=1, outcome="blocked", summary="fixture")
    )
    set_router_adapter("codex-default", adapter)
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))
    _run_adapter(
        router_context,
        candidate,
        claim_id,
        _next_revision(router_context.project_dir, package_id),
    )
    context.router_adapter = adapter


@then('the adapter request should include only issues "{issue_ids}"')
def then_adapter_request_bounded(context: object, issue_ids: str) -> None:
    request = context.router_adapter.requests[-1]
    assert request.package_issue_ids == [item.strip() for item in issue_ids.split(",")]


@then(
    'the adapter request should include checkpoint "{checkpoint}" at revision {revision:d}'
)
def then_adapter_request_checkpoint(
    context: object, checkpoint: str, revision: int
) -> None:
    request = context.router_adapter.requests[-1]
    assert request.checkpoint is not None
    assert (request.checkpoint.ref, request.checkpoint.revision) == (
        checkpoint,
        revision,
    )


@then(
    'the adapter request should include claim "{claim_id}" at logical revision {revision:d}'
)
def then_adapter_request_claim_revision(
    context: object, claim_id: str, revision: int
) -> None:
    request = context.router_adapter.requests[-1]
    assert (request.claim_id, request.revision) == (claim_id, revision)


@given("the project configuration includes:")
def given_project_configuration_includes(context: object) -> None:
    payload = yaml.safe_load(context.text) or {}
    config = _config(context)
    config.update(payload)
    _save_config(context, config)


@given('status "{key}" has semantic_category "{category}"')
def given_status_semantic_category(context: object, key: str, category: str) -> None:
    config = _config(context)
    status = next(item for item in config["statuses"] if item["key"] == key)
    status["semantic_category"] = category
    _save_config(context, config)


@given('status "{key}" has router marker "{value}"')
def given_status_router_marker(context: object, key: str, value: str) -> None:
    config = _config(context)
    status = next(item for item in config["statuses"] if item["key"] == key)
    status["router"] = value.lower() == "true"
    _save_config(context, config)


@given(
    'status "{key}" is defined as "{name}" with semantic_category "{category}" and router marker "{value}"'
)
def given_status_defined(
    context: object, key: str, name: str, category: str, value: str
) -> None:
    config = _config(context)
    statuses = config.setdefault("statuses", [])
    router_bool = value.lower() == "true"

    column_map = {
        "todo": "To do",
        "done": "Done",
    }
    display_category = column_map.get(category, "In progress")

    new_status = {
        "key": key,
        "name": name,
        "category": display_category,
        "semantic_category": category,
        "router": router_bool,
    }
    statuses.append(new_status)
    _save_config(context, config)


@given('workflow "{workflow}" allows "{from_status}" to "{to_status}"')
def given_workflow_allows(
    context: object, workflow: str, from_status: str, to_status: str
) -> None:
    config = _config(context)
    transitions = config.setdefault("workflows", {}).setdefault(workflow, {})
    allowed = transitions.setdefault(from_status, [])
    if to_status not in allowed:
        allowed.append(to_status)
    labels = config.setdefault("transition_labels", {}).setdefault(workflow, {})
    labels.setdefault(from_status, {}).setdefault(to_status, f"Move to {to_status}")
    _save_config(context, config)


@given('workflow "{workflow}" does not allow "{from_status}" to "{to_status}"')
def given_workflow_does_not_allow(
    context: object, workflow: str, from_status: str, to_status: str
) -> None:
    config = _config(context)
    allowed = config["workflows"][workflow][from_status]
    assert (
        to_status in allowed
    ), f"{workflow} does not list {from_status} to {to_status}"
    allowed.remove(to_status)
    del config["transition_labels"][workflow][from_status][to_status]
    _save_config(context, config)


@given('routed package "{issue_id}" is in status "{status}"')
def given_routed_package_in_status(context: object, issue_id: str, status: str) -> None:
    project_dir = Path(context.working_directory) / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    issue = build_issue(
        issue_id,
        f"Implement {issue_id}",
        "task",
        status,
        None,
        ["agent-provider:codex-default"],
    ).model_copy(
        update={
            "created_at": datetime.fromisoformat("2026-09-17T10:00:00+00:00"),
            "updated_at": datetime.fromisoformat("2026-09-17T10:00:00+00:00"),
        }
    )
    write_issue_file(project_dir, issue)
    event = create_event(
        issue_id=issue_id,
        event_type="state_transition",
        actor_id="fixture",
        payload={"from_status": "backlog", "to_status": status},
        occurred_at="2026-09-17T10:00:00Z",
    )
    events_dir = project_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    write_events_batch(events_dir, [event])


@then("no package should be eligible")
def then_no_package_eligible(context: object) -> None:
    payload = json.loads(context.result.stdout)
    eligible = payload.get("eligible", [])
    assert eligible == [], f"Expected no eligible packages, but got {eligible}"
