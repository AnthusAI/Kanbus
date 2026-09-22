"""Tests for the subprocess-backed OpenCode router adapter."""

from __future__ import annotations

import json
import subprocess

import pytest

from kanbus.issue_router import IssueRouterError
from kanbus.models import RouterAgentProfile
from kanbus.router_adapters import OpenCodeRunAdapter, RouterExecutionRequest

RESULT = {"schema_version": 1, "outcome": "completed", "summary": "done"}


def _events(text: str) -> str:
    return "\n".join(
        json.dumps(event)
        for event in (
            {"type": "step_start", "sessionID": "ses_1", "part": {}},
            {"type": "text", "sessionID": "ses_1", "part": {"text": text}},
            {"type": "step_finish", "sessionID": "ses_1", "part": {}},
        )
    )


def _run(monkeypatch, tmp_path, stdout, profile=None, returncode=0):
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
    adapter = OpenCodeRunAdapter(profile or RouterAgentProfile(adapter="opencode"))
    request = RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="claim-1",
        revision=1,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
    )
    return adapter, adapter.execute(request), calls


def test_profile_defaults_command_to_adapter():
    assert RouterAgentProfile(adapter="opencode").command == "opencode"
    assert RouterAgentProfile(adapter="codex").command == "codex"
    assert RouterAgentProfile(adapter="opencode", command="/x/oc").command == "/x/oc"


def test_profile_rejects_unknown_adapter():
    with pytest.raises(ValueError, match="codex or opencode"):
        RouterAgentProfile(adapter="claude")


def test_command_environment_and_session(monkeypatch, tmp_path):
    profile = RouterAgentProfile(
        adapter="opencode",
        model="amazon-bedrock/openai.gpt-oss-20b-1:0",
        env={"AWS_REGION": "us-east-1"},
    )
    adapter, result, calls = _run(
        monkeypatch, tmp_path, _events(json.dumps(RESULT)), profile
    )
    command, kwargs = calls[0]
    assert command[:6] == [
        "opencode",
        "run",
        "--format",
        "json",
        "--model",
        "amazon-bedrock/openai.gpt-oss-20b-1:0",
    ]
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"]["AWS_REGION"] == "us-east-1"
    assert result.outcome == "completed"
    assert adapter.session_id == "ses_1"


def test_fenced_and_prose_wrapped_json(monkeypatch, tmp_path):
    text = "Done.\n```json\n" + json.dumps(RESULT) + "\n```\n"
    _, result, _ = _run(monkeypatch, tmp_path, _events(text))
    assert result.summary == "done"
    _, result, _ = _run(monkeypatch, tmp_path, _events("Result: " + json.dumps(RESULT)))
    assert result.outcome == "completed"


def test_invalid_output_and_exit_errors(monkeypatch, tmp_path):
    with pytest.raises(
        IssueRouterError, match="OpenCode router adapter returned invalid JSON"
    ):
        _run(monkeypatch, tmp_path, _events("no json here"))
    with pytest.raises(IssueRouterError, match="OpenCode router adapter failed"):
        _run(monkeypatch, tmp_path, "", returncode=1)


def test_service_tier_is_sent_as_per_model_opencode_config(monkeypatch, tmp_path):
    profile = RouterAgentProfile(
        adapter="opencode",
        model="amazon-bedrock/minimax.minimax-m2.5",
        service_tier="flex",
    )
    _, _, calls = _run(monkeypatch, tmp_path, _events(json.dumps(RESULT)), profile)
    config = json.loads(calls[0][1]["env"]["OPENCODE_CONFIG_CONTENT"])
    options = config["provider"]["amazon-bedrock"]["models"]["minimax.minimax-m2.5"]
    assert options["options"] == {"serviceTier": "flex"}


def test_service_tier_validation():
    with pytest.raises(ValueError, match="flex, priority or default"):
        RouterAgentProfile(adapter="opencode", model="a/b", service_tier="fast")
    with pytest.raises(ValueError, match="requires adapter opencode"):
        RouterAgentProfile(adapter="codex", model="a/b", service_tier="flex")
    with pytest.raises(ValueError, match="provider/model"):
        RouterAgentProfile(adapter="opencode", model="b", service_tier="flex")


def test_each_run_gets_a_private_data_home_that_is_cleaned_up(monkeypatch, tmp_path):
    adapter, _, calls = _run(monkeypatch, tmp_path, _events(json.dumps(RESULT)))
    data_home = calls[0][1]["env"]["XDG_DATA_HOME"]
    assert "kanbus-opencode-" in data_home
    assert not __import__("pathlib").Path(data_home).exists()
    assert adapter._data_home is None


def _resume_request(tmp_path):
    return RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="claim-2",
        revision=2,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
        resume_session_id="ses_saved",
        reply="Use option B.",
    )


def test_opencode_resume_continues_the_saved_session(monkeypatch, tmp_path):
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
    profile = RouterAgentProfile(adapter="opencode", model="amazon-bedrock/m")
    OpenCodeRunAdapter(profile).execute(_resume_request(tmp_path))
    command = captured[0]
    assert command[command.index("--session") + 1] == "ses_saved"
    assert "A human replied to your question" in command[-1]
    assert "Use option B." in command[-1]


def test_codex_resume_uses_exec_resume_with_the_session_id(monkeypatch, tmp_path):
    from kanbus.router_adapters import CodexExecAdapter

    captured = []

    class Process:
        returncode = 0
        pid = 1

        def poll(self):
            return 0

        def communicate(self, timeout=None):
            return json.dumps(RESULT), ""

    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kw: (captured.append(command), Process())[1],
    )
    CodexExecAdapter(RouterAgentProfile(adapter="codex", model="gpt-x")).execute(
        _resume_request(tmp_path)
    )
    command = captured[0]
    assert command[:5] == ["codex", "exec", "resume", "--json", "--model"]
    assert command[5:7] == ["gpt-x", "ses_saved"]
    assert "--cd" not in command
    assert "Use option B." in command[-1]


def test_a_fresh_request_never_resumes(tmp_path):
    from kanbus.router_adapters import _agent_prompt

    request = RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="c",
        revision=1,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
    )
    assert "human replied" not in _agent_prompt(request)


def test_opencode_data_home_persists_per_package_when_a_state_dir_is_given(tmp_path):
    state = tmp_path / "state"
    profile = RouterAgentProfile(adapter="opencode")
    first = OpenCodeRunAdapter(profile, state_dir=state)
    request = RouterExecutionRequest(
        package_id="kbs-9",
        claim_id="c1",
        revision=1,
        package_issue_ids=["kbs-9"],
        worktree_path=str(tmp_path),
    )
    home = first._environment(request)["XDG_DATA_HOME"]
    first._cleanup()
    assert home == str(state / "opencode" / "kbs-9")
    assert (state / "opencode" / "kbs-9").is_dir()
    # A later attempt for the same package reuses the same directory; another
    # package gets its own.
    again = OpenCodeRunAdapter(profile, state_dir=state)._environment(request)
    assert again["XDG_DATA_HOME"] == home
    other = OpenCodeRunAdapter(profile, state_dir=state)._environment(
        request.model_copy(update={"package_id": "kbs-10"})
    )
    assert other["XDG_DATA_HOME"] != home


def test_only_opencode_needs_its_original_directory_to_resume(tmp_path):
    from types import SimpleNamespace

    from kanbus import router_execution
    from kanbus.router_adapters import CodexExecAdapter

    original = tmp_path / "original"
    original.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    plan = router_execution._ResumePlan(
        session_id="s", reply="r", branch=None, worktree=original
    )
    opencode = OpenCodeRunAdapter(RouterAgentProfile(adapter="opencode"))
    codex = CodexExecAdapter(RouterAgentProfile(adapter="codex"))
    assert router_execution._can_resume(opencode, plan, original) is True
    assert router_execution._can_resume(opencode, plan, elsewhere) is False
    assert router_execution._can_resume(codex, plan, elsewhere) is True
    assert router_execution._can_resume(SimpleNamespace(), plan, elsewhere) is True
    assert router_execution._can_resume(opencode, None, original) is False


def test_a_reply_without_a_resumable_session_reaches_a_fresh_session(tmp_path):
    from kanbus.router_adapters import _agent_prompt

    request = RouterExecutionRequest(
        package_id="kbs-1",
        claim_id="c",
        revision=2,
        package_issue_ids=["kbs-1"],
        worktree_path=str(tmp_path),
        reply="Use option B.",
    )
    prompt = _agent_prompt(request)
    assert "could not be resumed" in prompt
    assert "Use option B." in prompt
