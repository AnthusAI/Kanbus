from __future__ import annotations

from kanbus.policy_context import (
    GuidanceItem,
    GuidanceSeverity,
    PolicyContext,
    PolicyEvaluationReport,
    PolicyOperation,
    PolicyViolationError,
    StatusTransition,
)

from test_helpers import build_issue, build_project_configuration


def build_context() -> PolicyContext:
    parent = build_issue("kanbus-parent", status="open")
    issue = build_issue("kanbus-child", parent="kanbus-parent", status="in_progress")
    sibling = build_issue("kanbus-sibling")
    child = build_issue("kanbus-sub", parent="kanbus-child")
    return PolicyContext(
        current_issue=issue,
        proposed_issue=issue,
        transition=StatusTransition(from_status="open", to_status="in_progress"),
        operation=PolicyOperation.UPDATE,
        project_configuration=build_project_configuration(),
        all_issues=[parent, issue, sibling, child],
    )


def test_policy_context_transition_and_lookup_helpers() -> None:
    context = build_context()
    assert context.issue.identifier == "kanbus-child"
    assert context.is_transition() is True
    assert context.is_transitioning_to("in_progress") is True
    assert context.is_transitioning_from("open") is True
    assert context.is_transitioning_to("closed") is False
    assert context.is_transitioning_from("closed") is False
    assert [issue.identifier for issue in context.child_issues()] == ["kanbus-sub"]
    assert context.parent_issue() is not None
    assert context.parent_issue().identifier == "kanbus-parent"  # type: ignore[union-attr]


def test_policy_context_parent_issue_handles_missing_parent() -> None:
    context = build_context()
    context.proposed_issue = context.proposed_issue.model_copy(update={"parent": None})
    assert context.parent_issue() is None

    context.proposed_issue = context.proposed_issue.model_copy(update={"parent": "nope"})
    assert context.parent_issue() is None

    context.transition = None
    assert context.is_transition() is False
    assert context.is_transitioning_to("in_progress") is False
    assert context.is_transitioning_from("open") is False


def test_policy_violation_error_formats_explanations_and_sorted_guidance() -> None:
    guidance_items = [
        GuidanceItem(
            severity=GuidanceSeverity.SUGGESTION,
            message="later suggestion",
            explanations=["suggest detail"],
            policy_file="b.policy",
            scenario="B",
            step='suggest "later"',
        ),
        GuidanceItem(
            severity=GuidanceSeverity.WARNING,
            message="first warning",
            explanations=["warn detail"],
            policy_file="a.policy",
            scenario="A",
            step='warn "first"',
        ),
    ]

    error = PolicyViolationError(
        policy_file="root.policy",
        scenario="Create rule",
        failed_step='Then the issue must have field "title"',
        message="title is required",
        issue_id="kanbus-1",
        explanations=["because policy"],
        guidance_items=guidance_items,
    )
    text = str(error)
    assert "policy violation in root.policy for issue kanbus-1" in text
    assert "Explanation: because policy" in text
    # warnings should sort ahead of suggestions
    assert text.index("GUIDANCE WARNING: first warning") < text.index(
        "GUIDANCE SUGGESTION: later suggestion"
    )
    assert "Explanation: warn detail" in text
    assert "Explanation: suggest detail" in text


def test_policy_evaluation_report_defaults_are_empty() -> None:
    report = PolicyEvaluationReport()
    assert report.violations == []
    assert report.guidance_items == []
