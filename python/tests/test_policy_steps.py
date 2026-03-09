from __future__ import annotations

from kanbus.policy_context import PolicyContext, PolicyOperation, StatusTransition
from kanbus.policy_steps import (
    StepCategory,
    StepOutcome,
    StepRegistry,
    build_step_definitions,
    then_explain,
    then_suggest,
    then_warn,
)

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


def run_step(context: PolicyContext, text: str) -> tuple[StepOutcome, str | None]:
    found = StepRegistry().find_step(text)
    assert found is not None, f"step not found: {text}"
    step, match = found
    return step.execute(context, match)


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


def test_build_step_definitions_includes_all_categories() -> None:
    steps = build_step_definitions()
    categories = {step.category for step in steps}
    assert StepCategory.GIVEN in categories
    assert StepCategory.WHEN in categories
    assert StepCategory.THEN in categories
    assert len(steps) >= 30
    assert StepRegistry().find_step("this does not exist") is None


def test_given_filters_cover_matching_and_skipping_paths() -> None:
    context = build_context()
    assert run_step(context, 'the issue type is "task"') == (StepOutcome.PASS, None)
    assert run_step(context, 'the issue type is "bug"') == (StepOutcome.SKIP, None)
    assert run_step(context, 'the issue has label "security"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the issue has label "missing"') == (
        StepOutcome.SKIP,
        None,
    )
    assert run_step(context, "the issue has a parent") == (StepOutcome.PASS, None)
    assert run_step(context, "the issue priority is 2") == (StepOutcome.PASS, None)
    assert run_step(context, "the issue priority is 1") == (StepOutcome.SKIP, None)
    assert run_step(context, 'the issue status is "open"') == (StepOutcome.PASS, None)
    assert run_step(context, 'the issue status is "closed"') == (StepOutcome.SKIP, None)
    no_parent = build_context()
    no_parent.proposed_issue = no_parent.proposed_issue.model_copy(
        update={"parent": None}
    )
    assert run_step(no_parent, "the issue has a parent") == (StepOutcome.SKIP, None)


def test_when_filters_cover_operations_and_transition_paths() -> None:
    context = build_context()
    assert run_step(context, 'transitioning from "open"') == (StepOutcome.PASS, None)
    assert run_step(context, 'transitioning from "open" to "in_progress"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'transitioning from "closed" to "in_progress"') == (
        StepOutcome.SKIP,
        None,
    )
    assert run_step(context, 'transitioning from "closed"') == (StepOutcome.SKIP, None)
    assert run_step(context, 'transitioning to "closed"') == (StepOutcome.SKIP, None)
    assert run_step(context, "updating an issue") == (StepOutcome.PASS, None)
    assert run_step(context, "deleting an issue") == (StepOutcome.SKIP, None)
    assert run_step(context, "creating an issue") == (StepOutcome.SKIP, None)
    assert run_step(context, "closing an issue") == (StepOutcome.SKIP, None)

    transition_to_closed = build_context()
    transition_to_closed.transition = StatusTransition(
        from_status="in_progress", to_status="closed"
    )
    assert run_step(transition_to_closed, "closing an issue") == (
        StepOutcome.PASS,
        None,
    )

    create_context = build_context()
    create_context.operation = PolicyOperation.CREATE
    create_context.transition = None
    assert run_step(create_context, "creating an issue") == (StepOutcome.PASS, None)
    assert run_step(create_context, "closing an issue") == (StepOutcome.SKIP, None)

    close_context = build_context()
    close_context.operation = PolicyOperation.CLOSE
    close_context.transition = None
    assert run_step(close_context, "closing an issue") == (StepOutcome.PASS, None)
    assert run_step(close_context, "updating an issue") == (StepOutcome.SKIP, None)

    view_context = build_context()
    view_context.operation = PolicyOperation.VIEW
    assert run_step(view_context, "viewing an issue") == (StepOutcome.PASS, None)
    assert run_step(view_context, "listing issues") == (StepOutcome.SKIP, None)

    list_context = build_context()
    list_context.operation = PolicyOperation.LIST
    assert run_step(list_context, "listing issues") == (StepOutcome.PASS, None)
    assert run_step(list_context, "listing ready issues") == (StepOutcome.SKIP, None)

    ready_context = build_context()
    ready_context.operation = PolicyOperation.READY
    assert run_step(ready_context, "listing ready issues") == (StepOutcome.PASS, None)

    delete_context = build_context()
    delete_context.operation = PolicyOperation.DELETE
    assert run_step(delete_context, "deleting an issue") == (StepOutcome.PASS, None)

    non_view_context = build_context()
    assert run_step(non_view_context, "viewing an issue") == (StepOutcome.SKIP, None)


def test_then_field_assertions_cover_success_and_error_messages() -> None:
    context = build_context()
    assert run_step(context, 'the issue must have field "assignee"') == (
        StepOutcome.FAIL,
        'issue does not have field "assignee" set',
    )
    assert run_step(context, 'the issue must have field "title"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the issue must not have field "assignee"') == (
        StepOutcome.PASS,
        None,
    )
    fail_outcome, fail_message = run_step(
        context, 'the issue must not have field "parent"'
    )
    assert fail_outcome == StepOutcome.FAIL
    assert fail_message == 'issue has field "parent" set but should not'
    assert run_step(context, 'the issue must not have field "unknown"') == (
        StepOutcome.FAIL,
        "unknown field: unknown",
    )
    assert run_step(context, 'the field "status" must be "open"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the field "status" must be "closed"') == (
        StepOutcome.FAIL,
        'field "status" is "open" but must be "closed"',
    )
    assert run_step(context, 'the field "unknown" must be "x"') == (
        StepOutcome.FAIL,
        "unknown field: unknown",
    )
    assert run_step(context, 'the field "assignee" must be "alice"') == (
        StepOutcome.FAIL,
        'field "assignee" is not set',
    )


def test_then_child_parent_label_and_description_constraints() -> None:
    context = build_context()
    assert run_step(context, 'all child issues must have status "open"') == (
        StepOutcome.PASS,
        None,
    )
    child = build_issue(
        "kanbus-sub", title="Sub", parent="kanbus-child", status="in_progress"
    )
    other_child = build_issue(
        "kanbus-sub2", title="Sub2", parent="kanbus-child", status="open"
    )
    context.all_issues.extend([child, other_child])

    assert (
        run_step(context, 'all child issues must have status "open"')[0]
        == StepOutcome.FAIL
    )
    all_match = build_context()
    all_match_child = build_issue(
        "kanbus-sub-ok", title="Sub OK", parent="kanbus-child", status="open"
    )
    all_match.all_issues.append(all_match_child)
    assert run_step(all_match, 'all child issues must have status "open"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'no child issues may have status "closed"') == (
        StepOutcome.PASS,
        None,
    )
    assert (
        run_step(context, 'no child issues may have status "open"')[0]
        == StepOutcome.FAIL
    )
    assert run_step(context, "the issue must have at least 2 child issues") == (
        StepOutcome.PASS,
        None,
    )
    assert (
        run_step(context, "the issue must have at least 3 child issues")[0]
        == StepOutcome.FAIL
    )
    assert run_step(context, 'the parent issue must have status "open"') == (
        StepOutcome.PASS,
        None,
    )
    assert (
        run_step(context, 'the parent issue must have status "closed"')[0]
        == StepOutcome.FAIL
    )
    no_parent = build_context()
    no_parent.proposed_issue = no_parent.proposed_issue.model_copy(
        update={"parent": None}
    )
    assert run_step(no_parent, 'the parent issue must have status "open"') == (
        StepOutcome.FAIL,
        "issue has no parent",
    )
    assert run_step(context, "the issue must have at least 1 labels") == (
        StepOutcome.PASS,
        None,
    )
    assert (
        run_step(context, "the issue must have at least 2 labels")[0]
        == StepOutcome.FAIL
    )
    assert run_step(context, 'the issue must have label "security"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the issue must have label "backend"') == (
        StepOutcome.FAIL,
        'issue does not have label "backend"',
    )
    assert run_step(context, "the description must not be empty") == (
        StepOutcome.FAIL,
        "issue description is empty",
    )
    described = build_context()
    described.proposed_issue = described.proposed_issue.model_copy(
        update={"description": "filled"}
    )
    assert run_step(described, "the description must not be empty") == (
        StepOutcome.PASS,
        None,
    )


def test_then_title_pattern_and_custom_field_handlers() -> None:
    context = build_context()
    assert run_step(context, 'the title must match pattern "^Child$"') == (
        StepOutcome.PASS,
        None,
    )
    invalid_pattern = run_step(context, 'the title must match pattern "["')
    assert invalid_pattern[0] == StepOutcome.FAIL
    assert "invalid regex pattern" in (invalid_pattern[1] or "")
    assert run_step(context, 'the custom field "team" is set') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the custom field "missing" is set') == (
        StepOutcome.SKIP,
        None,
    )
    assert run_step(context, 'the custom field "team" must be set') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the custom field "missing" must be set') == (
        StepOutcome.FAIL,
        'custom field "missing" is not set',
    )
    assert run_step(context, 'the custom field "team" must be "platform"') == (
        StepOutcome.PASS,
        None,
    )
    assert run_step(context, 'the custom field "team" must be "infra"') == (
        StepOutcome.FAIL,
        'custom field "team" is "platform" but must be "infra"',
    )
    assert run_step(context, 'the custom field "missing" must be "v"') == (
        StepOutcome.FAIL,
        'custom field "missing" is not set',
    )
    title_miss = build_context()
    title_miss.proposed_issue = title_miss.proposed_issue.model_copy(
        update={"title": "Other"}
    )
    assert (
        run_step(title_miss, 'the title must match pattern "^Child$"')[0]
        == StepOutcome.FAIL
    )


def test_suggest_and_explain_handlers_are_callable() -> None:
    context = build_context()
    import re

    suggest_match = re.match(r'^suggest "([^"]*)"$', 'suggest "try this"')
    assert suggest_match is not None
    suggest_outcome, suggest_message = then_suggest(context, suggest_match)
    assert suggest_outcome == StepOutcome.SUGGEST
    assert suggest_message == "try this"

    explain_match = re.match(r'^explain "([^"]*)"$', 'explain "because details"')
    assert explain_match is not None
    explain_outcome, explain_message = then_explain(context, explain_match)
    assert explain_outcome == StepOutcome.EXPLAIN
    assert explain_message == "because details"
