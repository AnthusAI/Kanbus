"""Soft coordination ownership-loss behavior for router operations."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from kanbus.coordination import CoordinationError
from kanbus.router_execution import (
    _ClaimHandle,
    _RENEWAL_ERRORS,
    _release_claims,
    _start_lease_renewer,
)


def _lease(owner: str | None, claim_id: str | None, *, active: bool = True):
    return SimpleNamespace(
        active=active,
        owner=owner,
        claim_id=claim_id,
        expires_at=datetime.now(UTC),
    )


def test_lost_soft_handles_are_skipped_while_other_capacity_slots_release(
    monkeypatch, tmp_path: Path
) -> None:
    import kanbus.router_execution as execution

    context = SimpleNamespace(root=tmp_path, project_dir=tmp_path / "project")
    handles = [
        _ClaimHandle(
            "git",
            f"router:capacity:provider-profile:{slot}",
            "worker",
            "claim",
            None,
            1,
        )
        for slot in range(3)
    ]
    inspections: Counter[str] = Counter()
    attempted_releases: list[str] = []
    published: list[Path] = []

    def inspect(_events, resource, *, now=None):
        del now
        inspections[resource] += 1
        slot = resource.rsplit(":", 1)[1]
        if slot == "0":
            return _lease("worker-other", "claim-other")
        if slot == "1" and inspections[resource] > 1:
            return _lease("worker-other", "claim-other")
        return _lease("worker", "claim")

    def release(_events, *, resource, **_kwargs):
        attempted_releases.append(resource)
        if resource.endswith(":1"):
            raise CoordinationError("lease owner mismatch")
        return "released-slot-2"

    monkeypatch.setattr(execution, "inspect_lease", inspect)
    monkeypatch.setattr(execution, "soft_release", release)
    monkeypatch.setattr(
        execution, "publish_router_state", lambda root: published.append(root)
    )

    _release_claims(context, handles)

    assert attempted_releases == [
        "router:capacity:provider-profile:2",
        "router:capacity:provider-profile:1",
    ]
    assert inspections["router:capacity:provider-profile:1"] == 2
    assert published == [tmp_path]


def test_late_soft_renewal_loss_is_benign_for_long_adapter(
    monkeypatch, tmp_path: Path
) -> None:
    import kanbus.router_execution as execution

    project_dir = tmp_path / "project"
    claim_id = "long-adapter-late-soft-loss"
    context = SimpleNamespace(
        root=tmp_path,
        project_dir=project_dir,
        configuration=SimpleNamespace(
            coordination=SimpleNamespace(default_lease_ttl="1s")
        ),
    )
    handle = _ClaimHandle("git", "router:issue:kbs-long", "worker", claim_id, None, 1)
    inspections = 0
    ownership_loss_confirmed = threading.Event()
    attempted_renewals: list[str] = []
    recorded_failures: list[dict] = []

    def inspect(_events, _resource, *, now=None):
        nonlocal inspections
        del now
        inspections += 1
        if inspections == 3:
            ownership_loss_confirmed.set()
            return _lease("worker-other", "claim-other")
        return _lease("worker", claim_id)

    def renew(*_args, **kwargs):
        attempted_renewals.append(kwargs["claim_id"])
        raise CoordinationError("lease owner mismatch")

    monkeypatch.setattr(execution, "parse_duration", lambda _value: 1)
    monkeypatch.setattr(execution, "inspect_lease", inspect)
    monkeypatch.setattr(execution, "soft_renew", renew)
    monkeypatch.setattr(execution, "publish_router_state", lambda *_args: None)
    monkeypatch.setattr(
        execution,
        "record_router_event",
        lambda _project, **kwargs: recorded_failures.append(kwargs),
    )
    _RENEWAL_ERRORS.pop(claim_id, None)

    stopped, thread = _start_lease_renewer(context, [handle], claim_id)
    try:
        assert ownership_loss_confirmed.wait(2)
    finally:
        stopped.set()
        thread.join(timeout=2)

    assert not thread.is_alive()
    assert attempted_renewals == [claim_id]
    assert claim_id not in _RENEWAL_ERRORS
    assert recorded_failures == []
