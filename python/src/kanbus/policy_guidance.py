"""Policy guidance hook execution and rendering."""

from __future__ import annotations

import os
from pathlib import Path

import click

from kanbus.config_loader import load_project_configuration
from kanbus.issue_listing import load_issues_from_directory
from kanbus.models import IssueData
from kanbus.policy_context import (
    GuidanceItem,
    GuidanceSeverity,
    PolicyContext,
    PolicyEvaluationReport,
    PolicyOperation,
)
from kanbus.policy_evaluator import (
    PolicyEvaluationMode,
    PolicyEvaluationOptions,
    evaluate_policies_report,
)
from kanbus.policy_loader import load_policies
from kanbus.project import get_configuration_path, load_project_directory


def guidance_is_enabled(no_guidance: bool = False) -> bool:
    """Return True when guidance emission is enabled."""
    if no_guidance:
        return False
    raw = os.environ.get("KANBUS_NO_GUIDANCE", "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


def collect_guidance_for_issue(
    root: Path,
    issue: IssueData,
    operation: PolicyOperation,
) -> PolicyEvaluationReport:
    """Evaluate policies in guidance mode for one issue."""
    project_dir = load_project_directory(root)
    policies_dir = project_dir / "policies"
    if not policies_dir.is_dir():
        return PolicyEvaluationReport()

    policy_documents = load_policies(policies_dir)
    if not policy_documents:
        return PolicyEvaluationReport()

    configuration = load_project_configuration(get_configuration_path(project_dir))
    issues_dir = project_dir / "issues"
    all_issues = load_issues_from_directory(issues_dir)

    context = PolicyContext(
        current_issue=issue,
        proposed_issue=issue,
        transition=None,
        operation=operation,
        project_configuration=configuration,
        all_issues=all_issues,
    )

    return evaluate_policies_report(
        context,
        policy_documents,
        PolicyEvaluationOptions(
            collect_all_violations=True,
            mode=PolicyEvaluationMode.GUIDANCE,
        ),
    )


def emit_guidance_for_issues(
    root: Path,
    issues: list[IssueData],
    operation: PolicyOperation,
    *,
    no_guidance: bool = False,
) -> None:
    """Run non-blocking guidance hooks and emit results on stderr."""
    if not guidance_is_enabled(no_guidance):
        return

    collected: list[GuidanceItem] = []
    for issue in issues:
        try:
            report = collect_guidance_for_issue(root, issue, operation)
        except Exception:
            # Guidance must never block successful command paths.
            continue

        collected.extend(report.guidance_items)
        for violation in report.violations:
            collected.append(
                GuidanceItem(
                    severity=GuidanceSeverity.WARNING,
                    message=(
                        "Guidance policy error "
                        f"({violation.policy_file} / {violation.scenario}): {violation.message}"
                    ),
                    explanations=[
                        'Explanation: Run "kbs policy validate" to fix this policy definition.'
                    ],
                    policy_file=violation.policy_file,
                    scenario=violation.scenario,
                    step=violation.failed_step,
                )
            )

    for item in sorted_deduped_guidance_items(collected):
        prefix = (
            "GUIDANCE WARNING"
            if item.severity == GuidanceSeverity.WARNING
            else "GUIDANCE SUGGESTION"
        )
        click.echo(f"{prefix}: {item.message}", err=True)
        for explanation in item.explanations:
            if explanation.startswith("Explanation:"):
                click.echo(f"  {explanation}", err=True)
            else:
                click.echo(f"  Explanation: {explanation}", err=True)


def sorted_deduped_guidance_items(items: list[GuidanceItem]) -> list[GuidanceItem]:
    seen: set[tuple[str, str, tuple[str, ...], str, str, str]] = set()
    unique: list[GuidanceItem] = []
    for item in items:
        key = (
            item.severity.value,
            item.message,
            tuple(item.explanations),
            item.policy_file,
            item.scenario,
            item.step,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return sorted(
        unique,
        key=lambda item: (
            0 if item.severity == GuidanceSeverity.WARNING else 1,
            item.policy_file,
            item.scenario,
            item.step,
            item.message,
        ),
    )
