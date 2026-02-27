//! Built-in policy step definitions.

use regex::Regex;

use crate::policy_context::PolicyContext;

/// Result of a step evaluation.
pub type StepResult = Result<StepOutcome, String>;

/// Outcome of evaluating a step.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StepOutcome {
    /// Step passed.
    Pass,
    /// Step should be skipped (Given/When didn't match).
    Skip,
}

/// Category of a step.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepCategory {
    Given,
    When,
    Then,
}

/// A single step definition with pattern and handler.
pub struct StepDefinition {
    /// Human-readable description of what this step does.
    pub description: String,
    /// Category (Given/When/Then).
    pub category: StepCategory,
    /// Human-readable usage pattern.
    pub usage_pattern: String,
    /// Regex pattern to match step text.
    pub pattern: Regex,
    /// Handler function that evaluates the step.
    pub handler: fn(&PolicyContext, &regex::Captures) -> StepResult,
}

impl StepDefinition {
    /// Create a new step definition.
    pub fn new(
        description: &str,
        category: StepCategory,
        usage_pattern: &str,
        pattern: &str,
        handler: fn(&PolicyContext, &regex::Captures) -> StepResult,
    ) -> Self {
        Self {
            description: description.to_string(),
            category,
            usage_pattern: usage_pattern.to_string(),
            pattern: Regex::new(pattern).expect("invalid step pattern regex"),
            handler,
        }
    }

    /// Check if this step matches the given text.
    pub fn matches<'a>(&self, text: &'a str) -> Option<regex::Captures<'a>> {
        self.pattern.captures(text)
    }

    /// Execute the step handler.
    pub fn execute(&self, context: &PolicyContext, captures: &regex::Captures) -> StepResult {
        (self.handler)(context, captures)
    }
}

/// Registry of all built-in step definitions.
pub struct StepRegistry {
    pub steps: Vec<StepDefinition>,
}

impl StepRegistry {
    /// Create a new registry with all built-in steps.
    pub fn new() -> Self {
        Self {
            steps: build_step_definitions(),
        }
    }

    /// Find a step definition matching the given text.
    pub fn find_step<'a>(&self, text: &'a str) -> Option<(&StepDefinition, regex::Captures<'a>)> {
        for step in &self.steps {
            if let Some(captures) = step.matches(text) {
                return Some((step, captures));
            }
        }
        None
    }
}

impl Default for StepRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Build the list of all built-in step definitions.
fn build_step_definitions() -> Vec<StepDefinition> {
    vec![
        // Given steps (preconditions/filters)
        StepDefinition::new(
            "Filter by issue type",
            StepCategory::Given,
            "the issue type is \"TYPE\"",
            r#"^the issue type is "([^"]+)"$"#,
            given_issue_type_is,
        ),
        StepDefinition::new(
            "Filter by label presence",
            StepCategory::Given,
            "the issue has label \"LABEL\"",
            r#"^the issue has label "([^"]+)"$"#,
            given_issue_has_label,
        ),
        StepDefinition::new(
            "Filter by parent presence",
            StepCategory::Given,
            "the issue has a parent",
            r"^the issue has a parent$",
            given_issue_has_parent,
        ),
        StepDefinition::new(
            "Filter by priority",
            StepCategory::Given,
            "the issue priority is N",
            r"^the issue priority is (\d+)$",
            given_issue_priority_is,
        ),
        StepDefinition::new(
            "Filter by custom field presence",
            StepCategory::Given,
            "the custom field \"FIELD\" is set",
            r#"^the custom field "([^"]+)" is set$"#,
            given_custom_field_is_set,
        ),
        // When steps (trigger conditions)
        StepDefinition::new(
            "Filter by transition target",
            StepCategory::When,
            "transitioning to \"STATUS\"",
            r#"^transitioning to "([^"]+)"$"#,
            when_transitioning_to,
        ),
        StepDefinition::new(
            "Filter by transition source",
            StepCategory::When,
            "transitioning from \"STATUS\"",
            r#"^transitioning from "([^"]+)"$"#,
            when_transitioning_from,
        ),
        StepDefinition::new(
            "Filter by specific transition",
            StepCategory::When,
            "transitioning from \"A\" to \"B\"",
            r#"^transitioning from "([^"]+)" to "([^"]+)"$"#,
            when_transitioning_from_to,
        ),
        StepDefinition::new(
            "Filter by create operation",
            StepCategory::When,
            "creating an issue",
            r"^creating an issue$",
            when_creating_issue,
        ),
        StepDefinition::new(
            "Filter by close operation",
            StepCategory::When,
            "closing an issue",
            r"^closing an issue$",
            when_closing_issue,
        ),
        // Then steps (assertions/policy rules)
        StepDefinition::new(
            "Assert field is set",
            StepCategory::Then,
            "the issue must have field \"FIELD\"",
            r#"^the issue must have field "([^"]+)"$"#,
            then_issue_must_have_field,
        ),
        StepDefinition::new(
            "Assert field is not set",
            StepCategory::Then,
            "the issue must not have field \"FIELD\"",
            r#"^the issue must not have field "([^"]+)"$"#,
            then_issue_must_not_have_field,
        ),
        StepDefinition::new(
            "Assert field equals value",
            StepCategory::Then,
            "the field \"FIELD\" must be \"VALUE\"",
            r#"^the field "([^"]+)" must be "([^"]+)"$"#,
            then_field_must_be,
        ),
        StepDefinition::new(
            "Assert all children have status",
            StepCategory::Then,
            "all child issues must have status \"STATUS\"",
            r#"^all child issues must have status "([^"]+)"$"#,
            then_all_children_must_have_status,
        ),
        StepDefinition::new(
            "Assert no children have status",
            StepCategory::Then,
            "no child issues may have status \"STATUS\"",
            r#"^no child issues may have status "([^"]+)"$"#,
            then_no_children_may_have_status,
        ),
        StepDefinition::new(
            "Assert parent has status",
            StepCategory::Then,
            "the parent issue must have status \"STATUS\"",
            r#"^the parent issue must have status "([^"]+)"$"#,
            then_parent_must_have_status,
        ),
        StepDefinition::new(
            "Assert minimum label count",
            StepCategory::Then,
            "the issue must have at least N labels",
            r"^the issue must have at least (\d+) labels?$",
            then_issue_must_have_at_least_n_labels,
        ),
        StepDefinition::new(
            "Assert has specific label",
            StepCategory::Then,
            "the issue must have label \"LABEL\"",
            r#"^the issue must have label "([^"]+)"$"#,
            then_issue_must_have_label,
        ),
        StepDefinition::new(
            "Assert description not empty",
            StepCategory::Then,
            "the description must not be empty",
            r"^the description must not be empty$",
            then_description_must_not_be_empty,
        ),
        StepDefinition::new(
            "Assert title matches pattern",
            StepCategory::Then,
            "the title must match pattern \"REGEX\"",
            r#"^the title must match pattern "([^"]+)"$"#,
            then_title_must_match_pattern,
        ),
        StepDefinition::new(
            "Assert custom field is set",
            StepCategory::Then,
            "the custom field \"FIELD\" must be set",
            r#"^the custom field "([^"]+)" must be set$"#,
            then_custom_field_must_be_set,
        ),
        StepDefinition::new(
            "Assert custom field equals value",
            StepCategory::Then,
            "the custom field \"FIELD\" must be \"VALUE\"",
            r#"^the custom field "([^"]+)" must be "([^"]+)"$"#,
            then_custom_field_must_be,
        ),
    ]
}

// Given step handlers

fn given_issue_type_is(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let expected_type = &captures[1];
    if context.issue().issue_type == expected_type {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn given_issue_has_label(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let label = &captures[1];
    if context.issue().labels.iter().any(|l| l == label) {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn given_issue_has_parent(context: &PolicyContext, _captures: &regex::Captures) -> StepResult {
    if context.issue().parent.is_some() {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn given_issue_priority_is(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let priority: i32 = captures[1].parse().map_err(|_| "invalid priority")?;
    if context.issue().priority == priority {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

// When step handlers

fn when_transitioning_to(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let status = &captures[1];
    if context.is_transitioning_to(status) {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn when_transitioning_from(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let status = &captures[1];
    if context.is_transitioning_from(status) {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn when_transitioning_from_to(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let from = &captures[1];
    let to = &captures[2];
    if context.is_transitioning_from(from) && context.is_transitioning_to(to) {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn when_creating_issue(context: &PolicyContext, _captures: &regex::Captures) -> StepResult {
    use crate::policy_context::PolicyOperation;
    if context.operation == PolicyOperation::Create {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn when_closing_issue(context: &PolicyContext, _captures: &regex::Captures) -> StepResult {
    use crate::policy_context::PolicyOperation;
    if context.operation == PolicyOperation::Close {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

// Then step handlers

fn then_issue_must_have_field(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let field = &captures[1];
    let issue = context.issue();

    let is_set = match field {
        "assignee" => issue.assignee.is_some(),
        "parent" => issue.parent.is_some(),
        "description" => !issue.description.trim().is_empty(),
        "title" => !issue.title.trim().is_empty(),
        "creator" => issue.creator.is_some(),
        _ => return Err(format!("unknown field: {field}")),
    };

    if is_set {
        Ok(StepOutcome::Pass)
    } else {
        Err(format!("issue does not have field \"{field}\" set"))
    }
}

fn then_issue_must_not_have_field(
    context: &PolicyContext,
    captures: &regex::Captures,
) -> StepResult {
    let field = &captures[1];
    let issue = context.issue();

    let is_set = match field {
        "assignee" => issue.assignee.is_some(),
        "parent" => issue.parent.is_some(),
        "creator" => issue.creator.is_some(),
        _ => return Err(format!("unknown field: {field}")),
    };

    if !is_set {
        Ok(StepOutcome::Pass)
    } else {
        Err(format!("issue has field \"{field}\" set but should not"))
    }
}

fn then_field_must_be(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let field = &captures[1];
    let expected_value = &captures[2];
    let issue = context.issue();

    let actual_value = match field {
        "status" => Some(&issue.status),
        "issue_type" | "type" => Some(&issue.issue_type),
        "assignee" => issue.assignee.as_ref(),
        "parent" => issue.parent.as_ref(),
        "creator" => issue.creator.as_ref(),
        _ => return Err(format!("unknown field: {field}")),
    };

    match actual_value {
        Some(value) if value == expected_value => Ok(StepOutcome::Pass),
        Some(value) => Err(format!(
            "field \"{field}\" is \"{value}\" but must be \"{expected_value}\""
        )),
        None => Err(format!("field \"{field}\" is not set")),
    }
}

fn then_all_children_must_have_status(
    context: &PolicyContext,
    captures: &regex::Captures,
) -> StepResult {
    let required_status = &captures[1];
    let children = context.child_issues();

    if children.is_empty() {
        return Ok(StepOutcome::Pass);
    }

    let non_matching: Vec<_> = children
        .iter()
        .filter(|child| child.status != required_status)
        .collect();

    if non_matching.is_empty() {
        Ok(StepOutcome::Pass)
    } else {
        let ids: Vec<_> = non_matching.iter().map(|c| c.identifier.as_str()).collect();
        Err(format!(
            "child issues {} do not have status \"{required_status}\"",
            ids.join(", ")
        ))
    }
}

fn then_no_children_may_have_status(
    context: &PolicyContext,
    captures: &regex::Captures,
) -> StepResult {
    let forbidden_status = &captures[1];
    let children = context.child_issues();

    let matching: Vec<_> = children
        .iter()
        .filter(|child| child.status == forbidden_status)
        .collect();

    if matching.is_empty() {
        Ok(StepOutcome::Pass)
    } else {
        let ids: Vec<_> = matching.iter().map(|c| c.identifier.as_str()).collect();
        Err(format!(
            "child issues {} have status \"{forbidden_status}\" but should not",
            ids.join(", ")
        ))
    }
}

fn then_parent_must_have_status(
    context: &PolicyContext,
    captures: &regex::Captures,
) -> StepResult {
    let required_status = &captures[1];

    match context.parent_issue() {
        Some(parent) if parent.status == required_status => Ok(StepOutcome::Pass),
        Some(parent) => Err(format!(
            "parent issue {} has status \"{}\" but must have status \"{required_status}\"",
            parent.identifier, parent.status
        )),
        None => Err("issue has no parent".to_string()),
    }
}

fn then_issue_must_have_at_least_n_labels(
    context: &PolicyContext,
    captures: &regex::Captures,
) -> StepResult {
    let min_count: usize = captures[1].parse().map_err(|_| "invalid label count")?;
    let actual_count = context.issue().labels.len();

    if actual_count >= min_count {
        Ok(StepOutcome::Pass)
    } else {
        Err(format!(
            "issue has {actual_count} label(s) but must have at least {min_count}"
        ))
    }
}

fn then_issue_must_have_label(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let required_label = &captures[1];
    if context.issue().labels.iter().any(|l| l == required_label) {
        Ok(StepOutcome::Pass)
    } else {
        Err(format!("issue does not have label \"{required_label}\""))
    }
}

fn then_description_must_not_be_empty(
    context: &PolicyContext,
    _captures: &regex::Captures,
) -> StepResult {
    if !context.issue().description.trim().is_empty() {
        Ok(StepOutcome::Pass)
    } else {
        Err("issue description is empty".to_string())
    }
}

fn then_title_must_match_pattern(
    context: &PolicyContext,
    captures: &regex::Captures,
) -> StepResult {
    let pattern_str = &captures[1];
    let pattern = Regex::new(pattern_str).map_err(|error| format!("invalid regex pattern: {error}"))?;

    if pattern.is_match(&context.issue().title) {
        Ok(StepOutcome::Pass)
    } else {
        Err(format!(
            "title \"{}\" does not match pattern \"{}\"",
            context.issue().title,
            pattern_str
        ))
    }
}

fn given_custom_field_is_set(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let field = &captures[1];
    if context.issue().custom.contains_key(field) {
        Ok(StepOutcome::Pass)
    } else {
        Ok(StepOutcome::Skip)
    }
}

fn then_custom_field_must_be_set(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let field = &captures[1];
    if context.issue().custom.contains_key(field) {
        Ok(StepOutcome::Pass)
    } else {
        Err(format!("custom field \"{field}\" is not set"))
    }
}

fn then_custom_field_must_be(context: &PolicyContext, captures: &regex::Captures) -> StepResult {
    let field = &captures[1];
    let expected = &captures[2];
    match context.issue().custom.get(field) {
        Some(value) => {
            let value_str = match value {
                serde_json::Value::String(s) => s.to_string(),
                v => v.to_string(),
            };
            if value_str == expected {
                Ok(StepOutcome::Pass)
            } else {
                Err(format!("custom field \"{field}\" is \"{value_str}\" but must be \"{expected}\""))
            }
        }
        None => Err(format!("custom field \"{field}\" is not set")),
    }
}
