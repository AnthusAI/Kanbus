"""Behave steps for Git-backed coordination leases."""

from __future__ import annotations

import json
import shlex
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import yaml
from behave import given, then, use_step_matcher, when

from features.steps.shared import read_issue_file, run_cli
from kanbus import (
    coordination,
    coordination_mqtt,
    coordination_mutex_api,
    event_history,
)
from kanbus.config_loader import load_project_configuration
from kanbus.coordination import (
    claim,
    inspect_lease,
    inspect_published_result,
    parse_duration,
    publish_result,
)
from kanbus.gossip import CoordinationGossipEnvelope, DedupeSet
from kanbus.models import MutexApiConfiguration
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


def _mutex_api_config(context: object) -> MutexApiConfiguration:
    if getattr(context, "working_directory", None) is None:
        return context.mutex_api_configuration
    return _coordination_config(context).mutex_api


class _MutexApiStepResponse:
    def __init__(self, status: int, body: dict | None = None) -> None:
        self.status = status
        self._body = b"" if body is None else json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def _install_fake_mutex_api(context: object) -> None:
    if hasattr(context, "mutex_api_leases"):
        return
    original_urlopen = coordination_mutex_api._urlopen
    context.mutex_api_leases = {}
    context.mutex_api_history = []
    context.mutex_api_last_status = None

    def fake_urlopen(request, *, timeout: float):
        assert timeout == coordination_mutex_api.REQUEST_TIMEOUT_SECONDS
        method = request.get_method()
        path = urlparse(request.full_url).path
        prefix = "/api/coordination/leases/"
        assert path.startswith(prefix)
        resource = unquote(path[len(prefix) :])
        payload = json.loads(request.data) if request.data else None
        leases = context.mutex_api_leases
        lease = leases.get(resource)
        now = int(coordination.utc_now().timestamp())
        if lease is not None and lease["expires_at"] <= now:
            del leases[resource]
            lease = None

        if method == "POST":
            if lease is not None:
                response = _MutexApiStepResponse(409, {"message": "lease already held"})
            else:
                assert payload is not None
                lease = {
                    "resource": resource,
                    "owner": payload["owner"],
                    "claim_id": payload["claim_id"],
                    "revision": payload["revision"],
                    "claimed_at": now,
                    "expires_at": now + payload["ttl_seconds"],
                }
                leases[resource] = lease
                response = _MutexApiStepResponse(201, lease)
        elif method == "GET":
            response = (
                _MutexApiStepResponse(404, {"message": "no live lease"})
                if lease is None
                else _MutexApiStepResponse(200, lease)
            )
        elif method in {"PUT", "DELETE"}:
            if lease is None:
                response = _MutexApiStepResponse(404, {"message": "no live lease"})
            elif (payload["owner"], payload["claim_id"]) != (
                lease["owner"],
                lease["claim_id"],
            ):
                response = _MutexApiStepResponse(
                    403, {"message": "lease owner mismatch"}
                )
            elif method == "PUT":
                lease["expires_at"] = (
                    max(lease["expires_at"], now) + payload["extend_seconds"]
                )
                response = _MutexApiStepResponse(200, lease)
            else:
                del leases[resource]
                response = _MutexApiStepResponse(204)
        else:
            raise AssertionError(f"unexpected mutex API method: {method}")
        context.mutex_api_last_status = response.status
        return response

    coordination_mutex_api._urlopen = fake_urlopen

    def restore() -> None:
        coordination_mutex_api._urlopen = original_urlopen

    context.add_cleanup(restore)


def _set_mutex_api_endpoint(context: object, endpoint: str) -> None:
    _install_fake_mutex_api(context)
    context.mutex_api_configuration = MutexApiConfiguration(
        endpoint=endpoint, bearer_token="behave-test-token"
    )
    if getattr(context, "working_directory", None) is None:
        return
    config_path = get_configuration_path(Path(context.working_directory))
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    mutex_api = payload.setdefault("coordination", {}).setdefault("mutex_api", {})
    mutex_api.update(endpoint=endpoint, bearer_token="behave-test-token")
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


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
        contention_window=window,
        default_lease_ttl=ttl,
    )


@given('coordination is configured with default lease TTL "{ttl}"')
def given_coordination_default_ttl(context: object, ttl: str) -> None:
    _configure(context, default_lease_ttl=ttl)


@given('coordination providers are configured as "{providers}"')
def given_coordination_providers(context: object, providers: str) -> None:
    configured = [item.strip() for item in providers.split(",")]
    if set(configured) == {"mutex_api", "mqtt", "git"}:
        configured = ["mutex_api", "mqtt", "git"]
    elif set(configured) == {"mqtt", "git"}:
        configured = ["mqtt", "git"]
    _configure(context, providers=configured)


@given(
    'coordination MQTT publishes to "{topic}" with QoS {qos:d} and retain={retained}'
)
def given_coordination_mqtt_topic(
    context: object, topic: str, qos: int, retained: str
) -> None:
    assert qos == 0
    assert retained == "false"
    context.coordination_mqtt_messages = []
    config_path = get_configuration_path(Path(context.working_directory))
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    realtime = payload.setdefault("realtime", {})
    realtime["transport"] = "mqtt"
    realtime["broker"] = "mqtt://127.0.0.1:1"
    realtime["autostart"] = False
    realtime.setdefault("topics", {})["project_events"] = topic
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _publish_coordination_gossip(
    context: object,
    owner: str,
    event_type: str,
    resource: str,
    claim_id: str,
    *,
    within_window: bool = False,
) -> CoordinationGossipEnvelope:
    root = Path(context.working_directory)
    project_dir = load_project_directory(root)
    configuration = load_project_configuration(get_configuration_path(root))
    prior_start = getattr(context, "coordination_claim_start", None)
    occurred_at = prior_start or coordination.utc_now()
    if (
        within_window
        or event_type == "coordination.release"
        and prior_start is not None
    ):
        occurred_at += timedelta(seconds=1)
    if prior_start is None:
        context.coordination_claim_start = occurred_at

    if event_type == "coordination.claim":
        state = claim(
            project_dir / "events",
            configuration.coordination,
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            now=occurred_at,
        )
        assert state.operation_event_id is not None
        envelope = coordination_mqtt.make_claim_envelope(
            root,
            project_dir,
            configuration,
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            event_id=state.operation_event_id,
            lease_ttl_s=parse_duration(configuration.coordination.default_lease_ttl),
            occurred_at=occurred_at,
        )
    elif event_type == "coordination.release":
        # Model an optimistic release gossip arriving before its durable Git
        # release event has landed on this checkout.
        envelope = coordination_mqtt.make_release_envelope(
            root,
            project_dir,
            configuration,
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            event_id=f"release-{uuid4()}",
            occurred_at=occurred_at,
        )
    else:
        raise AssertionError(f"unsupported coordination gossip type: {event_type}")

    coordination_mqtt.record_envelope(
        project_dir, envelope, ttl_s=configuration.overlay.ttl_s
    )
    context.coordination_mqtt_messages.append(envelope)
    return envelope


@when(
    'worker "{owner}" publishes coordination gossip type "{event_type}" for resource "{resource}" with claim id "{claim_id}"'
)
def when_worker_publishes_coordination_gossip(
    context: object, owner: str, event_type: str, resource: str, claim_id: str
) -> None:
    context.last_coordination_envelope = _publish_coordination_gossip(
        context, owner, event_type, resource, claim_id
    )


@given(
    'worker "{owner}" published coordination gossip type "{event_type}" for resource "{resource}" with claim id "{claim_id}"'
)
def given_worker_published_coordination_gossip(
    context: object, owner: str, event_type: str, resource: str, claim_id: str
) -> None:
    context.last_coordination_envelope = _publish_coordination_gossip(
        context, owner, event_type, resource, claim_id
    )


@given(
    'worker "{owner}" published coordination gossip type "{event_type}" for resource "{resource}" with claim id "{claim_id}" within the contention window'
)
def given_worker_published_coordination_gossip_within_window(
    context: object, owner: str, event_type: str, resource: str, claim_id: str
) -> None:
    context.last_coordination_envelope = _publish_coordination_gossip(
        context, owner, event_type, resource, claim_id, within_window=True
    )


@then(
    'MQTT subscribers should receive envelope type "{event_type}" for resource "{resource}"'
)
def then_mqtt_subscribers_receive_coordination(
    context: object, event_type: str, resource: str
) -> None:
    assert any(
        envelope.type == event_type and envelope.resource == resource
        for envelope in context.coordination_mqtt_messages
    )


@then('the coordination envelope should contain top-level fields "{fields}"')
def then_coordination_envelope_fields(context: object, fields: str) -> None:
    envelope = context.last_coordination_envelope
    payload = envelope.model_dump(mode="json", exclude_none=True)
    assert {item.strip() for item in fields.split(",")} <= set(payload)


@then(
    'receivers should ignore their own producer id and deduplicate envelope ids for "{ttl}"'
)
def then_coordination_gossip_dedupe(context: object, ttl: str) -> None:
    assert parse_duration(ttl) == coordination_mqtt.DEDUPE_TTL_S == 3600
    envelope = context.last_coordination_envelope
    dedupe = DedupeSet(ttl_s=coordination_mqtt.DEDUPE_TTL_S)
    assert coordination_mqtt.should_ignore_envelope(
        envelope, dedupe, envelope.producer_id
    )
    assert coordination_mqtt.should_ignore_envelope(
        envelope, dedupe, "another-producer"
    )


@given("realtime MQTT broker is unreachable")
def given_mqtt_broker_unreachable(context: object) -> None:
    context.coordination_mqtt_unreachable = True


@given('MQTT partition isolates worker "{first}" from worker "{second}"')
def given_coordination_mqtt_partition(context: object, first: str, second: str) -> None:
    assert first and second
    context.coordination_mqtt_unreachable = True
    config_path = get_configuration_path(Path(context.working_directory))
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    realtime = payload.setdefault("realtime", {})
    realtime.update(
        transport="mqtt",
        broker="mqtt://127.0.0.1:1",
        autostart=False,
    )
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@given("coordination mutex API endpoint is unset")
def given_mutex_api_endpoint_unset(context: object) -> None:
    assert "mutex_api" not in _coordination_config(context).providers


@given('coordination mutex API endpoint is "{endpoint}"')
def given_mutex_api_endpoint(context: object, endpoint: str) -> None:
    _set_mutex_api_endpoint(context, endpoint)


@given("mutex API live lease storage is empty")
def given_mutex_api_storage_empty(context: object) -> None:
    _install_fake_mutex_api(context)
    context.mutex_api_leases.clear()
    context.mutex_api_history.clear()


@given('mutex API accepts acquire for resource "{resource}"')
def given_mutex_api_accepts_acquire(context: object, resource: str) -> None:
    _install_fake_mutex_api(context)
    context.mutex_api_leases.pop(resource, None)


use_step_matcher("re")


@given(
    r'mutex API live lease for "(?P<resource>[^"]+)" is held by owner "(?P<owner>[^"]+)" with claim id "(?P<claim_id>[^"]+)" expiring at "(?P<expires_at>[^"]+)"'
)
@given(
    r'mutex API live lease for "(?P<resource>[^"]+)" is held by owner "(?P<owner>[^"]+)" with claim id "(?P<claim_id>[^"]+)"'
)
def given_mutex_api_live_lease(
    context: object,
    resource: str,
    owner: str,
    claim_id: str,
    expires_at: str | None = None,
) -> None:
    _install_fake_mutex_api(context)
    now = int(coordination.utc_now().timestamp())
    context.mutex_api_leases[resource] = {
        "resource": resource,
        "owner": owner,
        "claim_id": claim_id,
        "revision": 1,
        "claimed_at": now,
        "expires_at": now + 300,
    }
    if expires_at is not None:
        context.mutex_api_leases[resource]["expires_at"] = int(
            coordination.parse_timestamp(expires_at).timestamp()
        )


use_step_matcher("parse")


@given('mutex API live lease for "{resource}" expired by TTL garbage collection')
def given_mutex_api_expired_lease(context: object, resource: str) -> None:
    _install_fake_mutex_api(context)
    context.mutex_api_leases.pop(resource, None)


@when(
    'mutex API client acquires resource "{resource}" for owner "{owner}" with claim id "{claim_id}" revision {revision:d} lease TTL "{ttl}"'
)
def when_mutex_api_client_acquires(
    context: object, resource: str, owner: str, claim_id: str, revision: int, ttl: str
) -> None:
    try:
        context.mutex_api_response = coordination_mutex_api.acquire(
            _mutex_api_config(context),
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            revision=revision,
            ttl_seconds=parse_duration(ttl),
        )
        context.mutex_api_response_body = vars(context.mutex_api_response)
        context.mutex_api_response_status = 201
        context.mutex_api_error = ""
    except coordination_mutex_api.MutexApiError as error:
        context.mutex_api_response = None
        context.mutex_api_response_body = {}
        context.mutex_api_response_status = error.status
        context.mutex_api_error = str(error)


@when(
    'mutex API client renews resource "{resource}" for owner "{owner}" with claim id "{claim_id}" extending "{extend}"'
)
def when_mutex_api_client_renews(
    context: object, resource: str, owner: str, claim_id: str, extend: str
) -> None:
    try:
        context.mutex_api_response = coordination_mutex_api.renew(
            _mutex_api_config(context),
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            extend_seconds=parse_duration(extend),
        )
        context.mutex_api_response_body = vars(context.mutex_api_response)
        context.mutex_api_response_status = 200
        context.mutex_api_error = ""
    except coordination_mutex_api.MutexApiError as error:
        context.mutex_api_response = None
        context.mutex_api_response_body = {}
        context.mutex_api_response_status = error.status
        context.mutex_api_error = str(error)


@when(
    'mutex API client releases resource "{resource}" for owner "{owner}" with claim id "{claim_id}"'
)
def when_mutex_api_client_releases(
    context: object, resource: str, owner: str, claim_id: str
) -> None:
    try:
        coordination_mutex_api.release(
            _mutex_api_config(context),
            resource=resource,
            owner=owner,
            claim_id=claim_id,
        )
        context.mutex_api_response_body = {}
        context.mutex_api_response_status = 204
        context.mutex_api_error = ""
    except coordination_mutex_api.MutexApiError as error:
        context.mutex_api_response_body = {}
        context.mutex_api_response_status = error.status
        context.mutex_api_error = str(error)


@when('mutex API client inspects resource "{resource}"')
def when_mutex_api_client_inspects(context: object, resource: str) -> None:
    lease = coordination_mutex_api.inspect(
        _mutex_api_config(context), resource=resource
    )
    context.mutex_api_response = lease
    context.mutex_api_response_body = {} if lease is None else vars(lease)
    context.mutex_api_response_status = 404 if lease is None else 200
    context.mutex_api_error = "no live lease" if lease is None else ""


@then("mutex API {action} response status should be {status:d}")
def then_mutex_api_response_status(context: object, action: str, status: int) -> None:
    assert context.mutex_api_response_status == status


@then('mutex API error message should contain "{message}"')
def then_mutex_api_error_message(context: object, message: str) -> None:
    assert message in context.mutex_api_error


@then('mutex API live lease for "{resource}" should include {field} "{value}"')
def then_mutex_api_live_lease_string_field(
    context: object, resource: str, field: str, value: str
) -> None:
    lease = context.mutex_api_leases[resource]
    assert lease[field.replace(" ", "_")] == value


@then('mutex API live lease for "{resource}" should include revision {revision:d}')
def then_mutex_api_live_lease_revision(
    context: object, resource: str, revision: int
) -> None:
    assert context.mutex_api_leases[resource]["revision"] == revision


@then('mutex API live lease for "{resource}" should include {field} timestamp')
def then_mutex_api_live_lease_timestamp(
    context: object, resource: str, field: str
) -> None:
    assert isinstance(context.mutex_api_leases[resource][field], (int, float))


@then('mutex API live lease for "{resource}" should expire after "{timestamp}"')
def then_mutex_api_live_lease_expires_after(
    context: object, resource: str, timestamp: str
) -> None:
    assert context.mutex_api_leases[resource]["expires_at"] > int(
        coordination.parse_timestamp(timestamp).timestamp()
    )


@then('mutex API live lease for "{resource}" should not exist')
def then_mutex_api_live_lease_missing(context: object, resource: str) -> None:
    assert resource not in context.mutex_api_leases


@then('mutex API inspect body should contain claim id "{claim_id}"')
def then_mutex_api_inspect_claim_id(context: object, claim_id: str) -> None:
    assert context.mutex_api_response_body["claim_id"] == claim_id


@then('mutex API inspect body should contain "{text}"')
def then_mutex_api_inspect_body_text(context: object, text: str) -> None:
    assert text in context.mutex_api_error or text in json.dumps(
        context.mutex_api_response_body
    )


@then(
    'mutex API storage for resource "{resource}" should contain no historical claim records'
)
def then_mutex_api_no_history(context: object, resource: str) -> None:
    assert resource not in context.mutex_api_leases
    assert not context.mutex_api_history


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
    root = Path(context.working_directory)
    project_dir = load_project_directory(root)
    configuration = load_project_configuration(get_configuration_path(root))
    window_seconds = parse_duration(configuration.coordination.contention_window)
    now = context.coordination_claim_start + timedelta(seconds=window_seconds + 1)
    state, envelope = coordination_mqtt.select_lease_envelope(
        root,
        project_dir,
        project_dir / "events",
        resource,
        configuration,
        now=now,
    )
    context.coordination_lease_state = state
    context.coordination_lease_envelope = envelope
    if envelope is not None:
        coordination_mqtt.record_envelope(
            project_dir, envelope, ttl_s=configuration.overlay.ttl_s
        )
        context.coordination_mqtt_messages.append(envelope)


@then(
    'coordination gossip type "{event_type}" should be emitted for resource "{resource}" with claim id "{claim_id}"'
)
def then_coordination_gossip_emitted(
    context: object, event_type: str, resource: str, claim_id: str
) -> None:
    envelope = context.coordination_lease_envelope
    assert envelope is not None
    assert (envelope.type, envelope.resource, envelope.claim_id) == (
        event_type,
        resource,
        claim_id,
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


@given('logical task revision for resource "{resource}" is {revision:d}')
def given_logical_task_revision(context: object, resource: str, revision: int) -> None:
    context.logical_task = (resource, revision)


@given('published revision for resource "{resource}" is {revision:d}')
def given_published_result_revision(
    context: object, resource: str, revision: int
) -> None:
    publish_result(
        _events_dir(context),
        resource=resource,
        revision=revision,
        artifact=f"fixture-artifact-r{revision}",
        actor_id="fixture-worker",
    )


@given('backstop eligibility threshold is "{threshold}"')
def given_backstop_threshold(context: object, threshold: str) -> None:
    context.backstop_threshold_seconds = parse_duration(threshold)


@when('simulated time advances by "{duration}" without a published result')
def when_backstop_time_advances(context: object, duration: str) -> None:
    elapsed = parse_duration(duration)
    context.backstop_elapsed_seconds = elapsed
    start = context.coordination_claim_start
    _set_clock(context, start + timedelta(seconds=elapsed))


@then('published revision for resource "{resource}" should be {revision:d}')
def then_published_result_revision(
    context: object, resource: str, revision: int
) -> None:
    result = inspect_published_result(_events_dir(context), resource)
    assert result is not None and result.revision == revision


@then('cloud backstop worker should not yet be eligible for resource "{resource}"')
def then_backstop_not_eligible(context: object, resource: str) -> None:
    assert getattr(context, "logical_task", (resource, None))[0] == resource
    threshold = getattr(context, "backstop_threshold_seconds", 15 * 60)
    assert context.backstop_elapsed_seconds < threshold
    assert inspect_published_result(_events_dir(context), resource) is None


@then('cloud backstop worker should be eligible for resource "{resource}"')
def then_backstop_eligible(context: object, resource: str) -> None:
    threshold = getattr(context, "backstop_threshold_seconds", 15 * 60)
    elapsed = getattr(context, "backstop_elapsed_seconds", threshold)
    assert elapsed >= threshold
    assert inspect_published_result(_events_dir(context), resource) is None


@given('cloud backstop worker is eligible for resource "{resource}"')
def given_backstop_eligible(context: object, resource: str) -> None:
    context.backstop_eligible_resource = resource


@then('Git remains the durable history for resource "{resource}"')
def then_git_remains_durable_history(context: object, resource: str) -> None:
    assert any(
        event["issue_id"] == resource
        for event in _event_records(context, resource)
        if event["event_type"] == "coordination.claim"
    )


@when('cloud worker runs "{command}"')
def when_cloud_worker_runs(context: object, command: str) -> None:
    run_cli(context, command)


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
    cli_results = getattr(context, "coordination_cli_results", [])
    cli_results.append(context.result)
    context.coordination_cli_results = cli_results


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


@then(
    'the LEASE envelope should identify the winning claim event and contain top-level fields "{fields}"'
)
def then_lease_envelope_identifies_winner(context: object, fields: str) -> None:
    envelope = context.coordination_lease_envelope
    state = context.coordination_lease_state
    assert envelope is not None and state.event_id is not None
    assert envelope.event_id == state.event_id
    payload = envelope.model_dump(mode="json", exclude_none=True)
    assert {item.strip() for item in fields.split(",")} <= set(payload)


@then("the LEASE expiry should equal the winning claim timestamp plus its lease TTL")
def then_lease_expiry_matches_winning_claim(context: object) -> None:
    envelope = context.coordination_lease_envelope
    state = context.coordination_lease_state
    assert envelope is not None and state.claimed_at is not None
    assert envelope.lease_ttl_s is not None and envelope.expires_at is not None
    expected = state.claimed_at + timedelta(seconds=envelope.lease_ttl_s)
    assert coordination.parse_timestamp(envelope.expires_at) == expected


@then('the RELEASE envelope should contain top-level fields "{fields}"')
def then_release_envelope_fields(context: object, fields: str) -> None:
    envelope = context.last_coordination_envelope
    payload = envelope.model_dump(mode="json", exclude_none=True)
    assert envelope.type == "coordination.release"
    assert {item.strip() for item in fields.split(",")} <= set(payload)


@then(
    "the matching soft lease should be cleared from MQTT visibility while Git remains the durable history"
)
def then_release_clears_mqtt_visibility(context: object) -> None:
    root = Path(context.working_directory)
    project_dir = load_project_directory(root)
    configuration = load_project_configuration(get_configuration_path(root))
    envelope = context.last_coordination_envelope
    assert envelope.type == "coordination.release"
    state = coordination_mqtt.inspect_lease(
        project_dir / "events",
        project_dir,
        envelope.resource,
        configuration,
        now=max(
            coordination.utc_now(),
            coordination.parse_timestamp(envelope.ts) + timedelta(seconds=1),
        ),
    )
    assert not state.active
    durable_releases = [
        event
        for event in _event_records(context, envelope.resource)
        if event["event_type"] == "coordination.release"
    ]
    assert not durable_releases


@then(
    "an MQTT partition may allow duplicate work because soft leases are not hard mutexes"
)
def then_partition_is_soft_only(context: object) -> None:
    results = getattr(context, "coordination_worker_results", [])
    assert len(results) == 2 and all(code == 0 for _, code in results)
    assert all(
        "provider: git" in result.stdout
        for result in getattr(context, "coordination_cli_results", [])
    )


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
