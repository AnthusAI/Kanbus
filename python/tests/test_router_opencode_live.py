"""Opt-in live smoke test: OpenCode -> Bedrock GPT-OSS 20b.

Run with KANBUS_LIVE_BEDROCK=1 (plus AWS credentials and the opencode CLI).
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from kanbus.models import RouterAgentProfile
from kanbus.router_adapters import OpenCodeRunAdapter, RouterExecutionRequest

pytestmark = pytest.mark.skipif(
    os.environ.get("KANBUS_LIVE_BEDROCK") != "1" or shutil.which("opencode") is None,
    reason="set KANBUS_LIVE_BEDROCK=1 and install opencode to run",
)


def test_gpt_oss_20b_on_bedrock_returns_a_valid_result(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    issues = tmp_path / "project" / "issues"
    issues.mkdir(parents=True)
    (issues / "kbs-1.json").write_text(
        '{"id": "kbs-1", "title": "Add hello file", "status": "in_progress", '
        '"description": "Create a file named hello.txt in the repository root '
        'containing exactly the word hello."}',
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-qm",
            "init",
        ],
        check=True,
    )
    profile = RouterAgentProfile(
        adapter="opencode",
        model="amazon-bedrock/openai.gpt-oss-20b-1:0",
        env={"AWS_REGION": os.environ.get("AWS_REGION", "us-east-1")},
    )
    adapter = OpenCodeRunAdapter(profile)
    result = adapter.execute(
        RouterExecutionRequest(
            package_id="kbs-1",
            claim_id="claim-1",
            revision=1,
            package_issue_ids=["kbs-1"],
            worktree_path=str(tmp_path),
        )
    )
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8").strip() == "hello"
    assert result.outcome == "completed"
    assert result.outcome in {"completed", "blocked", "retryable_failure"}
    assert adapter.session_id
