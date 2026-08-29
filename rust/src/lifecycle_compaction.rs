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

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{Duration, Utc};
    use std::path::PathBuf;
    use tempfile::TempDir;

    use crate::issue_files::write_issue_to_file;
    use crate::models::IssueData;
    use serial_test::serial;

    fn sample_issue(
        identifier: &str,
        status: &str,
        updated_at: chrono::DateTime<Utc>,
    ) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: format!("Issue {identifier}"),
            description: "Test description".to_string(),
            issue_type: "task".to_string(),
            status: status.to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: updated_at,
            updated_at,
            closed_at: None,
            custom: std::collections::BTreeMap::new(),
        }
    }

    fn write_project_with_issue(temp: &TempDir, issue: &IssueData) -> PathBuf {
        let root = temp.path().to_path_buf();
        std::fs::write(
            root.join(".kanbus.yml"),
            "project_key: TST\nproject_directory: project\nai:\n  provider: litellm\n  model: gpt-5.6-luna\n",
        )
        .expect("write config");
        let issues_dir = root.join("project/issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");
        write_issue_to_file(
            issue,
            &issues_dir.join(format!("{}.json", issue.identifier)),
        )
        .expect("write issue");
        root
    }

    #[test]
    #[serial]
    fn run_lifecycle_compaction_dry_run_lists_candidates() {
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        let temp = TempDir::new().expect("tempdir");
        let updated_at = Utc::now() - Duration::days(40);
        let issue = sample_issue("TST-archived", "closed", updated_at);
        let root = write_project_with_issue(&temp, &issue);
        let output = run_lifecycle_compaction(&root, true, true, None).expect("dry-run compaction");
        assert!(output.contains("Dry-run mode: no issues were modified."));
        assert!(output.contains("Would summarize TST-archived"));
    }
}
