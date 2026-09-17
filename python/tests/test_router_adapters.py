"""Focused tests for the subprocess-backed Codex router adapter."""

from __future__ import annotations

import json
import subprocess

import pytest

from kanbus.issue_router import IssueRouterError
from kanbus.models import RouterAgentProfile
from kanbus.router_adapters import (
    CodexExecAdapter,
    RouterExecutionRequest,
    _find_result_payload,
    _parse_result,
)
from kanbus.router_execution import (
    _adapter_process_record_path,
    _signal_registered_adapter,
)


def test_codex_adapter_captures_structured_output_with_popen(monkeypatch, tmp_path):
    expected = {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "done",
        "issue_updates": [],
        "checkpoint": {"ref": "refs/kanbus/checkpoints/kbs-1", "revision": 1},
        "artifacts": [],
    }
    record_path = tmp_path / "private-router-state" / "claim.json"

    def communicate(self, timeout=None):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record == {
            "schema_version": 2,
            "package_id": "kbs-1",
            "claim_id": "claim-1",
            "pid": 4242,
            "process_identity": "process-identity-4242",
        }
        return json.dumps(expected), ""

    process = type(
        "Process",
        (),
        {
            "returncode": 0,
            "pid": 4242,
            "poll": lambda self: self.returncode,
            "communicate": communicate,
        },
    )()
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(
        "kanbus.router_adapters._process_identity",
        lambda pid: f"process-identity-{pid}",
    )
    adapter = CodexExecAdapter(
        RouterAgentProfile(adapter="codex"), process_record_path=record_path
    )
    result = adapter.execute(
        RouterExecutionRequest(
            package_id="kbs-1",
            claim_id="claim-1",
            revision=1,
            package_issue_ids=["kbs-1"],
            worktree_path=str(tmp_path),
        )
    )

    assert result.outcome == "completed"
    assert result.checkpoint is not None
    assert calls[0][0][1:3] == ["exec", "--json"]
    assert calls[0][1]["stdout"] is subprocess.PIPE
    assert calls[0][1]["stderr"] is subprocess.PIPE
    assert calls[0][1]["text"] is True
    assert "capture_output" not in calls[0][1]
    assert adapter.process is None
    assert not record_path.exists()


def test_codex_adapter_cancel_terminates_registered_process(monkeypatch, tmp_path):
    process = type(
        "Process",
        (),
        {
            "returncode": None,
            "poll": lambda self: self.returncode,
            "terminate": lambda self: setattr(self, "terminated", True),
        },
    )()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    adapter = CodexExecAdapter(RouterAgentProfile(adapter="codex"))
    adapter.process = process

    adapter.cancel("claim-1")

    assert process.terminated is True


def test_external_cancel_signals_only_the_matching_claim_process(monkeypatch, tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    record_path = _adapter_process_record_path(tmp_path, "kbs-1", "claim-1")
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "package_id": "kbs-1",
                "claim_id": "claim-1",
                "pid": 4242,
                "process_identity": "identity-current",
            }
        ),
        encoding="utf-8",
    )
    signals = []
    monkeypatch.setattr(
        "kanbus.router_execution.os.kill", lambda pid, sig: signals.append((pid, sig))
    )
    monkeypatch.setattr(
        "kanbus.router_execution._process_identity", lambda _pid: "identity-current"
    )
    monkeypatch.setattr("kanbus.router_execution.os.pidfd_open", None, raising=False)
    monkeypatch.setattr(
        "kanbus.router_execution.signal.pidfd_send_signal", None, raising=False
    )

    _signal_registered_adapter(tmp_path, "kbs-1", "claim-other")
    assert signals == []

    _signal_registered_adapter(tmp_path, "kbs-1", "claim-1")
    assert signals == [(4242, 15)]


def test_external_cancel_does_not_signal_a_reused_pid(monkeypatch, tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    record_path = _adapter_process_record_path(tmp_path, "kbs-1", "claim-1")
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "package_id": "kbs-1",
                "claim_id": "claim-1",
                "pid": 4242,
                "process_identity": "process-before-reuse",
            }
        ),
        encoding="utf-8",
    )
    signals = []
    monkeypatch.setattr(
        "kanbus.router_execution.os.kill", lambda pid, sig: signals.append((pid, sig))
    )
    monkeypatch.setattr(
        "kanbus.router_execution._process_identity", lambda _pid: "process-after-reuse"
    )

    _signal_registered_adapter(tmp_path, "kbs-1", "claim-1")

    assert signals == []


def test_codex_adapter_terminates_timed_out_process_and_removes_record(
    monkeypatch, tmp_path
):
    record_path = tmp_path / "private-router-state" / "claim.json"

    class Process:
        returncode = None
        pid = 4242

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("codex", timeout)
            return "", ""

    process = Process()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr("kanbus.router_adapters._process_identity", lambda _pid: None)
    adapter = CodexExecAdapter(
        RouterAgentProfile(adapter="codex"), process_record_path=record_path
    )

    with pytest.raises(IssueRouterError, match="adapter failed"):
        adapter.execute(
            RouterExecutionRequest(
                package_id="kbs-1",
                claim_id="claim-1",
                revision=1,
                package_issue_ids=["kbs-1"],
                worktree_path=str(tmp_path),
            )
        )

    assert process.terminated is True
    assert adapter.process is None
    assert not record_path.exists()


def test_codex_adapter_rejects_nonzero_exit_and_invalid_output(monkeypatch, tmp_path):
    class Process:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout

        def communicate(self, timeout=None):
            del timeout
            return self.stdout, "diagnostic"

        def poll(self):
            return self.returncode

    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(9, "{}"),
    )
    adapter = CodexExecAdapter(RouterAgentProfile(adapter="codex"))
    request = RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="claim-1",
        revision=1,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
    )
    with pytest.raises(IssueRouterError, match="adapter failed"):
        adapter.execute(request)

    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(0, "not json"),
    )
    with pytest.raises(IssueRouterError, match="invalid JSON"):
        adapter.execute(request)


def test_adapter_result_parser_selects_last_jsonl_payload_and_validates_schema():
    first = {"schema_version": 1, "outcome": "blocked", "summary": "first"}
    last = {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "last",
        "result": {"schema_version": 1, "outcome": "retryable_failure"},
    }
    payload = _find_result_payload(
        "\n".join(
            [
                json.dumps({"type": "event", "result": first}),
                json.dumps({"type": "result", "structured_output": last}),
            ]
        )
    )
    assert payload == last

    with pytest.raises(IssueRouterError, match='invalid Codex router outcome "future"'):
        _parse_result({"schema_version": 1, "outcome": "future"})
    with pytest.raises(IssueRouterError, match="invalid result"):
        _parse_result({"schema_version": 1, "outcome": "completed", "extra": True})
