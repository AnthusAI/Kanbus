//! Policy evaluation engine.

use gherkin::{Feature, Step, StepType};

use crate::error::KanbusError;
use crate::policy_context::PolicyContext;
use crate::policy_steps::{StepOutcome, StepRegistry};

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
    let registry = StepRegistry::new();

    for (filename, feature) in features {
        for scenario in &feature.scenarios {
            let result = evaluate_scenario(
                context,
                &registry,
                filename,
                &scenario.name,
                &scenario.steps,
            )?;

            if result == ScenarioResult::Skipped {
                continue;
            }
        }
    }

    Ok(())
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
