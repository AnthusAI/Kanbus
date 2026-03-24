from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import policy_guidance
from kanbus.policy_context import (
    GuidanceItem,
    GuidanceSeverity,
    PolicyEvaluationReport,
    PolicyOperation,
    PolicyViolationError,
)

from test_helpers import build_issue


def test_guidance_is_enabled_honors_flag_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy_guidance.guidance_is_enabled(no_guidance=True) is False

    monkeypatch.setenv("KANBUS_NO_GUIDANCE", "1")
    assert policy_guidance.guidance_is_enabled() is False

    monkeypatch.setenv("KANBUS_NO_GUIDANCE", "TRUE")
    assert policy_guidance.guidance_is_enabled() is False

    monkeypatch.setenv("KANBUS_NO_GUIDANCE", "off")
    assert policy_guidance.guidance_is_enabled() is True


def test_collect_guidance_for_issue_returns_empty_without_policies_dir(
    tmp_path: Path,
) -> None:
    issue = build_issue("kanbus-1")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        policy_guidance, "load_project_directory", lambda _root: tmp_path
    )
    report = policy_guidance.collect_guidance_for_issue(
        tmp_path, issue, PolicyOperation.UPDATE
    )
    monkeypatch.undo()
    assert report.violations == []
    assert report.guidance_items == []


def test_collect_guidance_for_issue_returns_empty_with_no_policy_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "policies").mkdir(parents=True)

    monkeypatch.setattr(
        policy_guidance, "load_project_directory", lambda _root: project_dir
    )
    monkeypatch.setattr(policy_guidance, "load_policies", lambda _policies_dir: [])

    issue = build_issue("kanbus-1")
    report = policy_guidance.collect_guidance_for_issue(
        tmp_path, issue, PolicyOperation.UPDATE
    )
    assert report.violations == []
    assert report.guidance_items == []


def test_collect_guidance_for_issue_builds_context_and_uses_guidance_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-1")
    all_issues = [issue, build_issue("kanbus-2")]
    project_dir = tmp_path / "project"
    policies_dir = project_dir / "policies"
    policies_dir.mkdir(parents=True)

    seen: dict[str, object] = {}
    documents = [("rules.feature", object())]

    monkeypatch.setattr(
        policy_guidance, "load_project_directory", lambda _root: project_dir
    )
    monkeypatch.setattr(policy_guidance, "load_policies", lambda _d: documents)
    monkeypatch.setattr(
        policy_guidance,
        "get_configuration_path",
        lambda _d: project_dir / "config.yaml",
    )
    monkeypatch.setattr(
        policy_guidance, "load_project_configuration", lambda _p: {"ok": True}
    )
    monkeypatch.setattr(
        policy_guidance, "load_issues_from_directory", lambda _d: all_issues
    )

    def fake_evaluate(
        context: object, docs: object, options: object
    ) -> PolicyEvaluationReport:
        seen["context"] = context
        seen["docs"] = docs
        seen["options"] = options
        return PolicyEvaluationReport(
            guidance_items=[
                GuidanceItem(
                    severity=GuidanceSeverity.SUGGESTION,
                    message="msg",
                    explanations=[],
                    policy_file="rules.feature",
                    scenario="Scenario",
                    step="Then suggest",
                )
            ]
        )

    monkeypatch.setattr(policy_guidance, "evaluate_policies_report", fake_evaluate)

    report = policy_guidance.collect_guidance_for_issue(
        tmp_path, issue, PolicyOperation.CREATE
    )

    assert len(report.guidance_items) == 1
    assert seen["docs"] == documents
    options = seen["options"]
    assert options.collect_all_violations is True
    assert str(options.mode).endswith("GUIDANCE")
    context = seen["context"]
    assert context.current_issue.identifier == "kanbus-1"
    assert context.proposed_issue.identifier == "kanbus-1"
    assert context.transition is None
    assert context.operation == PolicyOperation.CREATE
    assert context.all_issues == all_issues


def test_emit_guidance_for_issues_skips_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        policy_guidance, "guidance_is_enabled", lambda _no_guidance: False
    )
    monkeypatch.setattr(
        policy_guidance,
        "collect_guidance_for_issue",
        lambda *_args, **_kwargs: calls.append("collect"),
    )

    policy_guidance.emit_guidance_for_issues(
        Path("/repo"), [build_issue("kanbus-1")], PolicyOperation.UPDATE
    )
    assert calls == []


def test_emit_guidance_for_issues_emits_sorted_deduped_items_and_converts_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1")
    duplicate = GuidanceItem(
        severity=GuidanceSeverity.SUGGESTION,
        message="consider tags",
        explanations=["add labels"],
        policy_file="b.policy",
        scenario="S2",
        step="Then suggest",
    )
    warning = GuidanceItem(
        severity=GuidanceSeverity.WARNING,
        message="missing owner",
        explanations=["Explanation: owner helps triage", "set assignee"],
        policy_file="a.policy",
        scenario="S1",
        step="Then warn",
    )
    violation = PolicyViolationError(
        policy_file="c.policy",
        scenario="S3",
        failed_step="Then ...",
        message="bad policy",
        issue_id="kanbus-1",
    )
    report = PolicyEvaluationReport(
        guidance_items=[duplicate, duplicate, warning],
        violations=[violation],
    )

    monkeypatch.setattr(
        policy_guidance, "guidance_is_enabled", lambda _no_guidance: True
    )
    monkeypatch.setattr(
        policy_guidance,
        "collect_guidance_for_issue",
        lambda *_args, **_kwargs: report,
    )

    lines: list[str] = []
    monkeypatch.setattr(
        policy_guidance.click, "echo", lambda msg, err=True: lines.append(msg)
    )

    policy_guidance.emit_guidance_for_issues(
        Path("/repo"), [issue], PolicyOperation.UPDATE
    )

    assert sum("GUIDANCE WARNING: missing owner" in line for line in lines) == 1
    assert sum("GUIDANCE SUGGESTION: consider tags" in line for line in lines) == 1
    assert any(
        "Guidance policy error (c.policy / Rule: S3): bad policy" in line
        for line in lines
    )
    assert any("  Explanation: owner helps triage" == line for line in lines)
    assert any("  Explanation: set assignee" == line for line in lines)


def test_emit_guidance_for_issues_ignores_collection_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1")
    monkeypatch.setattr(
        policy_guidance, "guidance_is_enabled", lambda _no_guidance: True
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("broken")

    monkeypatch.setattr(policy_guidance, "collect_guidance_for_issue", _boom)
    monkeypatch.setattr(
        policy_guidance.click,
        "echo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("should not echo")
        ),
    )

    policy_guidance.emit_guidance_for_issues(
        Path("/repo"), [issue], PolicyOperation.UPDATE
    )


def test_sorted_deduped_guidance_items_orders_warning_before_suggestion() -> None:
    warning = GuidanceItem(
        severity=GuidanceSeverity.WARNING,
        message="warn",
        explanations=["w"],
        policy_file="z.policy",
        scenario="Z",
        step="Then warn",
    )
    suggestion = GuidanceItem(
        severity=GuidanceSeverity.SUGGESTION,
        message="suggest",
        explanations=["s"],
        policy_file="a.policy",
        scenario="A",
        step="Then suggest",
    )

    result = policy_guidance.sorted_deduped_guidance_items(
        [suggestion, warning, warning]
    )

    assert len(result) == 2
    assert result[0].severity == GuidanceSeverity.WARNING
    assert result[1].severity == GuidanceSeverity.SUGGESTION
