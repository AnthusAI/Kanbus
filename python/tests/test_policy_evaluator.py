from __future__ import annotations

from types import SimpleNamespace

import pytest

from kanbus import policy_evaluator
from kanbus.policy_context import PolicyOperation
from kanbus.policy_steps import StepOutcome

from test_helpers import build_issue, build_project_configuration


def _context():
    issue = build_issue("kanbus-1")
    return SimpleNamespace(
        proposed_issue=issue,
        current_issue=issue,
        transition=None,
        operation=PolicyOperation.UPDATE,
        project_configuration=build_project_configuration(),
        all_issues=[issue],
    )


def _step(keyword: str, text: str):
    return SimpleNamespace(keyword=keyword, text=text)


def _scenario(name: str, steps: list[object]):
    return SimpleNamespace(name=name, steps=steps)


def _doc_with_children(children: list[object]):
    return SimpleNamespace(feature=SimpleNamespace(children=children))


class _FakeStepDef:
    def __init__(self, outcome: StepOutcome, message: str | None = None):
        self._outcome = outcome
        self._message = message

    def execute(self, _context, _match):
        return self._outcome, self._message


class _FakeRegistry:
    def __init__(self, outcomes: dict[str, tuple[StepOutcome, str | None]]):
        self._outcomes = outcomes

    def find_step(self, text: str):
        if text not in self._outcomes:
            return None
        outcome, message = self._outcomes[text]
        return _FakeStepDef(outcome, message), object()


def test_get_step_registry_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    policy_evaluator._REGISTRY = None
    created: list[str] = []

    class _Registry:
        def __init__(self):
            created.append("x")

    monkeypatch.setattr(policy_evaluator, "StepRegistry", _Registry)

    first = policy_evaluator._get_step_registry()
    second = policy_evaluator._get_step_registry()
    assert first is second
    assert created == ["x"]


def test_is_explain_step_and_iter_policy_rule_units() -> None:
    assert policy_evaluator._is_explain_step('explain "x"') is True
    assert policy_evaluator._is_explain_step("explain x") is False

    no_feature = SimpleNamespace(feature=None)
    assert policy_evaluator._iter_policy_rule_units(no_feature) == []

    top_scenario = _scenario("Top", [_step("Given", "a")])
    nested_scenario = _scenario("Nested", [_step("When", "b")])
    rule = SimpleNamespace(
        name="RuleA",
        children=[
            SimpleNamespace(scenario=nested_scenario),
            SimpleNamespace(other=True),
        ],
    )
    doc = _doc_with_children(
        [
            SimpleNamespace(scenario=top_scenario),
            SimpleNamespace(rule=rule),
            SimpleNamespace(),
        ]
    )

    units = policy_evaluator._iter_policy_rule_units(doc)
    assert units[0][0] == "Top"
    assert units[1][0] == "RuleA / Nested"


def test_policy_structure_violation_carries_issue_id() -> None:
    violation = policy_evaluator._policy_structure_violation(
        context=_context(),
        policy_file="x.policy",
        scenario_name="S",
        failed_step="Then x",
        message="m",
    )
    assert violation.issue_id == "kanbus-1"


def test_validate_policy_documents_reports_unknown_and_orphan_explain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context()
    registry = _FakeRegistry(
        {
            'explain "x"': (StepOutcome.EXPLAIN, "x"),
            'warn "w"': (StepOutcome.WARN, "w"),
            'explain "ok"': (StepOutcome.EXPLAIN, "ok"),
        }
    )
    monkeypatch.setattr(policy_evaluator, "_get_step_registry", lambda: registry)

    doc = _doc_with_children(
        [
            SimpleNamespace(
                scenario=_scenario(
                    "S1",
                    [
                        _step("Given", "unknown step"),
                        _step("Then", 'explain "x"'),
                        _step("Given", 'warn "w"'),
                        _step("Then", 'explain "ok"'),
                    ],
                )
            )
        ]
    )

    violations = policy_evaluator.validate_policy_documents(ctx, [("p.feature", doc)])
    messages = [v.message for v in violations]
    assert any("no matching step definition" in m for m in messages)
    assert any("orphan explain step" in m for m in messages)


def test_validate_policy_documents_reports_orphan_explain_at_first_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context()
    registry = _FakeRegistry({'explain "x"': (StepOutcome.EXPLAIN, "x")})
    monkeypatch.setattr(policy_evaluator, "_get_step_registry", lambda: registry)

    doc = _doc_with_children(
        [SimpleNamespace(scenario=_scenario("S1", [_step("Then", 'explain "x"')]))]
    )
    violations = policy_evaluator.validate_policy_documents(ctx, [("p.feature", doc)])
    assert len(violations) == 1
    assert "orphan explain step" in violations[0].message


def test_evaluate_scenario_handles_missing_step_definition() -> None:
    ctx = _context()
    registry = _FakeRegistry({})
    steps = [_step("Given", "missing")]
    report = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S",
        steps=steps,
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert report.violation is not None
    assert "no matching step definition" in report.violation.message


def test_evaluate_scenario_skip_paths_and_pass_result() -> None:
    ctx = _context()
    registry = _FakeRegistry(
        {
            "given-skip": (StepOutcome.SKIP, None),
            "then-fail": (StepOutcome.FAIL, "bad"),
            "then-skip": (StepOutcome.SKIP, None),
            "then-pass": (StepOutcome.PASS, None),
        }
    )

    skipped = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S1",
        steps=[_step("Given", "given-skip")],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert skipped.result == policy_evaluator.ScenarioResult.SKIPPED

    has_violation = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S2",
        steps=[_step("Then", "then-fail"), _step("Then", "then-skip")],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert has_violation.violation is not None

    passed = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S3",
        steps=[_step("Then", "then-pass")],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert passed.result == policy_evaluator.ScenarioResult.PASSED
    assert passed.violation is None

    skip_then_no_violation = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S4",
        steps=[_step("Then", "then-skip"), _step("Then", "then-pass")],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert skip_then_no_violation.violation is None


def test_evaluate_scenario_guidance_and_explain_attachment() -> None:
    ctx = _context()
    registry = _FakeRegistry(
        {
            "warn": (StepOutcome.WARN, "warn-msg"),
            "suggest": (StepOutcome.SUGGEST, "suggest-msg"),
            "explain-guidance": (StepOutcome.EXPLAIN, "because"),
            "fail": (StepOutcome.FAIL, "failed"),
            "explain-violation": (StepOutcome.EXPLAIN, "explain-fail"),
            "pass": (StepOutcome.PASS, None),
        }
    )

    guidance_report = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S1",
        steps=[
            _step("Then", "warn"),
            _step("Then", "explain-guidance"),
            _step("Then", "suggest"),
        ],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert len(guidance_report.guidance_items) == 2
    assert guidance_report.guidance_items[0].explanations == ["because"]

    violation_report = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S2",
        steps=[
            _step("Then", "fail"),
            _step("Then", "explain-violation"),
            _step("Then", "pass"),
        ],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert violation_report.violation is not None
    assert violation_report.violation.explanations == ["explain-fail"]


def test_evaluate_scenario_explain_without_target_and_guidance_mode_fail_behavior() -> (
    None
):
    ctx = _context()
    registry = _FakeRegistry(
        {
            "orphan": (StepOutcome.EXPLAIN, "oops"),
            "fail": (StepOutcome.FAIL, "bad"),
            "explain": (StepOutcome.EXPLAIN, "drop-me"),
        }
    )

    orphan = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S1",
        steps=[_step("Then", "orphan")],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert orphan.violation is not None
    assert "orphan explain step" in orphan.violation.message

    guidance_mode = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=registry,
        policy_file="p.feature",
        scenario_name="S2",
        steps=[_step("Then", "fail"), _step("Then", "explain")],
        mode=policy_evaluator.PolicyEvaluationMode.GUIDANCE,
    )
    assert guidance_mode.violation is None

    double_fail = policy_evaluator.evaluate_scenario(
        context=ctx,
        registry=_FakeRegistry({"fail": (StepOutcome.FAIL, "bad")}),
        policy_file="p.feature",
        scenario_name="S3",
        steps=[_step("Then", "fail"), _step("Then", "fail")],
        mode=policy_evaluator.PolicyEvaluationMode.ENFORCEMENT,
    )
    assert double_fail.violation is not None


def test_evaluate_policies_report_and_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _context()

    doc = _doc_with_children(
        [
            SimpleNamespace(
                scenario=_scenario("S", [_step("Then", "x")]),
            )
        ]
    )

    reg = _FakeRegistry({"x": (StepOutcome.PASS, None)})
    monkeypatch.setattr(policy_evaluator, "_get_step_registry", lambda: reg)

    # Validation violations should short-circuit when collect_all is False.
    monkeypatch.setattr(
        policy_evaluator,
        "validate_policy_documents",
        lambda _ctx, _docs: [
            policy_evaluator._policy_structure_violation(
                context=ctx,
                policy_file="p.feature",
                scenario_name="S",
                failed_step="Then x",
                message="invalid",
            )
        ],
    )

    report = policy_evaluator.evaluate_policies_report(
        ctx,
        [("p.feature", doc)],
        policy_evaluator.PolicyEvaluationOptions(collect_all_violations=False),
    )
    assert len(report.violations) == 1

    # collect_all True should include scenario violation too.
    monkeypatch.setattr(
        policy_evaluator, "validate_policy_documents", lambda _ctx, _docs: []
    )
    monkeypatch.setattr(
        policy_evaluator,
        "evaluate_scenario",
        lambda **_kwargs: policy_evaluator.ScenarioEvaluationReport(
            result=policy_evaluator.ScenarioResult.PASSED,
            violation=policy_evaluator._policy_structure_violation(
                context=ctx,
                policy_file="p.feature",
                scenario_name="S",
                failed_step="Then y",
                message="boom",
            ),
            guidance_items=[],
        ),
    )

    report2 = policy_evaluator.evaluate_policies_report(
        ctx,
        [("p.feature", doc)],
        policy_evaluator.PolicyEvaluationOptions(collect_all_violations=True),
    )
    assert len(report2.violations) == 1

    with pytest.raises(Exception):
        policy_evaluator.evaluate_policies(ctx, [("p.feature", doc)])

    violations = policy_evaluator.evaluate_policies_with_options(
        ctx,
        [("p.feature", doc)],
        policy_evaluator.PolicyEvaluationOptions(collect_all_violations=True),
    )
    assert len(violations) == 1

    monkeypatch.setattr(
        policy_evaluator,
        "evaluate_scenario",
        lambda **_kwargs: policy_evaluator.ScenarioEvaluationReport(
            result=policy_evaluator.ScenarioResult.PASSED,
            violation=None,
            guidance_items=[],
        ),
    )
    report3 = policy_evaluator.evaluate_policies_report(
        ctx,
        [("p.feature", doc)],
        policy_evaluator.PolicyEvaluationOptions(collect_all_violations=True),
    )
    assert report3.violations == []
