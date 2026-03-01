//! Policy guidance hook execution and rendering.

use std::collections::HashSet;
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_listing::load_issues_from_directory;
use crate::models::IssueData;
use crate::policy_context::{PolicyContext, PolicyOperation};
use crate::policy_evaluator::{
    evaluate_policies_report, GuidanceItem, GuidanceSeverity, PolicyEvaluationMode,
    PolicyEvaluationOptions, PolicyEvaluationReport,
};
use crate::policy_loader::load_policies;
use crate::project::load_project_directory;
use crate::rich_text_signals::emit_stderr_line;

/// Return true if guidance hooks are enabled.
pub fn guidance_enabled(no_guidance: bool) -> bool {
    if no_guidance {
        return false;
    }
    let raw = std::env::var("KANBUS_NO_GUIDANCE")
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    !matches!(raw.as_str(), "1" | "true" | "yes" | "on")
}

/// Evaluate guidance for a single issue and operation.
pub fn collect_guidance_for_issue(
    root: &Path,
    issue: &IssueData,
    operation: PolicyOperation,
) -> Result<PolicyEvaluationReport, KanbusError> {
    let project_dir = load_project_directory(root)?;
    let policies_dir = project_dir.join("policies");
    if !policies_dir.is_dir() {
        return Ok(PolicyEvaluationReport::default());
    }

    let policy_documents = load_policies(&policies_dir)?;
    if policy_documents.is_empty() {
        return Ok(PolicyEvaluationReport::default());
    }

    let config_path = get_configuration_path(&project_dir)?;
    let configuration = load_project_configuration(&config_path)?;
    let issues_dir = project_dir.join("issues");
    let all_issues = load_issues_from_directory(&issues_dir)?;

    let context = PolicyContext {
        current_issue: Some(issue.clone()),
        proposed_issue: issue.clone(),
        transition: None,
        operation,
        project_configuration: configuration,
        all_issues,
    };

    Ok(evaluate_policies_report(
        &context,
        &policy_documents,
        &PolicyEvaluationOptions {
            collect_all_violations: true,
            mode: PolicyEvaluationMode::Guidance,
        },
    ))
}

/// Run non-blocking guidance hooks and emit results to stderr.
pub fn emit_guidance_for_issues(
    root: &Path,
    issues: &[IssueData],
    operation: PolicyOperation,
    no_guidance: bool,
) {
    if !guidance_enabled(no_guidance) || issues.is_empty() {
        return;
    }

    let mut collected: Vec<GuidanceItem> = Vec::new();
    for issue in issues {
        let report = match collect_guidance_for_issue(root, issue, operation.clone()) {
            Ok(report) => report,
            Err(_) => continue,
        };

        collected.extend(report.guidance_items);
        for violation in report.violations {
            match violation {
                KanbusError::PolicyViolation {
                    policy_file,
                    scenario,
                    message,
                    failed_step,
                    ..
                } => {
                    let policy_file: String = policy_file.into();
                    let scenario: String = scenario.into();
                    let message: String = message.into();
                    let failed_step: String = failed_step.into();
                    collected.push(GuidanceItem {
                        severity: GuidanceSeverity::Warning,
                        message: format!(
                            "Guidance policy error ({policy_file} / {scenario}): {message}"
                        ),
                        explanations: vec![
                            "Run \"kbs policy validate\" to fix this policy definition."
                                .to_string(),
                        ],
                        policy_file,
                        scenario,
                        step: failed_step,
                    });
                }
                _ => {
                    collected.push(GuidanceItem {
                        severity: GuidanceSeverity::Warning,
                        message: violation.to_string(),
                        explanations: vec![
                            "Run \"kbs policy validate\" to fix this policy definition."
                                .to_string(),
                        ],
                        policy_file: "unknown".to_string(),
                        scenario: "unknown".to_string(),
                        step: "unknown".to_string(),
                    });
                }
            }
        }
    }

    for item in sorted_deduped_guidance_items(&collected) {
        let prefix = if item.severity == GuidanceSeverity::Warning {
            "GUIDANCE WARNING"
        } else {
            "GUIDANCE SUGGESTION"
        };
        emit_stderr_line(&format!("{prefix}: {}", item.message));
        for explanation in item.explanations {
            emit_stderr_line(&format!("  Explanation: {explanation}"));
        }
    }
}

/// Sort and de-duplicate guidance items with warnings first.
pub fn sorted_deduped_guidance_items(items: &[GuidanceItem]) -> Vec<GuidanceItem> {
    let mut seen: HashSet<GuidanceItem> = HashSet::new();
    let mut unique = Vec::new();
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
