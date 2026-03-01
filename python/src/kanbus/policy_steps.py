"""Built-in policy step definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from kanbus.policy_context import PolicyContext, PolicyOperation


class StepOutcome(str, Enum):
    """Outcome of evaluating a step."""

    PASS = "pass"
    SKIP = "skip"
    FAIL = "fail"
    WARN = "warn"
    SUGGEST = "suggest"
    EXPLAIN = "explain"


StepResult = tuple[StepOutcome, Optional[str]]


class StepCategory(str, Enum):
    """Category of a step."""

    GIVEN = "Given"
    WHEN = "When"
    THEN = "Then"


@dataclass
class StepDefinition:
    """A single step definition with pattern and handler.

    :param description: Human-readable description of what this step does.
    :type description: str
    :param category: Step category (Given/When/Then).
    :type category: StepCategory
    :param usage_pattern: Human-readable usage pattern.
    :type usage_pattern: str
    :param pattern: Regex pattern to match step text.
    :type pattern: re.Pattern
    :param handler: Handler function that evaluates the step.
    :type handler: Callable[[PolicyContext, re.Match], StepResult]
    """

    description: str
    category: StepCategory
    usage_pattern: str
    pattern: re.Pattern
    handler: Callable[[PolicyContext, re.Match], StepResult]

    def matches(self, text: str) -> Optional[re.Match]:
        """Check if this step matches the given text.

        :param text: Step text to match.
        :type text: str
        :return: Match object if pattern matches.
        :rtype: Optional[re.Match]
        """
        return self.pattern.match(text)

    def execute(self, context: PolicyContext, match: re.Match) -> StepResult:
        """Execute the step handler.

        :param context: Policy evaluation context.
        :type context: PolicyContext
        :param match: Regex match object with captured groups.
        :type match: re.Match
        :return: Step outcome and optional error message.
        :rtype: StepResult
        """
        return self.handler(context, match)


class StepRegistry:
    """Registry of all built-in step definitions."""

    def __init__(self) -> None:
        """Initialize registry with all built-in steps."""
        self.steps = build_step_definitions()

    def find_step(self, text: str) -> Optional[tuple[StepDefinition, re.Match]]:
        """Find a step definition matching the given text.

        :param text: Step text to match.
        :type text: str
        :return: Tuple of step definition and match object if found.
        :rtype: Optional[tuple[StepDefinition, re.Match]]
        """
        for step in self.steps:
            match = step.matches(text)
            if match:
                return (step, match)
        return None


def build_step_definitions() -> list[StepDefinition]:
    """Build the list of all built-in step definitions.

    :return: List of step definitions.
    :rtype: list[StepDefinition]
    """
    return [
        StepDefinition(
            "Filter by issue type",
            StepCategory.GIVEN,
            'the issue type is "TYPE"',
            re.compile(r'^the issue type is "([^"]+)"$'),
            given_issue_type_is,
        ),
        StepDefinition(
            "Filter by label presence",
            StepCategory.GIVEN,
            'the issue has label "LABEL"',
            re.compile(r'^the issue has label "([^"]+)"$'),
            given_issue_has_label,
        ),
        StepDefinition(
            "Filter by parent presence",
            StepCategory.GIVEN,
            "the issue has a parent",
            re.compile(r"^the issue has a parent$"),
            given_issue_has_parent,
        ),
        StepDefinition(
            "Filter by priority",
            StepCategory.GIVEN,
            "the issue priority is N",
            re.compile(r"^the issue priority is (\d+)$"),
            given_issue_priority_is,
        ),
        StepDefinition(
            "Filter by transition target",
            StepCategory.WHEN,
            'transitioning to "STATUS"',
            re.compile(r'^transitioning to "([^"]+)"$'),
            when_transitioning_to,
        ),
        StepDefinition(
            "Filter by transition source",
            StepCategory.WHEN,
            'transitioning from "STATUS"',
            re.compile(r'^transitioning from "([^"]+)"$'),
            when_transitioning_from,
        ),
        StepDefinition(
            "Filter by specific transition",
            StepCategory.WHEN,
            'transitioning from "A" to "B"',
            re.compile(r'^transitioning from "([^"]+)" to "([^"]+)"$'),
            when_transitioning_from_to,
        ),
        StepDefinition(
            "Filter by create operation",
            StepCategory.WHEN,
            "creating an issue",
            re.compile(r"^creating an issue$"),
            when_creating_issue,
        ),
        StepDefinition(
            "Filter by close operation",
            StepCategory.WHEN,
            "closing an issue",
            re.compile(r"^closing an issue$"),
            when_closing_issue,
        ),
        StepDefinition(
            "Filter by update operation",
            StepCategory.WHEN,
            "updating an issue",
            re.compile(r"^updating an issue$"),
            when_updating_issue,
        ),
        StepDefinition(
            "Filter by delete operation",
            StepCategory.WHEN,
            "deleting an issue",
            re.compile(r"^deleting an issue$"),
            when_deleting_issue,
        ),
        StepDefinition(
            "Filter by view operation",
            StepCategory.WHEN,
            "viewing an issue",
            re.compile(r"^viewing an issue$"),
            when_viewing_issue,
        ),
        StepDefinition(
            "Filter by list operation",
            StepCategory.WHEN,
            "listing issues",
            re.compile(r"^listing issues$"),
            when_listing_issues,
        ),
        StepDefinition(
            "Filter by ready-list operation",
            StepCategory.WHEN,
            "listing ready issues",
            re.compile(r"^listing ready issues$"),
            when_listing_ready_issues,
        ),
        StepDefinition(
            "Assert field is set",
            StepCategory.THEN,
            'the issue must have field "FIELD"',
            re.compile(r'^the issue must have field "([^"]+)"$'),
            then_issue_must_have_field,
        ),
        StepDefinition(
            "Assert field is not set",
            StepCategory.THEN,
            'the issue must not have field "FIELD"',
            re.compile(r'^the issue must not have field "([^"]+)"$'),
            then_issue_must_not_have_field,
        ),
        StepDefinition(
            "Assert field equals value",
            StepCategory.THEN,
            'the field "FIELD" must be "VALUE"',
            re.compile(r'^the field "([^"]+)" must be "([^"]+)"$'),
            then_field_must_be,
        ),
        StepDefinition(
            "Assert all children have status",
            StepCategory.THEN,
            'all child issues must have status "STATUS"',
            re.compile(r'^all child issues must have status "([^"]+)"$'),
            then_all_children_must_have_status,
        ),
        StepDefinition(
            "Assert no children have status",
            StepCategory.THEN,
            'no child issues may have status "STATUS"',
            re.compile(r'^no child issues may have status "([^"]+)"$'),
            then_no_children_may_have_status,
        ),
        StepDefinition(
            "Assert minimum child count",
            StepCategory.THEN,
            "the issue must have at least N child issues",
            re.compile(r"^the issue must have at least (\d+) child issues?$"),
            then_issue_must_have_at_least_n_child_issues,
        ),
        StepDefinition(
            "Assert parent has status",
            StepCategory.THEN,
            'the parent issue must have status "STATUS"',
            re.compile(r'^the parent issue must have status "([^"]+)"$'),
            then_parent_must_have_status,
        ),
        StepDefinition(
            "Assert minimum label count",
            StepCategory.THEN,
            "the issue must have at least N labels",
            re.compile(r"^the issue must have at least (\d+) labels?$"),
            then_issue_must_have_at_least_n_labels,
        ),
        StepDefinition(
            "Assert has specific label",
            StepCategory.THEN,
            'the issue must have label "LABEL"',
            re.compile(r'^the issue must have label "([^"]+)"$'),
            then_issue_must_have_label,
        ),
        StepDefinition(
            "Assert description not empty",
            StepCategory.THEN,
            "the description must not be empty",
            re.compile(r"^the description must not be empty$"),
            then_description_must_not_be_empty,
        ),
        StepDefinition(
            "Assert title matches pattern",
            StepCategory.THEN,
            'the title must match pattern "REGEX"',
            re.compile(r'^the title must match pattern "([^"]+)"$'),
            then_title_must_match_pattern,
        ),
        StepDefinition(
            "Filter by custom field presence",
            StepCategory.GIVEN,
            'the custom field "FIELD" is set',
            re.compile(r'^the custom field "([^"]+)" is set$'),
            given_custom_field_is_set,
        ),
        StepDefinition(
            "Assert custom field is set",
            StepCategory.THEN,
            'the custom field "FIELD" must be set',
            re.compile(r'^the custom field "([^"]+)" must be set$'),
            then_custom_field_must_be_set,
        ),
        StepDefinition(
            "Assert custom field equals value",
            StepCategory.THEN,
            'the custom field "FIELD" must be "VALUE"',
            re.compile(r'^the custom field "([^"]+)" must be "([^"]+)"$'),
            then_custom_field_must_be,
        ),
        StepDefinition(
            "Emit warning guidance",
            StepCategory.THEN,
            'warn "TEXT"',
            re.compile(r'^warn "([^"]*)"$'),
            then_warn,
        ),
        StepDefinition(
            "Emit suggestion guidance",
            StepCategory.THEN,
            'suggest "TEXT"',
            re.compile(r'^suggest "([^"]*)"$'),
            then_suggest,
        ),
        StepDefinition(
            "Attach explanation to previous item",
            StepCategory.THEN,
            'explain "TEXT"',
            re.compile(r'^explain "([^"]*)"$'),
            then_explain,
        ),
    ]


def given_issue_type_is(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by issue type."""
    expected_type = match.group(1)
    if context.issue.issue_type == expected_type:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def given_issue_has_label(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by label presence."""
    label = match.group(1)
    if label in context.issue.labels:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def given_issue_has_parent(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by parent presence."""
    if context.issue.parent:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def given_issue_priority_is(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by priority."""
    priority = int(match.group(1))
    if context.issue.priority == priority:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_transitioning_to(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by transition target."""
    status = match.group(1)
    if context.is_transitioning_to(status):
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_transitioning_from(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by transition source."""
    status = match.group(1)
    if context.is_transitioning_from(status):
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_transitioning_from_to(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by specific transition."""
    from_status = match.group(1)
    to_status = match.group(2)
    if context.is_transitioning_from(from_status) and context.is_transitioning_to(
        to_status
    ):
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_creating_issue(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by create operation."""
    if context.operation == PolicyOperation.CREATE:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_closing_issue(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by close operation."""
    if context.operation == PolicyOperation.CLOSE or (
        context.operation == PolicyOperation.UPDATE
        and context.is_transitioning_to("closed")
    ):
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_updating_issue(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by update operation."""
    if context.operation == PolicyOperation.UPDATE:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_deleting_issue(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by delete operation."""
    if context.operation == PolicyOperation.DELETE:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_viewing_issue(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by view operation."""
    if context.operation == PolicyOperation.VIEW:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_listing_issues(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by list operation."""
    if context.operation == PolicyOperation.LIST:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def when_listing_ready_issues(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by ready-list operation."""
    if context.operation == PolicyOperation.READY:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def then_issue_must_have_field(context: PolicyContext, match: re.Match) -> StepResult:
    """Assert field is set."""
    field = match.group(1)
    issue = context.issue

    field_map = {
        "assignee": issue.assignee is not None,
        "parent": issue.parent is not None,
        "description": bool(issue.description.strip()),
        "title": bool(issue.title.strip()),
        "creator": issue.creator is not None,
    }

    if field not in field_map:
        return (StepOutcome.FAIL, f"unknown field: {field}")

    if field_map[field]:
        return (StepOutcome.PASS, None)
    return (StepOutcome.FAIL, f'issue does not have field "{field}" set')


def then_issue_must_not_have_field(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert field is not set."""
    field = match.group(1)
    issue = context.issue

    field_map = {
        "assignee": issue.assignee is not None,
        "parent": issue.parent is not None,
        "creator": issue.creator is not None,
    }

    if field not in field_map:
        return (StepOutcome.FAIL, f"unknown field: {field}")

    if not field_map[field]:
        return (StepOutcome.PASS, None)
    return (StepOutcome.FAIL, f'issue has field "{field}" set but should not')


def then_field_must_be(context: PolicyContext, match: re.Match) -> StepResult:
    """Assert field equals value."""
    field = match.group(1)
    expected_value = match.group(2)
    issue = context.issue

    field_map = {
        "status": issue.status,
        "issue_type": issue.issue_type,
        "type": issue.issue_type,
        "assignee": issue.assignee,
        "parent": issue.parent,
        "creator": issue.creator,
    }

    if field not in field_map:
        return (StepOutcome.FAIL, f"unknown field: {field}")

    actual_value = field_map[field]
    if actual_value == expected_value:
        return (StepOutcome.PASS, None)
    if actual_value is None:
        return (StepOutcome.FAIL, f'field "{field}" is not set')
    return (
        StepOutcome.FAIL,
        f'field "{field}" is "{actual_value}" but must be "{expected_value}"',
    )


def then_all_children_must_have_status(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert all children have status."""
    required_status = match.group(1)
    children = context.child_issues()

    if not children:
        return (StepOutcome.PASS, None)

    non_matching = [c for c in children if c.status != required_status]

    if not non_matching:
        return (StepOutcome.PASS, None)

    ids = ", ".join(c.identifier for c in non_matching)
    return (
        StepOutcome.FAIL,
        f'child issues {ids} do not have status "{required_status}"',
    )


def then_no_children_may_have_status(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert no children have status."""
    forbidden_status = match.group(1)
    children = context.child_issues()

    matching = [c for c in children if c.status == forbidden_status]

    if not matching:
        return (StepOutcome.PASS, None)

    ids = ", ".join(c.identifier for c in matching)
    return (
        StepOutcome.FAIL,
        f'child issues {ids} have status "{forbidden_status}" but should not',
    )


def then_issue_must_have_at_least_n_child_issues(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert minimum child issue count."""
    min_count = int(match.group(1))
    actual_count = len(context.child_issues())
    if actual_count >= min_count:
        return (StepOutcome.PASS, None)
    return (
        StepOutcome.FAIL,
        f"issue has {actual_count} child issue(s) but must have at least {min_count}",
    )


def then_parent_must_have_status(context: PolicyContext, match: re.Match) -> StepResult:
    """Assert parent has status."""
    required_status = match.group(1)
    parent = context.parent_issue()

    if parent is None:
        return (StepOutcome.FAIL, "issue has no parent")

    if parent.status == required_status:
        return (StepOutcome.PASS, None)

    return (
        StepOutcome.FAIL,
        f'parent issue {parent.identifier} has status "{parent.status}" '
        f'but must have status "{required_status}"',
    )


def then_issue_must_have_at_least_n_labels(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert minimum label count."""
    min_count = int(match.group(1))
    actual_count = len(context.issue.labels)

    if actual_count >= min_count:
        return (StepOutcome.PASS, None)

    return (
        StepOutcome.FAIL,
        f"issue has {actual_count} label(s) but must have at least {min_count}",
    )


def then_issue_must_have_label(context: PolicyContext, match: re.Match) -> StepResult:
    """Assert has specific label."""
    required_label = match.group(1)
    if required_label in context.issue.labels:
        return (StepOutcome.PASS, None)
    return (StepOutcome.FAIL, f'issue does not have label "{required_label}"')


def then_description_must_not_be_empty(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert description not empty."""
    if context.issue.description.strip():
        return (StepOutcome.PASS, None)
    return (StepOutcome.FAIL, "issue description is empty")


def then_title_must_match_pattern(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert title matches pattern."""
    pattern_str = match.group(1)
    try:
        pattern = re.compile(pattern_str)
    except re.error as error:
        return (StepOutcome.FAIL, f"invalid regex pattern: {error}")

    if pattern.search(context.issue.title):
        return (StepOutcome.PASS, None)

    return (
        StepOutcome.FAIL,
        f'title "{context.issue.title}" does not match pattern "{pattern_str}"',
    )


def given_custom_field_is_set(context: PolicyContext, match: re.Match) -> StepResult:
    """Filter by custom field presence."""
    field = match.group(1)
    if field in context.issue.custom:
        return (StepOutcome.PASS, None)
    return (StepOutcome.SKIP, None)


def then_custom_field_must_be_set(
    context: PolicyContext, match: re.Match
) -> StepResult:
    """Assert custom field is set."""
    field = match.group(1)
    if field in context.issue.custom:
        return (StepOutcome.PASS, None)
    return (StepOutcome.FAIL, f'custom field "{field}" is not set')


def then_custom_field_must_be(context: PolicyContext, match: re.Match) -> StepResult:
    """Assert custom field equals value."""
    field = match.group(1)
    expected_value = match.group(2)

    if field not in context.issue.custom:
        return (StepOutcome.FAIL, f'custom field "{field}" is not set')

    actual_value = str(context.issue.custom[field])
    if actual_value == expected_value:
        return (StepOutcome.PASS, None)

    return (
        StepOutcome.FAIL,
        f'custom field "{field}" is "{actual_value}" but must be "{expected_value}"',
    )


def then_warn(context: PolicyContext, match: re.Match) -> StepResult:
    """Emit non-blocking warning guidance."""
    return (StepOutcome.WARN, match.group(1))


def then_suggest(context: PolicyContext, match: re.Match) -> StepResult:
    """Emit non-blocking suggestion guidance."""
    return (StepOutcome.SUGGEST, match.group(1))


def then_explain(context: PolicyContext, match: re.Match) -> StepResult:
    """Attach explanation text to the previously emitted item."""
    return (StepOutcome.EXPLAIN, match.group(1))
