"""Policy evaluation engine with enforcement and guidance reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from kanbus.policy_context import (
    GuidanceItem,
    GuidanceSeverity,
    PolicyContext,
    PolicyEvaluationReport,
    PolicyViolationError,
)
from kanbus.policy_steps import StepOutcome, StepRegistry

if TYPE_CHECKING:
    from gherkin.ast import GherkinDocument, Step


class ScenarioResult(str, Enum):
    """Result of evaluating a scenario."""

    PASSED = "passed"
    SKIPPED = "skipped"


class PolicyEvaluationMode(str, Enum):
    """Policy evaluation mode."""

    ENFORCEMENT = "enforcement"
    GUIDANCE = "guidance"


_REGISTRY: StepRegistry | None = None


def _get_step_registry() -> StepRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = StepRegistry()
    return _REGISTRY


@dataclass
class PolicyEvaluationOptions:
    """Options for policy evaluation."""

    collect_all_violations: bool = False
    mode: PolicyEvaluationMode = PolicyEvaluationMode.ENFORCEMENT


@dataclass
class ScenarioEvaluationReport:
    """Detailed result of evaluating one scenario."""

    result: ScenarioResult
    violation: PolicyViolationError | None = None
    guidance_items: list[GuidanceItem] = field(default_factory=list)


def evaluate_policies(
    context: PolicyContext, documents: list[tuple[str, GherkinDocument]]
) -> None:
    """Evaluate all policies in enforcement mode.

    :param context: Policy evaluation context.
    :type context: PolicyContext
    :param documents: List of tuples containing filename and parsed Gherkin document.
    :type documents: list[tuple[str, GherkinDocument]]
    :raises PolicyViolationError: If any policy rule fails.
    """
    report = evaluate_policies_report(
        context,
        documents,
        PolicyEvaluationOptions(mode=PolicyEvaluationMode.ENFORCEMENT),
    )
    if report.violations:
        raise report.violations[0]


def evaluate_policies_with_options(
    context: PolicyContext,
    documents: list[tuple[str, GherkinDocument]],
    options: PolicyEvaluationOptions,
) -> list[PolicyViolationError]:
    """Backwards-compatible wrapper returning only violations."""
    return evaluate_policies_report(context, documents, options).violations


def evaluate_policies_report(
    context: PolicyContext,
    documents: list[tuple[str, GherkinDocument]],
    options: PolicyEvaluationOptions,
) -> PolicyEvaluationReport:
    """Evaluate policies and return violations and guidance items."""
    registry = _get_step_registry()
    report = PolicyEvaluationReport()

    validation_violations = validate_policy_documents(context, documents)
    if validation_violations:
        report.violations.extend(validation_violations)
        if not options.collect_all_violations:
            report.violations = report.violations[:1]
            return report

    for filename, document in documents:
        if not document.feature:
            continue

        for child in document.feature.children:
            if not hasattr(child, "scenario") or not child.scenario:
                continue

            scenario = child.scenario
            scenario_report = evaluate_scenario(
                context=context,
                registry=registry,
                policy_file=filename,
                scenario_name=scenario.name,
                steps=scenario.steps,
                mode=options.mode,
            )
            report.guidance_items.extend(scenario_report.guidance_items)

            if scenario_report.violation is None:
                continue

            report.violations.append(scenario_report.violation)
            if not options.collect_all_violations:
                return report

    return report


def validate_policy_documents(
    context: PolicyContext, documents: list[tuple[str, GherkinDocument]]
) -> list[PolicyViolationError]:
    """Validate policy structure that cannot be guaranteed by parsing alone."""
    violations: list[PolicyViolationError] = []
    registry = _get_step_registry()

    for filename, document in documents:
        if not document.feature:
            continue
        for child in document.feature.children:
            if not hasattr(child, "scenario") or not child.scenario:
                continue
            scenario = child.scenario
            for index, step in enumerate(scenario.steps):
                step_text = step.text.strip()
                step_keyword = step.keyword.strip()
                if registry.find_step(step_text) is None:
                    violations.append(
                        _policy_structure_violation(
                            context=context,
                            policy_file=filename,
                            scenario_name=scenario.name,
                            failed_step=f"{step_keyword} {step_text}",
                            message=f"no matching step definition for: {step_text}",
                        )
                    )
                    continue

                if not _is_explain_step(step_text):
                    continue

                if index == 0:
                    violations.append(
                        _policy_structure_violation(
                            context=context,
                            policy_file=filename,
                            scenario_name=scenario.name,
                            failed_step=f"{step_keyword} {step_text}",
                            message="orphan explain step: explain must follow an emitted error, warning, or suggestion",
                        )
                    )
                    continue

                previous = scenario.steps[index - 1]
                previous_text = previous.text.strip()
                previous_keyword = previous.keyword.strip()
                if previous_keyword != "Then" or _is_explain_step(previous_text):
                    violations.append(
                        _policy_structure_violation(
                            context=context,
                            policy_file=filename,
                            scenario_name=scenario.name,
                            failed_step=f"{step_keyword} {step_text}",
                            message="orphan explain step: explain must immediately follow a non-explain Then step",
                        )
                    )

    return violations


def _policy_structure_violation(
    *,
    context: PolicyContext,
    policy_file: str,
    scenario_name: str,
    failed_step: str,
    message: str,
) -> PolicyViolationError:
    return PolicyViolationError(
        policy_file=policy_file,
        scenario=scenario_name,
        failed_step=failed_step,
        message=message,
        issue_id=context.proposed_issue.identifier,
    )


def evaluate_scenario(
    context: PolicyContext,
    registry: StepRegistry,
    policy_file: str,
    scenario_name: str,
    steps: list[Step],
    mode: PolicyEvaluationMode,
) -> ScenarioEvaluationReport:
    """Evaluate a single scenario."""
    scenario_skipped = False
    guidance_items: list[GuidanceItem] = []

    pending_target: tuple[str, int] | None = None
    violation_step: str | None = None
    violation_message: str | None = None
    violation_explanations: list[str] = []

    for step in steps:
        step_text = step.text.strip()
        step_keyword = step.keyword.strip()

        found = registry.find_step(step_text)
        if not found:
            return ScenarioEvaluationReport(
                result=ScenarioResult.PASSED,
                violation=PolicyViolationError(
                    policy_file=policy_file,
                    scenario=scenario_name,
                    failed_step=f"{step_keyword} {step_text}",
                    message=f"no matching step definition for: {step_text}",
                    issue_id=context.proposed_issue.identifier,
                ),
                guidance_items=guidance_items,
            )

        step_def, match = found
        outcome, error_message = step_def.execute(context, match)

        if outcome == StepOutcome.PASS:
            if violation_step is not None and step_keyword == "Then":
                break
            pending_target = None
            continue

        if outcome == StepOutcome.SKIP:
            if step_keyword in ("Given", "When"):
                scenario_skipped = True
                break
            if violation_step is not None and step_keyword == "Then":
                break
            pending_target = None
            continue

        if outcome == StepOutcome.WARN:
            item = GuidanceItem(
                severity=GuidanceSeverity.WARNING,
                message=error_message or "",
                explanations=[],
                policy_file=policy_file,
                scenario=scenario_name,
                step=f"{step_keyword} {step_text}",
            )
            guidance_items.append(item)
            pending_target = ("guidance", len(guidance_items) - 1)
            continue

        if outcome == StepOutcome.SUGGEST:
            item = GuidanceItem(
                severity=GuidanceSeverity.SUGGESTION,
                message=error_message or "",
                explanations=[],
                policy_file=policy_file,
                scenario=scenario_name,
                step=f"{step_keyword} {step_text}",
            )
            guidance_items.append(item)
            pending_target = ("guidance", len(guidance_items) - 1)
            continue

        if outcome == StepOutcome.EXPLAIN:
            if pending_target is None:
                return ScenarioEvaluationReport(
                    result=ScenarioResult.PASSED,
                    violation=PolicyViolationError(
                        policy_file=policy_file,
                        scenario=scenario_name,
                        failed_step=f"{step_keyword} {step_text}",
                        message="orphan explain step: no previously emitted item to attach explanation",
                        issue_id=context.proposed_issue.identifier,
                    ),
                    guidance_items=guidance_items,
                )
            target_kind, target_index = pending_target
            if target_kind == "guidance":
                item = guidance_items[target_index]
                guidance_items[target_index] = GuidanceItem(
                    severity=item.severity,
                    message=item.message,
                    explanations=[*item.explanations, error_message or ""],
                    policy_file=item.policy_file,
                    scenario=item.scenario,
                    step=item.step,
                )
            elif target_kind == "violation":
                violation_explanations.append(error_message or "")
            # Transient target in guidance mode intentionally drops attached explanations.
            continue

        if outcome == StepOutcome.FAIL:
            if mode == PolicyEvaluationMode.GUIDANCE:
                pending_target = ("transient", 0)
                continue

            if violation_step is None:
                violation_step = f"{step_keyword} {step_text}"
                violation_message = error_message or "step failed without explanation"
                pending_target = ("violation", 0)
                continue

            break

    if scenario_skipped:
        return ScenarioEvaluationReport(result=ScenarioResult.SKIPPED)

    if violation_step is not None:
        return ScenarioEvaluationReport(
            result=ScenarioResult.PASSED,
            violation=PolicyViolationError(
                policy_file=policy_file,
                scenario=scenario_name,
                failed_step=violation_step,
                message=violation_message or "step failed without explanation",
                issue_id=context.proposed_issue.identifier,
                explanations=violation_explanations,
                guidance_items=guidance_items,
            ),
            guidance_items=guidance_items,
        )

    return ScenarioEvaluationReport(
        result=ScenarioResult.PASSED,
        guidance_items=guidance_items,
    )


def _is_explain_step(step_text: str) -> bool:
    return step_text.startswith('explain "') and step_text.endswith('"')
