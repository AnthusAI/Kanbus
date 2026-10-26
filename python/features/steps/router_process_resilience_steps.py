"""Behave steps for router process hygiene and watch resilience."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from behave import given, then, when

from kanbus.issue_router import IssueRouterError
from kanbus.router_adapters import (
    _process_identity,
    spawn_adapter_process,
    terminate_process_tree,
)
from kanbus.router_execution import (
    _adapter_process_record_path,
    _signal_registered_adapter,
    decide_watch_poll_failure,
)

PACKAGE_IDENTIFIER = "kbs-resilience"
CLAIM_IDENTIFIER = "claim-resilience"
SHUTDOWN_DEADLINE_SECONDS = 5.0


def _process_is_alive(process_identifier: int) -> bool:
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(process_identifier)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return bool(status) and not status.startswith("Z")


def _wait_until_process_ends(process_identifier: int) -> bool:
    deadline = time.monotonic() + SHUTDOWN_DEADLINE_SECONDS
    while _process_is_alive(process_identifier):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _kill_leftover(process_identifier: int) -> None:
    try:
        os.kill(process_identifier, 9)
    except OSError:
        return


@given("a router adapter process that forked a sleeping grandchild")
def given_adapter_with_sleeping_grandchild(context: object) -> None:
    process = spawn_adapter_process(
        ["sh", "-c", "sleep 300 & echo $!; wait"],
        working_directory=None,
        environment=None,
    )
    assert process.stdout is not None
    context.resilience_adapter = process
    context.resilience_grandchild = int(process.stdout.readline().strip())
    context.add_cleanup(lambda: _kill_leftover(context.resilience_grandchild))
    assert _process_is_alive(context.resilience_grandchild)


@when("the router terminates the adapter process tree")
def when_router_terminates_adapter_tree(context: object) -> None:
    terminate_process_tree(context.resilience_adapter)


@then("the adapter process should be reaped")
def then_adapter_process_reaped(context: object) -> None:
    assert context.resilience_adapter.returncode is not None


@then("the grandchild process should no longer be running")
def then_grandchild_gone(context: object) -> None:
    assert _wait_until_process_ends(
        context.resilience_grandchild
    ), "grandchild survived termination of its adapter"


@given("the router watch interval is {interval:d} seconds")
def given_watch_interval_seconds(context: object, interval: int) -> None:
    context.resilience_interval = interval


_POLL_FAILURES = {
    "HTTP status 500": "GitHub API returned status 500",
    "HTTP status 429": "GitHub API returned status 429",
    "HTTP status 401": "GitHub API returned status 401",
    "a network error": "GitHub API unavailable",
}


@when(
    "GitHub pull request polling fails with {failure} for consecutive failure {count:d}"
)
def when_pull_request_polling_fails(context: object, failure: str, count: int) -> None:
    context.resilience_decision = decide_watch_poll_failure(
        IssueRouterError(_POLL_FAILURES[failure]), context.resilience_interval, count
    )


@then("the router watch should retry after {seconds:d} seconds")
def then_watch_retries(context: object, seconds: int) -> None:
    assert context.resilience_decision == seconds, context.resilience_decision


@then("the router watch should stop")
def then_watch_stops(context: object) -> None:
    assert context.resilience_decision is None, context.resilience_decision


def _record_active_adapter(
    context: object, decoy: subprocess.Popen[bytes], identity: str | None
) -> None:
    directory = tempfile.TemporaryDirectory()
    context.add_cleanup(directory.cleanup)
    root = Path(directory.name)
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    record_path = _adapter_process_record_path(
        root, PACKAGE_IDENTIFIER, CLAIM_IDENTIFIER
    )
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "package_id": PACKAGE_IDENTIFIER,
                "claim_id": CLAIM_IDENTIFIER,
                "pid": decoy.pid,
                "process_identity": identity,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    context.resilience_root = root
    context.resilience_decoy = decoy
    context.add_cleanup(lambda: (decoy.kill(), decoy.wait()))


def _start_decoy() -> subprocess.Popen[bytes]:
    return subprocess.Popen(["sleep", "300"], start_new_session=True)


@given("a recorded active adapter whose process ID now belongs to an unrelated process")
def given_recorded_adapter_with_reused_process_id(context: object) -> None:
    decoy = _start_decoy()
    foreign_identity = _process_identity(os.getpid())
    assert foreign_identity is not None
    _record_active_adapter(context, decoy, foreign_identity)


@given("a recorded active adapter whose process identity matches")
def given_recorded_adapter_with_matching_identity(context: object) -> None:
    decoy = _start_decoy()
    identity = _process_identity(decoy.pid)
    assert identity is not None
    _record_active_adapter(context, decoy, identity)


@when("the router signals the registered adapter for its package claim")
def when_router_signals_registered_adapter(context: object) -> None:
    _signal_registered_adapter(
        context.resilience_root, PACKAGE_IDENTIFIER, CLAIM_IDENTIFIER
    )


@then("the unrelated process should still be running")
def then_unrelated_process_still_running(context: object) -> None:
    time.sleep(0.3)
    assert context.resilience_decoy.poll() is None


@then("the recorded adapter process should have been terminated")
def then_recorded_adapter_terminated(context: object) -> None:
    context.resilience_decoy.wait(timeout=SHUTDOWN_DEADLINE_SECONDS)
    assert context.resilience_decoy.returncode is not None
