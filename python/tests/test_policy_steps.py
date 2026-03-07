from __future__ import annotations

from kanbus.policy_context import PolicyContext, PolicyOperation, StatusTransition
from kanbus.policy_steps import StepOutcome, StepRegistry, then_warn

from test_helpers import build_issue, build_project_configuration


def build_context() -> PolicyContext:
    parent = build_issue("kanbus-parent", title="Parent", status="open")
    issue = build_issue(
        "kanbus-child",
        title="Child",
        parent="kanbus-parent",
        labels=["security"],
        custom={"team": "platform"},
    )
    sibling = build_issue("kanbus-sibling", title="Sibling")
    configuration = build_project_configuration()
    return PolicyContext(
        current_issue=issue,
        proposed_issue=issue,
        transition=StatusTransition(from_status="open", to_status="in_progress"),
        operation=PolicyOperation.UPDATE,
        project_configuration=configuration,
        all_issues=[parent, issue, sibling],
    )


def test_registry_finds_and_executes_matcher() -> None:
    context = build_context()
    registry = StepRegistry()

    found = registry.find_step('the issue must have label "security"')

    assert found is not None
    step, match = found
    outcome, message = step.execute(context, match)
    assert outcome == StepOutcome.PASS
    assert message is None


def test_field_assertion_reports_unknown_field() -> None:
    context = build_context()
    registry = StepRegistry()
    found = registry.find_step('the issue must have field "unknown"')
    assert found is not None
    step, match = found

    outcome, message = step.execute(context, match)

    assert outcome == StepOutcome.FAIL
    assert message == "unknown field: unknown"


def test_transition_steps_respect_context_transition() -> None:
    context = build_context()
    registry = StepRegistry()
    found = registry.find_step('transitioning to "in_progress"')
    assert found is not None
    step, match = found

    outcome, message = step.execute(context, match)

    assert outcome == StepOutcome.PASS
    assert message is None


def test_custom_field_step_fails_when_missing_value() -> None:
    context = build_context()
    registry = StepRegistry()
    found = registry.find_step('the custom field "team" must be "infra"')
    assert found is not None
    step, match = found

    outcome, message = step.execute(context, match)

    assert outcome == StepOutcome.FAIL
    assert 'custom field "team" is "platform" but must be "infra"' == message


def test_warn_step_emits_warning_outcome() -> None:
    context = build_context()
    registry = StepRegistry()
    found = registry.find_step('warn "fix me"')
    assert found is not None
    step, match = found

    outcome, message = step.execute(context, match)

    assert outcome == StepOutcome.WARN
    assert message == "fix me"


def test_then_warn_handler_is_directly_callable() -> None:
    context = build_context()
    import re

    match = re.match(r'^warn "([^"]*)"$', 'warn "heads up"')
    assert match is not None

    outcome, message = then_warn(context, match)

    assert outcome == StepOutcome.WARN
    assert message == "heads up"
