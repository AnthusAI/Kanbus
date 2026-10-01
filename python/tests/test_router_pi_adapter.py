"""Tests for the subprocess-backed Pi router adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from kanbus.issue_router import IssueRouterError
from kanbus.models import RouterAgentProfile
from kanbus.router_adapters import (
    ADAPTER_CLASSES,
    PiRunAdapter,
    RouterExecutionRequest,
)

RESULT = {"schema_version": 1, "outcome": "completed", "summary": "done"}


def _events(text: str, session_id: str = "pi-session-1") -> str:
    return "\n".join(
        json.dumps(event)
        for event in (
            {"type": "session", "version": 3, "id": session_id, "cwd": "/w"},
            {"type": "agent_start"},
            {
                "type": "message_end",
                "message": {"role": "user", "content": "the task"},
            },
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": text},
            },
            {"type": "agent_end"},
        )
    )


def _run(monkeypatch, tmp_path, stdout, profile=None, returncode=0, state_dir=None):
    calls = []

    class Process:
        pid = 1

        def __init__(self):
            self.returncode = returncode

        def poll(self):
            return self.returncode

        def communicate(self, timeout=None):
            return stdout, ""

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    monkeypatch.setattr(subprocess, "Popen", popen)
    adapter = PiRunAdapter(
        profile or RouterAgentProfile(adapter="pi"), state_dir=state_dir
    )
    request = RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="claim-1",
        revision=1,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
    )
    return adapter, adapter.execute(request), calls


def test_pi_is_registered_and_defaults_its_command():
    assert ADAPTER_CLASSES["pi"] is PiRunAdapter
    assert RouterAgentProfile(adapter="pi").command == "pi"
    assert RouterAgentProfile(adapter="Pi").adapter == "pi"
    assert RouterAgentProfile(adapter="pi", command="/x/pi").command == "/x/pi"


def test_service_tier_stays_opencode_only():
    with pytest.raises(ValueError, match="requires adapter opencode"):
        RouterAgentProfile(adapter="pi", model="a/b", service_tier="flex")


def test_command_shape_session_id_and_result(monkeypatch, tmp_path):
    profile = RouterAgentProfile(
        adapter="pi", model="anthropic/claude-sonnet-5", args=["--offline"]
    )
    adapter, result, calls = _run(
        monkeypatch, tmp_path, _events(json.dumps(RESULT)), profile
    )
    command, kwargs = calls[0]
    assert command[:7] == [
        "pi",
        "--offline",
        "-p",
        "--mode",
        "json",
        "--model",
        "anthropic/claude-sonnet-5",
    ]
    assert "--session" not in command
    assert "--session-dir" not in command
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert result.outcome == "completed"
    assert adapter.session_id == "pi-session-1"


def test_only_the_last_assistant_message_is_the_result(monkeypatch, tmp_path):
    stdout = "\n".join(
        [
            _events("working on it"),
            json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Result: "},
                            {"type": "tool_call", "name": "bash"},
                            {"type": "text", "text": json.dumps(RESULT)},
                        ],
                    },
                }
            ),
        ]
    )
    _, result, _ = _run(monkeypatch, tmp_path, stdout)
    assert result.summary == "done"


def test_fenced_json_in_the_final_message(monkeypatch, tmp_path):
    text = "Done.\n```json\n" + json.dumps(RESULT) + "\n```\n"
    _, result, _ = _run(monkeypatch, tmp_path, _events(text))
    assert result.outcome == "completed"


def test_invalid_output_and_exit_errors(monkeypatch, tmp_path):
    with pytest.raises(
        IssueRouterError, match="Pi router adapter returned invalid JSON"
    ):
        _run(monkeypatch, tmp_path, _events("no json here"))
    with pytest.raises(
        IssueRouterError, match="Pi router adapter returned invalid JSON"
    ):
        _run(monkeypatch, tmp_path, '{"type":"session","id":"s"}\n')
    with pytest.raises(IssueRouterError, match="Pi router adapter failed"):
        _run(monkeypatch, tmp_path, "", returncode=1)


def test_each_package_gets_a_private_persistent_session_directory(
    monkeypatch, tmp_path
):
    state = tmp_path / "state"
    _, _, calls = _run(
        monkeypatch, tmp_path, _events(json.dumps(RESULT)), state_dir=state
    )
    command = calls[0][0]
    directory = Path(command[command.index("--session-dir") + 1])
    assert directory == state / "pi" / "kbs-1"
    assert directory.is_dir()


def test_resume_continues_the_saved_session(monkeypatch, tmp_path):
    captured = []

    class Process:
        returncode = 0
        pid = 1

        def poll(self):
            return 0

        def communicate(self, timeout=None):
            return _events(json.dumps(RESULT)), ""

    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kw: (captured.append(command), Process())[1],
    )
    request = RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="claim-2",
        revision=2,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
        resume_session_id="pi-saved",
        reply="Use option B.",
    )
    PiRunAdapter(RouterAgentProfile(adapter="pi")).execute(request)
    command = captured[0]
    assert command[command.index("--session") + 1] == "pi-saved"
    assert "A human replied to your question" in command[-1]
    assert "Use option B." in command[-1]
