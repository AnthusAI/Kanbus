"""Policy evaluation engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from kanbus.policy_context import PolicyContext, PolicyViolationError
from kanbus.policy_steps import StepOutcome, StepRegistry

if TYPE_CHECKING:
    from gherkin.ast import GherkinDocument, Step


class ScenarioResult(str, Enum):
    """Result of evaluating a scenario."""

    PASSED = "passed"
    SKIPPED = "skipped"


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


def evaluate_policies(
    context: PolicyContext, documents: list[tuple[str, GherkinDocument]]
) -> None:
    """Evaluate all policies against the given context.

    :param context: Policy evaluation context.
    :type context: PolicyContext
    :param documents: List of tuples containing filename and parsed Gherkin document.
    :type documents: list[tuple[str, GherkinDocument]]
    :raises PolicyViolationError: If any policy rule fails.
    """
    violations = evaluate_policies_with_options(
        context, documents, PolicyEvaluationOptions()
    )
    if violations:
        raise violations[0]


def evaluate_policies_with_options(
    context: PolicyContext,
    documents: list[tuple[str, GherkinDocument]],
    options: PolicyEvaluationOptions,
) -> list[PolicyViolationError]:
    """Evaluate all policies and optionally collect all violations.

    :param context: Policy evaluation context.
    :type context: PolicyContext
    :param documents: List of tuples containing filename and parsed Gherkin document.
    :type documents: list[tuple[str, GherkinDocument]]
    :param options: Evaluation options.
    :type options: PolicyEvaluationOptions
    :return: List of policy violations.
    :rtype: list[PolicyViolationError]
    """
    registry = _get_step_registry()
    violations = []

    for filename, document in documents:
        if not document.feature:
            continue

        for child in document.feature.children:
            if not hasattr(child, "scenario") or not child.scenario:
                continue

            scenario = child.scenario
            try:
                evaluate_scenario(
                    context, registry, filename, scenario.name, scenario.steps
                )
            except PolicyViolationError as error:
                violations.append(error)
                if not options.collect_all_violations:
                    return violations

    return violations


def evaluate_scenario(
    context: PolicyContext,
    registry: StepRegistry,
    policy_file: str,
    scenario_name: str,
    steps: list[Step],
) -> ScenarioResult:
    """Evaluate a single scenario.

    :param context: Policy evaluation context.
    :type context: PolicyContext
    :param registry: Step registry.
    :type registry: StepRegistry
    :param policy_file: Name of the policy file.
    :type policy_file: str
    :param scenario_name: Name of the scenario.
    :type scenario_name: str
    :param steps: List of steps in the scenario.
    :type steps: list[Step]
    :return: Scenario result.
    :rtype: ScenarioResult
    :raises PolicyViolationError: If any Then step fails.
    """
    scenario_skipped = False

    for step in steps:
        step_text = step.text.strip()
        step_keyword = step.keyword.strip()

        found = registry.find_step(step_text)
        if not found:
            raise PolicyViolationError(
                policy_file=policy_file,
                scenario=scenario_name,
                failed_step=f"{step_keyword} {step_text}",
                message=f"no matching step definition for: {step_text}",
                issue_id=context.proposed_issue.identifier,
            )

        step_def, match = found
        outcome, error_message = step_def.execute(context, match)

        if outcome == StepOutcome.PASS:
            continue

        if outcome == StepOutcome.FAIL:
            raise PolicyViolationError(
                policy_file=policy_file,
                scenario=scenario_name,
                failed_step=f"{step_keyword} {step_text}",
                message=error_message or "step failed without explanation",
                issue_id=context.proposed_issue.identifier,
            )

        if outcome == StepOutcome.SKIP:
            if step_keyword in ("Given", "When"):
                scenario_skipped = True
                break
            continue

    if scenario_skipped:
        return ScenarioResult.SKIPPED
    return ScenarioResult.PASSED
