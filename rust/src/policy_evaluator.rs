//! Policy evaluation engine.

use gherkin::{Feature, Step, StepType};
use std::borrow::Cow;
use std::collections::HashSet;
use std::sync::LazyLock;

use crate::error::KanbusError;
use crate::error::PolicyViolationDetails;
use crate::policy_context::PolicyContext;
use crate::policy_steps::{StepOutcome, StepRegistry};

pub static STEP_REGISTRY: LazyLock<StepRegistry> = LazyLock::new(StepRegistry::new);

/// Guidance severity level.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum GuidanceSeverity {
    Warning,
    Suggestion,
}

/// A single guidance item emitted during policy evaluation.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct GuidanceItem {
    pub severity: GuidanceSeverity,
    pub message: String,
    pub explanations: Vec<String>,
    pub policy_file: String,
    pub scenario: String,
    pub step: String,
}

/// Combined policy evaluation output.
#[derive(Debug, Default)]
pub struct PolicyEvaluationReport {
    pub violations: Vec<KanbusError>,
    pub guidance_items: Vec<GuidanceItem>,
}

/// Policy evaluation mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PolicyEvaluationMode {
    /// Enforce violations as blockers.
    #[default]
    Enforcement,
    /// Collect non-blocking guidance only.
    Guidance,
}

/// Options for policy evaluation.
#[derive(Debug, Clone, Default)]
pub struct PolicyEvaluationOptions {
    /// If true, collect all violations instead of stopping at the first one.
    pub collect_all_violations: bool,
    /// Evaluation mode.
    pub mode: PolicyEvaluationMode,
}

/// Evaluate all policies against the given context.
///
/// # Arguments
/// * `context` - Policy evaluation context.
/// * `features` - List of parsed policy features with their filenames.
///
/// # Returns
/// Ok if all policies pass, Err with PolicyViolation if any policy fails.
///
/// # Errors
/// Returns `KanbusError::PolicyViolation` if any policy rule fails.
pub fn evaluate_policies(
    context: &PolicyContext,
    features: &[(String, Feature)],
) -> Result<(), KanbusError> {
    let report = evaluate_policies_report(
        context,
        features,
        &PolicyEvaluationOptions {
            collect_all_violations: false,
            mode: PolicyEvaluationMode::Enforcement,
        },
    );
    if report.violations.is_empty() {
        Ok(())
    } else {
        let mut violations = report.violations;
        Err(violations.remove(0))
    }
}

/// Evaluate all policies and optionally collect all violations.
pub fn evaluate_policies_with_options(
    context: &PolicyContext,
    features: &[(String, Feature)],
    options: &PolicyEvaluationOptions,
) -> Result<Vec<()>, Vec<KanbusError>> {
    let report = evaluate_policies_report(context, features, options);
    if report.violations.is_empty() {
        Ok(vec![])
    } else {
        Err(report.violations)
    }
}

/// Evaluate policies and return both violations and guidance items.
pub fn evaluate_policies_report(
    context: &PolicyContext,
    features: &[(String, Feature)],
    options: &PolicyEvaluationOptions,
) -> PolicyEvaluationReport {
    let mut report = PolicyEvaluationReport::default();

    let validation = validate_policy_documents(context, features);
    if !validation.is_empty() {
        report.violations.extend(validation);
        if !options.collect_all_violations {
            report.violations.truncate(1);
            return report;
        }
    }

    for (filename, feature) in features {
        for (rule_name, steps) in iter_policy_units(feature) {
            let scenario_report = evaluate_scenario(
                context,
                &STEP_REGISTRY,
                filename,
                rule_name.as_ref(),
                steps,
                options.mode,
            );

            report
                .guidance_items
                .extend(scenario_report.guidance_items.clone());

            if let Some(violation) = scenario_report.violation {
                report.violations.push(violation);
                if !options.collect_all_violations {
                    return report;
                }
            }
        }
    }

    report
}

/// Validate policy structure without running policy assertions.
pub fn validate_policy_documents(
    context: &PolicyContext,
    features: &[(String, Feature)],
) -> Vec<KanbusError> {
    let mut violations = Vec::new();

    for (filename, feature) in features {
        for (rule_name, steps) in iter_policy_units(feature) {
            for (index, step) in steps.iter().enumerate() {
                let step_text = step.value.trim();
                let step_keyword = step_keyword(step.ty);
                if STEP_REGISTRY.find_step(step_text).is_none() {
                    violations.push(policy_violation(
                        filename,
                        rule_name.as_ref(),
                        &format!("{step_keyword} {step_text}"),
                        &format!("no matching step definition for: {step_text}"),
                        &context.proposed_issue.identifier,
                        Vec::new(),
                        Vec::new(),
                    ));
                    continue;
                }

                if !is_explain_step(step_text) {
                    continue;
                }

                if index == 0 {
                    violations.push(policy_violation(
                        filename,
                        rule_name.as_ref(),
                        &format!("{step_keyword} {step_text}"),
                        "orphan explain step: explain must follow an emitted error, warning, or suggestion",
                        &context.proposed_issue.identifier,
                        Vec::new(),
                        Vec::new(),
                    ));
                    continue;
                }

                let previous = &steps[index - 1];
                let previous_text = previous.value.trim();
                if !matches!(previous.ty, StepType::Then) || is_explain_step(previous_text) {
                    violations.push(policy_violation(
                        filename,
                        rule_name.as_ref(),
                        &format!("{step_keyword} {step_text}"),
                        "orphan explain step: explain must immediately follow a non-explain Then step",
                        &context.proposed_issue.identifier,
                        Vec::new(),
                        Vec::new(),
                    ));
                }
            }
        }
    }

    violations
}

fn iter_policy_units(feature: &Feature) -> impl Iterator<Item = (Cow<'_, str>, &[Step])> {
    let top = feature.scenarios.iter().map(|scenario| {
        (
            Cow::Borrowed(scenario.name.as_str()),
            scenario.steps.as_slice(),
        )
    });
    let nested = feature.rules.iter().flat_map(|rule| {
        rule.scenarios.iter().map(move |scenario| {
            (
                Cow::Owned(format!("{} / {}", rule.name, scenario.name)),
                scenario.steps.as_slice(),
            )
        })
    });
    top.chain(nested)
}

#[derive(Debug)]
struct ScenarioEvaluationReport {
    violation: Option<KanbusError>,
    guidance_items: Vec<GuidanceItem>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PendingTarget {
    Guidance(usize),
    Violation,
    Transient,
}

fn evaluate_scenario(
    context: &PolicyContext,
    registry: &StepRegistry,
    policy_file: &str,
    scenario_name: &str,
    steps: &[Step],
    mode: PolicyEvaluationMode,
) -> ScenarioEvaluationReport {
    let mut scenario_skipped = false;
    let mut guidance_items: Vec<GuidanceItem> = Vec::new();

    let mut pending_target: Option<PendingTarget> = None;
    let mut violation_step: Option<String> = None;
    let mut violation_message: Option<String> = None;
    let mut violation_explanations: Vec<String> = Vec::new();

    for step in steps {
        let step_text = step.value.trim();
        let step_keyword = step_keyword(step.ty);

        let (step_def, captures) = match registry.find_step(step_text) {
            Some(found) => found,
            None => {
                return ScenarioEvaluationReport {
                    violation: Some(policy_violation(
                        policy_file,
                        scenario_name,
                        &format!("{step_keyword} {step_text}"),
                        &format!("no matching step definition for: {step_text}"),
                        &context.proposed_issue.identifier,
                        Vec::new(),
                        guidance_items,
                    )),
                    guidance_items: Vec::new(),
                };
            }
        };

        match step_def.execute(context, &captures) {
            Ok(StepOutcome::Pass) => {
                if violation_step.is_some() && matches!(step.ty, StepType::Then) {
                    break;
                }
                pending_target = None;
            }
            Ok(StepOutcome::Skip) => {
                if matches!(step.ty, StepType::Given | StepType::When) {
                    scenario_skipped = true;
                    break;
                }
                if violation_step.is_some() && matches!(step.ty, StepType::Then) {
                    break;
                }
                pending_target = None;
            }
            Ok(StepOutcome::Warn(message)) => {
                guidance_items.push(GuidanceItem {
                    severity: GuidanceSeverity::Warning,
                    message,
                    explanations: Vec::new(),
                    policy_file: policy_file.to_string(),
                    scenario: scenario_name.to_string(),
                    step: format!("{step_keyword} {step_text}"),
                });
                pending_target = Some(PendingTarget::Guidance(guidance_items.len() - 1));
            }
            Ok(StepOutcome::Suggest(message)) => {
                guidance_items.push(GuidanceItem {
                    severity: GuidanceSeverity::Suggestion,
                    message,
                    explanations: Vec::new(),
                    policy_file: policy_file.to_string(),
                    scenario: scenario_name.to_string(),
                    step: format!("{step_keyword} {step_text}"),
                });
                pending_target = Some(PendingTarget::Guidance(guidance_items.len() - 1));
            }
            Ok(StepOutcome::Explain(message)) => {
                let Some(target) = pending_target else {
                    return ScenarioEvaluationReport {
                        violation: Some(policy_violation(
                            policy_file,
                            scenario_name,
                            &format!("{step_keyword} {step_text}"),
                            "orphan explain step: no previously emitted item to attach explanation",
                            &context.proposed_issue.identifier,
                            Vec::new(),
                            guidance_items,
                        )),
                        guidance_items: Vec::new(),
                    };
                };
                match target {
                    PendingTarget::Guidance(index) => {
                        if let Some(item) = guidance_items.get_mut(index) {
                            item.explanations.push(message);
                        }
                    }
                    PendingTarget::Violation => violation_explanations.push(message),
                    PendingTarget::Transient => {
                        // Guidance mode allows explain after failing assertions without emitting errors.
                    }
                }
            }
            Err(message) => {
                if mode == PolicyEvaluationMode::Guidance {
                    pending_target = Some(PendingTarget::Transient);
                    continue;
                }
                if violation_step.is_none() {
                    violation_step = Some(format!("{step_keyword} {step_text}"));
                    violation_message = Some(message);
                    pending_target = Some(PendingTarget::Violation);
                    continue;
                }
                break;
            }
        }
    }

    if scenario_skipped {
        return ScenarioEvaluationReport {
            violation: None,
            guidance_items: Vec::new(),
        };
    }

    if let Some(failed_step) = violation_step {
        return ScenarioEvaluationReport {
            violation: Some(policy_violation(
                policy_file,
                scenario_name,
                &failed_step,
                &violation_message.unwrap_or_else(|| "step failed without explanation".to_string()),
                &context.proposed_issue.identifier,
                violation_explanations,
                guidance_items,
            )),
            guidance_items: Vec::new(),
        };
    }

    ScenarioEvaluationReport {
        violation: None,
        guidance_items,
    }
}

fn step_keyword(step_type: StepType) -> &'static str {
    match step_type {
        StepType::Given => "Given",
        StepType::When => "When",
        StepType::Then => "Then",
    }
}

fn is_explain_step(step_text: &str) -> bool {
    step_text.starts_with("explain \"") && step_text.ends_with('"')
}

fn policy_violation(
    policy_file: &str,
    scenario: &str,
    failed_step: &str,
    message: &str,
    issue_id: &str,
    explanations: Vec<String>,
    guidance_items: Vec<GuidanceItem>,
) -> KanbusError {
    let guidance_sorted = dedupe_and_sort_guidance(&guidance_items);
    let guidance_lines = guidance_sorted
        .iter()
        .flat_map(|item| {
            let mut lines = vec![format!(
                "{}: {}",
                if item.severity == GuidanceSeverity::Warning {
                    "GUIDANCE WARNING"
                } else {
                    "GUIDANCE SUGGESTION"
                },
                item.message
            )];
            for explanation in &item.explanations {
                lines.push(format!("Explanation: {explanation}"));
            }
            lines
        })
        .collect();

    KanbusError::PolicyViolation {
        policy_file: policy_file.to_string().into_boxed_str(),
        scenario: scenario.to_string().into_boxed_str(),
        failed_step: failed_step.to_string().into_boxed_str(),
        message: message.to_string().into_boxed_str(),
        issue_id: issue_id.to_string().into_boxed_str(),
        details: Box::new(PolicyViolationDetails {
            explanations,
            guidance: guidance_lines,
        }),
    }
}

fn dedupe_and_sort_guidance(items: &[GuidanceItem]) -> Vec<GuidanceItem> {
    let mut seen: HashSet<GuidanceItem> = HashSet::new();
    let mut unique: Vec<GuidanceItem> = Vec::new();
    for item in items {
        if seen.insert(item.clone()) {
            unique.push(item.clone());
        }
    }

    unique.sort_by(|left, right| {
        let left_rank = if left.severity == GuidanceSeverity::Warning {
            0
        } else {
            1
        };
        let right_rank = if right.severity == GuidanceSeverity::Warning {
            0
        } else {
            1
        };
        left_rank
            .cmp(&right_rank)
            .then_with(|| left.policy_file.cmp(&right.policy_file))
            .then_with(|| left.scenario.cmp(&right.scenario))
            .then_with(|| left.step.cmp(&right.step))
            .then_with(|| left.message.cmp(&right.message))
    });

    unique
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{IssueData, PriorityDefinition, ProjectConfiguration, StatusDefinition};
    use crate::policy_context::{PolicyContext, PolicyOperation};
    use chrono::Utc;
    use gherkin::GherkinEnv;
    use std::collections::BTreeMap;

    fn warning(message: &str) -> GuidanceItem {
        GuidanceItem {
            severity: GuidanceSeverity::Warning,
            message: message.to_string(),
            explanations: Vec::new(),
            policy_file: "policy-a.feature".to_string(),
            scenario: "scenario-a".to_string(),
            step: "Then warn".to_string(),
        }
    }

    fn suggestion(message: &str) -> GuidanceItem {
        GuidanceItem {
            severity: GuidanceSeverity::Suggestion,
            message: message.to_string(),
            explanations: Vec::new(),
            policy_file: "policy-b.feature".to_string(),
            scenario: "scenario-b".to_string(),
            step: "Then suggest".to_string(),
        }
    }

    fn parse_feature(feature_text: &str) -> Feature {
        let temp_dir = tempfile::tempdir().expect("tempdir");
        let path = temp_dir.path().join("policy.policy");
        std::fs::write(&path, feature_text).expect("write feature");
        Feature::parse_path(&path, GherkinEnv::default()).expect("parse feature")
    }

    fn sample_context() -> PolicyContext {
        let now = Utc::now();
        let issue = IssueData {
            identifier: "kanbus-1".to_string(),
            title: "Issue".to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now,
            updated_at: now,
            closed_at: None,
            custom: BTreeMap::new(),
        };
        let mut workflows = BTreeMap::new();
        workflows.insert("default".to_string(), BTreeMap::new());
        let mut priorities = BTreeMap::new();
        priorities.insert(
            2u8,
            PriorityDefinition {
                name: "medium".to_string(),
                color: None,
            },
        );
        let config = ProjectConfiguration {
            project_directory: "project".to_string(),
            virtual_projects: BTreeMap::new(),
            new_issue_project: None,
            ignore_paths: Vec::new(),
            console_port: None,
            project_key: "kanbus".to_string(),
            project_management_template: None,
            hierarchy: vec!["task".to_string()],
            types: vec!["task".to_string()],
            workflows,
            transition_labels: BTreeMap::new(),
            initial_status: "open".to_string(),
            priorities,
            default_priority: 2,
            assignee: None,
            time_zone: None,
            statuses: vec![StatusDefinition {
                key: "open".to_string(),
                name: "Open".to_string(),
                category: "todo".to_string(),
                color: None,
                collapsed: false,
            }],
            categories: Vec::new(),
            sort_order: BTreeMap::new(),
            type_colors: BTreeMap::new(),
            beads_compatibility: false,
            wiki_directory: None,
            ai: None,
            jira: None,
            snyk: None,
            realtime: Default::default(),
            overlay: Default::default(),
            hooks: Default::default(),
        };
        PolicyContext {
            current_issue: None,
            proposed_issue: issue.clone(),
            transition: None,
            operation: PolicyOperation::Update,
            project_configuration: config,
            all_issues: vec![issue],
        }
    }

    #[test]
    fn explain_step_detection_is_exact() {
        assert!(is_explain_step("explain \"reason\""));
        assert!(!is_explain_step("explain reason"));
        assert!(!is_explain_step("warn \"reason\""));
    }

    #[test]
    fn dedupe_and_sort_guidance_keeps_warning_before_suggestion() {
        let duplicate_warning = warning("use required labels");
        let items = vec![
            suggestion("consider adding ownership"),
            duplicate_warning.clone(),
            duplicate_warning,
        ];

        let deduped = dedupe_and_sort_guidance(&items);

        assert_eq!(deduped.len(), 2);
        assert_eq!(deduped[0].severity, GuidanceSeverity::Warning);
        assert_eq!(deduped[1].severity, GuidanceSeverity::Suggestion);
    }

    #[test]
    fn step_keyword_maps_step_types() {
        assert_eq!(step_keyword(StepType::Given), "Given");
        assert_eq!(step_keyword(StepType::When), "When");
        assert_eq!(step_keyword(StepType::Then), "Then");
    }

    #[test]
    fn validate_policy_documents_flags_unknown_and_orphan_explain_steps() {
        let context = sample_context();
        let feature = parse_feature(
            r#"
Feature: Validation checks
  Scenario: Unknown step fails
    Given this step does not exist

  Scenario: Explain cannot be first
    Then explain "orphan explanation"
"#,
        );

        let violations =
            validate_policy_documents(&context, &[("policy.policy".to_string(), feature)]);
        assert_eq!(violations.len(), 2);
        let rendered = violations
            .into_iter()
            .map(|error| error.to_string())
            .collect::<Vec<_>>()
            .join("\n");
        assert!(rendered.contains("no matching step definition"));
        assert!(rendered.contains("orphan explain step"));
    }

    #[test]
    fn evaluate_policies_with_collect_all_returns_all_failures() {
        let context = sample_context();
        let feature = parse_feature(
            r#"
Feature: Multiple failures
  Scenario: First failure
    Then the issue must have field "assignee"

  Scenario: Second failure
    Then the issue must have label "security"
"#,
        );
        let options = PolicyEvaluationOptions {
            collect_all_violations: true,
            mode: PolicyEvaluationMode::Enforcement,
        };

        let result = evaluate_policies_with_options(
            &context,
            &[("policy.policy".to_string(), feature)],
            &options,
        );
        match result {
            Err(errors) => {
                assert!(errors.len() >= 2);
                let rendered = errors
                    .into_iter()
                    .map(|error| error.to_string())
                    .collect::<Vec<_>>()
                    .join("\n");
                assert!(rendered.contains("assignee"));
                assert!(rendered.contains("security"));
            }
            Ok(_) => panic!("expected violations"),
        }
    }

    #[test]
    fn guidance_mode_allows_failed_assertion_with_following_explain() {
        let context = sample_context();
        let feature = parse_feature(
            r#"
Feature: Guidance transient handling
  Scenario: Failed assertion then explain
    Then the issue must have field "assignee"
    Then explain "Assignee is optional during triage."
"#,
        );
        let steps = feature.scenarios[0].steps.as_slice();
        let scenario = evaluate_scenario(
            &context,
            &STEP_REGISTRY,
            "policy.policy",
            "Failed assertion then explain",
            steps,
            PolicyEvaluationMode::Guidance,
        );
        assert!(scenario.violation.is_none());
        assert!(scenario.guidance_items.is_empty());
    }

    #[test]
    fn validation_reports_rule_prefixed_scenario_name_for_nested_rules() {
        let context = sample_context();
        let feature = parse_feature(
            r#"
Feature: Rule naming
  Rule: Assignment checks
    Scenario: Missing step mapping
      Given this nested step is unknown
"#,
        );

        let violations =
            validate_policy_documents(&context, &[("policy.policy".to_string(), feature)]);
        assert_eq!(violations.len(), 1);
        let rendered = violations[0].to_string();
        assert!(rendered.contains("Assignment checks / Missing step mapping"));
    }
}
