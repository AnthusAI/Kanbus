"""Policy guidance hook execution and rendering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from kanbus.config_loader import ConfigurationError, load_project_configuration
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
from kanbus.project_context import ProjectContext


def guidance_is_enabled(no_guidance: bool = False) -> bool:
    """Return True when guidance emission is enabled."""
    if no_guidance:
        return False
    raw = os.environ.get("KANBUS_NO_GUIDANCE", "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class _LoadedGuidanceEnvironment:
    policy_documents: list
    project_configuration: object
    all_issues: list


def _load_guidance_environment(
    root: Path, context: ProjectContext | None
) -> Optional[_LoadedGuidanceEnvironment]:
    project_dir = (
        context.primary_project_directory()
        if context is not None
        else load_project_directory(root)
    )
    policies_dir = project_dir / "policies"
    if not policies_dir.is_dir():
        return None

    policy_documents = load_policies(policies_dir)
    if not policy_documents:
        return None

    if context is not None:
        configuration = context.configuration_for_project_directory(project_dir)
    else:
        configuration = load_project_configuration(get_configuration_path(project_dir))
    all_issues = load_issues_from_directory(project_dir / "issues")
    return _LoadedGuidanceEnvironment(
        policy_documents=policy_documents,
        project_configuration=configuration,
        all_issues=all_issues,
    )


def _evaluate_guidance_in_environment(
    environment: _LoadedGuidanceEnvironment,
    issue: IssueData,
    operation: PolicyOperation,
) -> PolicyEvaluationReport:
    context = PolicyContext(
        current_issue=issue,
        proposed_issue=issue,
        transition=None,
        operation=operation,
        project_configuration=environment.project_configuration,
        all_issues=environment.all_issues,
    )
    return evaluate_policies_report(
        context,
        environment.policy_documents,
        PolicyEvaluationOptions(
            collect_all_violations=True,
            mode=PolicyEvaluationMode.GUIDANCE,
        ),
    )


def collect_guidance_for_issue(
    root: Path,
    issue: IssueData,
    operation: PolicyOperation,
) -> PolicyEvaluationReport:
    """Evaluate policies in guidance mode for one issue."""
    environment = _load_guidance_environment(root, ProjectContext.discover(root))
    if environment is None:
        return PolicyEvaluationReport()
    return _evaluate_guidance_in_environment(environment, issue, operation)


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
    emit_guidance_for_issues_with_context(
        root,
        ProjectContext.discover(root),
        issues,
        operation,
        no_guidance=no_guidance,
    )


def emit_guidance_for_issues_with_context(
    root: Path,
    context: ProjectContext | None,
    issues: list[IssueData],
    operation: PolicyOperation,
    *,
    no_guidance: bool = False,
) -> None:
    """Run non-blocking guidance hooks using an already built project context.

    Configuration errors are raised; other guidance failures stay non-blocking.
    """
    if not guidance_is_enabled(no_guidance):
        return

    collected: list[GuidanceItem] = []
    try:
        environment = _load_guidance_environment(root, context)
    except ConfigurationError:
        raise
    except Exception:
        return
    if environment is None:
        return
    for issue in issues:
        try:
            report = _evaluate_guidance_in_environment(environment, issue, operation)
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
                        f"({violation.policy_file} / Rule: {violation.scenario}): {violation.message}"
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
