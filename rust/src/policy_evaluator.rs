//! Policy evaluation engine.

use gherkin::{Feature, Step, StepType};
use std::sync::LazyLock;

use crate::error::KanbusError;
use crate::policy_context::PolicyContext;
use crate::policy_steps::{StepOutcome, StepRegistry};

pub static STEP_REGISTRY: LazyLock<StepRegistry> = LazyLock::new(StepRegistry::new);

/// Options for policy evaluation.
#[derive(Debug, Clone, Default)]
pub struct PolicyEvaluationOptions {
    /// If true, collect all violations instead of stopping at the first one.
    pub collect_all_violations: bool,
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
    evaluate_policies_with_options(context, features, &PolicyEvaluationOptions::default())
        .map(|_| ())
        .map_err(|mut errs| errs.remove(0))
}

/// Evaluate all policies and optionally collect all violations.
pub fn evaluate_policies_with_options(
    context: &PolicyContext,
    features: &[(String, Feature)],
    options: &PolicyEvaluationOptions,
) -> Result<Vec<()>, Vec<KanbusError>> {
    let mut violations = Vec::new();

    for (filename, feature) in features {
        for scenario in &feature.scenarios {
            match evaluate_scenario(
                context,
                &STEP_REGISTRY,
                filename,
                &scenario.name,
                &scenario.steps,
            ) {
                Ok(ScenarioResult::Passed) | Ok(ScenarioResult::Skipped) => continue,
                Err(err) => {
                    violations.push(err);
                    if !options.collect_all_violations {
                        return Err(violations);
                    }
                }
            }
        }
    }

    if violations.is_empty() {
        Ok(vec![])
    } else {
        Err(violations)
    }
}

#[derive(Debug, PartialEq, Eq)]
enum ScenarioResult {
    Passed,
    Skipped,
}

fn evaluate_scenario(
    context: &PolicyContext,
    registry: &StepRegistry,
    policy_file: &str,
    scenario_name: &str,
    steps: &[Step],
) -> Result<ScenarioResult, KanbusError> {
    let mut scenario_skipped = false;

    for step in steps {
        let step_text = step.value.trim();
        let step_keyword = match step.ty {
            StepType::Given => "Given",
            StepType::When => "When",
            StepType::Then => "Then",
        };

        let (step_def, captures) = match registry.find_step(step_text) {
            Some(found) => found,
            None => {
                return Err(KanbusError::PolicyViolation {
                    policy_file: policy_file.to_string(),
                    scenario: scenario_name.to_string(),
                    failed_step: format!("{step_keyword} {step_text}"),
                    message: format!("no matching step definition for: {step_text}"),
                    issue_id: context.proposed_issue.identifier.clone(),
                });
            }
        };

        match step_def.execute(context, &captures) {
            Ok(StepOutcome::Pass) => {
                continue;
            }
            Ok(StepOutcome::Skip) => {
                if matches!(step.ty, StepType::Given | StepType::When) {
                    scenario_skipped = true;
                    break;
                }
                continue;
            }
            Err(message) => {
                if scenario_skipped {
                    continue;
                }
                return Err(KanbusError::PolicyViolation {
                    policy_file: policy_file.to_string(),
                    scenario: scenario_name.to_string(),
                    failed_step: format!("{step_keyword} {step_text}"),
                    message,
                    issue_id: context.proposed_issue.identifier.clone(),
                });
            }
        }
    }

    if scenario_skipped {
        Ok(ScenarioResult::Skipped)
    } else {
        Ok(ScenarioResult::Passed)
    }
}
