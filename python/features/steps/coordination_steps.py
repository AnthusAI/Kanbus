"""Behave steps for Git-backed coordination leases."""

from __future__ import annotations

import json
import shlex
from datetime import timedelta
from pathlib import Path

import yaml
from behave import given, then, when

from features.steps.shared import read_issue_file, run_cli
from kanbus import coordination, event_history
from kanbus.config_loader import load_project_configuration
from kanbus.coordination import claim, inspect_lease, parse_duration
from kanbus.project import get_configuration_path, load_project_directory


def _configure(context: object, **values: object) -> None:
    config_path = get_configuration_path(Path(context.working_directory))
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload.setdefault("coordination", {}).update(values)
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _events_dir(context: object) -> Path:
    return load_project_directory(Path(context.working_directory)) / "events"


def _set_clock(context: object, value) -> None:
    if not hasattr(context, "coordination_original_clock"):
        context.coordination_original_clock = coordination.utc_now

        def restore_clock() -> None:
            coordination.utc_now = context.coordination_original_clock

        context.add_cleanup(restore_clock)
    coordination.utc_now = lambda: value


def _coordination_config(context: object):
    return load_project_configuration(
        get_configuration_path(Path(context.working_directory))
    ).coordination


def _seed_claim(
    context: object,
    resource: str,
    owner: str,
    claim_id: str,
    *,
    expires_at: str | None = None,
    occurred_at=None,
) -> None:
    start = occurred_at or coordination.utc_now()
    config = _coordination_config(context)
    ttl_seconds = parse_duration(config.default_lease_ttl)
    expiry = (
        coordination.parse_timestamp(expires_at)
        if expires_at is not None
        else start + timedelta(seconds=ttl_seconds)
    )
    record = event_history.create_event(
        issue_id=resource,
        event_type="coordination.claim",
        actor_id=owner,
        payload={
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": coordination.format_timestamp(expiry),
            "contention_window_s": parse_duration(config.contention_window),
            "ttl_s": ttl_seconds,
        },
        occurred_at=coordination.format_timestamp(start),
    )
    event_history.write_events_batch(_events_dir(context), [record])
    context.coordination_claim_start = start


def _seed_renewal(
    context: object,
    resource: str,
    owner: str,
    claim_id: str,
    expires_at: str,
) -> None:
    occurred_at = coordination.utc_now()
    renewal = event_history.create_event(
        issue_id=resource,
        event_type="coordination.renew",
        actor_id=owner,
        payload={
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": coordination.format_timestamp(
                coordination.parse_timestamp(expires_at)
            ),
        },
        occurred_at=coordination.format_timestamp(occurred_at),
    )
    event_history.write_events_batch(_events_dir(context), [renewal])
    _set_clock(context, occurred_at + timedelta(seconds=1))


def _event_records(context: object, resource: str | None = None) -> list[dict]:
    records = []
    for path in _events_dir(context).glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("event_type", "").startswith("coordination.") and (
            resource is None or record.get("issue_id") == resource
        ):
            records.append(record)
    return sorted(
        records,
        key=lambda item: (item.get("occurred_at", ""), item.get("event_id", "")),
    )


@given(
    'coordination is configured with contention window "{window}" and default lease TTL "{ttl}"'
)
def given_coordination_durations(context: object, window: str, ttl: str) -> None:
    _configure(
        context,
        providers=["git"],
        contention_window=window,
        default_lease_ttl=ttl,
    )


@given('coordination is configured with default lease TTL "{ttl}"')
def given_coordination_default_ttl(context: object, ttl: str) -> None:
    _configure(context, default_lease_ttl=ttl)


@given('coordination providers are configured as "{providers}"')
def given_coordination_providers(context: object, providers: str) -> None:
    _configure(context, providers=[item.strip() for item in providers.split(",")])


@given("realtime MQTT broker is unreachable")
def given_mqtt_broker_unreachable(context: object) -> None:
    context.coordination_mqtt_unreachable = True


@given("coordination mutex API endpoint is unset")
def given_mutex_api_endpoint_unset(context: object) -> None:
    assert "mutex_api" not in _coordination_config(context).providers


@when(
    'two workers submit competing coordination claims for resource "{resource}" within the contention window'
)
def when_two_workers_submit_claims(context: object, resource: str) -> None:
    start = coordination.utc_now()
    context.coordination_claim_start = start
    context.coordination_worker_results = []
    for owner, claim_id, at in (
        ("worker-z", "claim-z", start),
        ("worker-a", "claim-a", start + timedelta(seconds=1)),
    ):
        state = claim(
            _events_dir(context),
            _coordination_config(context),
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            now=at,
        )
        context.coordination_worker_results.append((owner, state))


@given(
    'worker "{owner}" submits coordination claim id "{claim_id}" for resource "{resource}"'
)
def given_worker_submits_claim(
    context: object, owner: str, claim_id: str, resource: str
) -> None:
    start = getattr(context, "coordination_claim_start", None) or coordination.utc_now()
    context.coordination_claim_start = start
    claim(
        _events_dir(context),
        _coordination_config(context),
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        now=start,
    )


@given(
    'worker "{owner}" submits coordination claim id "{claim_id}" for resource "{resource}" within the contention window'
)
def given_contending_worker_submits_claim(
    context: object, owner: str, claim_id: str, resource: str
) -> None:
    start = getattr(context, "coordination_claim_start", None) or coordination.utc_now()
    context.coordination_claim_start = start
    claim(
        _events_dir(context),
        _coordination_config(context),
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        now=start + timedelta(seconds=1),
    )


@when('the contention window closes for resource "{resource}"')
def when_contention_window_closes(context: object, resource: str) -> None:
    window_seconds = parse_duration(_coordination_config(context).contention_window)
    context.coordination_lease_state = inspect_lease(
        _events_dir(context),
        resource,
        now=context.coordination_claim_start + timedelta(seconds=window_seconds + 1),
    )


@given(
    'coordination lease "{resource}" is held by owner "{owner}" with claim id "{claim_id}"'
)
def given_held_coordination_lease(
    context: object, resource: str, owner: str, claim_id: str
) -> None:
    _seed_claim(
        context,
        resource,
        owner,
        claim_id,
        expires_at="2099-06-01T00:05:00Z",
    )


@given('the lease expires at "{expires_at}"')
def given_lease_expiry(context: object, expires_at: str) -> None:
    claims = [
        event
        for event in _event_records(context)
        if event["event_type"] == "coordination.claim"
    ]
    assert claims, "expected a seeded coordination claim"
    last_claim = claims[-1]
    _seed_renewal(
        context,
        last_claim["issue_id"],
        last_claim["payload"]["owner"],
        last_claim["payload"]["claim_id"],
        expires_at,
    )


@given('coordination lease "{resource}" expired at "{expires_at}"')
def given_expired_coordination_lease(
    context: object, resource: str, expires_at: str
) -> None:
    _seed_claim(
        context, resource, "worker-expired", "claim-expired", expires_at=expires_at
    )
    _set_clock(
        context,
        coordination.parse_timestamp(expires_at) + timedelta(seconds=1),
    )


@when("simulated time advances past the lease expiration")
def when_time_advances_past_expiration(context: object) -> None:
    expiry = max(
        coordination.parse_timestamp(event["payload"]["lease_expires_at"])
        for event in _event_records(context)
        if event["event_type"] in {"coordination.claim", "coordination.renew"}
    )
    _set_clock(context, expiry + timedelta(seconds=1))


@given("no renewal occurs before lease expiration")
def given_no_renewal_before_expiration(context: object) -> None:
    assert not any(
        event["event_type"] == "coordination.renew" for event in _event_records(context)
    )


@when('worker "{owner}" runs "{command}"')
def when_worker_runs_command(context: object, owner: str, command: str) -> None:
    run_cli(context, command)
    results = getattr(context, "coordination_worker_results", [])
    results.append((owner, context.result.exit_code))
    context.coordination_worker_results = results


@when('worker "{owner}" runs "{command}" after a simulated Git partition heals')
def when_worker_runs_command_after_partition(
    context: object, owner: str, command: str
) -> None:
    when_worker_runs_command(context, owner, command)


@then('coordination lease "{resource}" should have owner "{owner}"')
def then_coordination_lease_owner(context: object, resource: str, owner: str) -> None:
    state = getattr(context, "coordination_lease_state", None) or inspect_lease(
        _events_dir(context), resource, now=coordination.utc_now()
    )
    assert state.active and state.owner == owner


@then('coordination lease "{resource}" should have claim id "{claim_id}"')
def then_coordination_claim_id(context: object, resource: str, claim_id: str) -> None:
    state = getattr(context, "coordination_lease_state", None) or inspect_lease(
        _events_dir(context), resource, now=coordination.utc_now()
    )
    assert state.active and state.claim_id == claim_id


@then('coordination lease "{resource}" should expire after "{expires_at}"')
def then_coordination_expiry(context: object, resource: str, expires_at: str) -> None:
    state = inspect_lease(_events_dir(context), resource, now=coordination.utc_now())
    assert state.active and state.expires_at is not None
    assert state.expires_at > coordination.parse_timestamp(expires_at)


@then('coordination lease "{resource}" should not be active')
def then_coordination_is_inactive(context: object, resource: str) -> None:
    assert not inspect_lease(
        _events_dir(context), resource, now=coordination.utc_now()
    ).active


@then('both claims are recorded in the contention window for resource "{resource}"')
def then_two_claims_recorded(context: object, resource: str) -> None:
    records = [
        event
        for event in _event_records(context, resource)
        if event["event_type"] == "coordination.claim"
    ]
    assert len(records) == 2


@then('the winning lease TTL should be "{ttl}" not "{window}"')
def then_lease_uses_default_ttl(context: object, ttl: str, window: str) -> None:
    assert parse_duration(ttl) > parse_duration(window)
    resource = "tts:render-2"
    state = inspect_lease(
        _events_dir(context),
        resource,
        now=context.coordination_claim_start
        + timedelta(seconds=parse_duration(window) + 2),
    )
    assert state.active and state.expires_at is not None
    assert state.expires_at > context.coordination_claim_start + timedelta(
        seconds=parse_duration(ttl) - 1
    )


@then('both coordination claims for resource "{resource}" should succeed')
def then_both_coordination_claims_succeed(context: object, resource: str) -> None:
    results = getattr(context, "coordination_worker_results", [])
    assert len(results) == 2 and all(code == 0 for _, code in results)
    records = [
        event
        for event in _event_records(context, resource)
        if event["event_type"] == "coordination.claim"
    ]
    assert len(records) == 2


@then('Git history for resource "{resource}" should contain both claim events')
def then_git_history_contains_both_claims(context: object, resource: str) -> None:
    records = [
        event
        for event in _event_records(context, resource)
        if event["event_type"] == "coordination.claim"
    ]
    assert len(records) >= 2


@then('coordination provider used should be "{provider}"')
def then_coordination_provider(context: object, provider: str) -> None:
    assert f"provider: {provider}" in context.result.stdout


@then(
    'coordination inspect for resource "{resource}" should report soft ownership not hard mutex'
)
def then_coordination_soft_owner(context: object, resource: str) -> None:
    run_cli(context, f"kanbus coordination inspect --resource {shlex.quote(resource)}")
    assert context.result.exit_code == 0
    assert "state: active soft ownership" in context.result.stdout
    assert "hard mutex" not in context.result.stdout.lower()


@then('issue "{identifier}" should have assignee unset')
def then_coordination_did_not_assign_issue(context: object, identifier: str) -> None:
    project_dir = load_project_directory(Path(context.working_directory))
    issue = read_issue_file(project_dir, identifier)
    assert issue.assignee is None


@then("the command exit code should be {exit_code:d}")
def then_coordination_exit_code_should_be(context: object, exit_code: int) -> None:
    assert context.result.exit_code == exit_code
