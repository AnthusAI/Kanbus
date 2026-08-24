//! Batch lifecycle compaction helpers.

use std::path::Path;

use chrono::Utc;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_listing::load_issues_from_directory;
use crate::models::IssueData;
use crate::summarize::compaction_summarize;

const ARCHIVED_STATUSES: [&str; 3] = ["closed", "done", "backlog"];

fn issue_has_terminal_summary(issue: &IssueData) -> bool {
    issue
        .comments
        .last()
        .is_some_and(|comment| comment.comment_type == "summary")
}

fn is_archived_candidate(issue: &IssueData) -> bool {
    if !ARCHIVED_STATUSES.contains(&issue.status.as_str()) {
        return false;
    }
    let age_days = (Utc::now() - issue.updated_at).num_days();
    age_days >= 30
}

/// Run batch lifecycle compaction for eligible issues.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `dry_run` - Whether to report candidates without mutating issues.
/// * `archived_only` - Whether to restrict compaction to archived issues.
/// * `max_items` - Optional maximum number of issues to process.
///
/// # Errors
/// Returns `KanbusError` when configuration or compaction fails.
pub fn run_lifecycle_compaction(
    root: &Path,
    dry_run: bool,
    archived_only: bool,
    max_items: Option<usize>,
) -> Result<String, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&configuration_path)?;
    let ai_configuration = configuration.ai.as_ref().ok_or_else(|| {
        KanbusError::IssueOperation(
            "AI provider 'litellm' is not configured in .kanbus.yml".to_string(),
        )
    })?;
    if ai_configuration.provider != "litellm" {
        return Err(KanbusError::IssueOperation(
            "AI provider 'litellm' is not configured in .kanbus.yml".to_string(),
        ));
    }

    let issues_dir = root.join(&configuration.project_directory).join("issues");
    let mut issues = load_issues_from_directory(&issues_dir)?;
    let mut eligible: Vec<IssueData> = issues
        .drain(..)
        .filter(|issue| !issue_has_terminal_summary(issue))
        .filter(|issue| !archived_only || is_archived_candidate(issue))
        .collect();

    if let Some(limit) = max_items {
        if limit > 0 && eligible.len() > limit {
            eligible.truncate(limit);
        }
    }

    let mut output = String::new();
    if dry_run {
        output.push_str("Dry-run mode: no issues were modified.\n");
        for issue in &eligible {
            output.push_str(&format!("Would summarize {}\n", issue.identifier));
        }
        return Ok(output);
    }

    for issue in &eligible {
        for message in compaction_summarize(root, &issue.identifier, false)? {
            output.push_str(&message);
            output.push('\n');
        }
    }
    output.push_str(&format!("Processed {} issues\n", eligible.len()));

    let log_path = root
        .join(&configuration.project_directory)
        .join("events")
        .join("llm_usage.jsonl");
    let mut total_cost = 0.0;
    if log_path.is_file() {
        let contents = std::fs::read_to_string(&log_path)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        for line in contents.lines() {
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(line) {
                if let Some(cost) = value.get("cost").and_then(|entry| entry.as_f64()) {
                    total_cost += cost;
                }
            }
        }
    }
    output.push_str(&format!("Total cost: ${total_cost:.4}\n"));
    Ok(output)
}
