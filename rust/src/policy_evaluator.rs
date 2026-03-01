//! Policy evaluation engine.

use gherkin::{Feature, Step, StepType};
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
        for scenario in &feature.scenarios {
            let scenario_report = evaluate_scenario(
                context,
                &STEP_REGISTRY,
                filename,
                &scenario.name,
                &scenario.steps,
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
        for scenario in &feature.scenarios {
            for (index, step) in scenario.steps.iter().enumerate() {
                let step_text = step.value.trim();
                let step_keyword = step_keyword(step.ty);
                if STEP_REGISTRY.find_step(step_text).is_none() {
                    violations.push(policy_violation(
                        filename,
                        &scenario.name,
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
                        &scenario.name,
                        &format!("{step_keyword} {step_text}"),
                        "orphan explain step: explain must follow an emitted error, warning, or suggestion",
                        &context.proposed_issue.identifier,
                        Vec::new(),
                        Vec::new(),
                    ));
                    continue;
                }

                let previous = &scenario.steps[index - 1];
                let previous_text = previous.value.trim();
                if !matches!(previous.ty, StepType::Then) || is_explain_step(previous_text) {
                    violations.push(policy_violation(
                        filename,
                        &scenario.name,
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
