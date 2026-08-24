//! Issue summarization helpers shared by CLI display paths.

use std::collections::BTreeMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use chrono::Utc;
use uuid::Uuid;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_files::write_issue_to_file;
use crate::issue_listing::load_issues_from_directory;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueComment, IssueData};

pub const SUMMARY_REWRITTEN_DESCRIPTION_KEY: &str = "rewritten_description";
pub const SUMMARY_ACTIVITY_SUMMARY_KEY: &str = "activity_summary";

const MOCK_REWRITTEN_OPERATION: &str = "compaction_rewritten_description";
const MOCK_ACTIVITY_OPERATION: &str = "compaction_activity_summary";

/// Return the most recent summary comment on an issue.
///
/// # Arguments
/// * `issue` - Issue data to inspect
///
/// # Returns
/// Latest summary comment when present.
pub fn get_latest_summary_comment(issue: &IssueData) -> Option<&IssueComment> {
    issue
        .comments
        .iter()
        .rev()
        .find(|comment| comment.comment_type == "summary")
}

/// Return the rewritten description stored on a summary comment.
///
/// # Arguments
/// * `comment` - Summary comment to inspect
///
/// # Returns
/// Rewritten description text when present.
pub fn get_summary_rewritten_description(comment: &IssueComment) -> Option<String> {
    comment
        .data
        .get(SUMMARY_REWRITTEN_DESCRIPTION_KEY)
        .and_then(|value| value.as_str())
        .map(str::to_string)
        .filter(|value| !value.is_empty())
}

/// Return the activity summary stored on a summary comment.
///
/// # Arguments
/// * `comment` - Summary comment to inspect
///
/// # Returns
/// Activity summary text.
pub fn get_summary_activity_summary(comment: &IssueComment) -> String {
    comment
        .data
        .get(SUMMARY_ACTIVITY_SUMMARY_KEY)
        .and_then(|value| value.as_str())
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .unwrap_or_default()
}

/// Return the text to display for a comment.
///
/// # Arguments
/// * `comment` - Comment to render
///
/// # Returns
/// Display text for CLI and UI comment rendering.
pub fn get_comment_display_text(comment: &IssueComment) -> String {
    if comment.comment_type == "summary" {
        return get_summary_activity_summary(comment);
    }
    comment.text.clone().unwrap_or_default()
}

/// Return the effective description for display or LLM context.
///
/// # Arguments
/// * `issue` - Issue data to inspect
///
/// # Returns
/// Rewritten description when compacted, otherwise the stored description.
pub fn get_virtualized_description(issue: &IssueData) -> String {
    if let Some(summary_comment) = get_latest_summary_comment(issue) {
        if let Some(rewritten_description) = get_summary_rewritten_description(summary_comment) {
            return rewritten_description;
        }
    }
    issue.description.clone()
}

/// Apply compaction virtualization rules for display.
///
/// # Arguments
/// * `issue` - Issue data to virtualize in place
/// * `raw` - Whether to show the uncompacted view
pub fn apply_virtualized_issue_view(issue: &mut IssueData, raw: bool) {
    let summary_idx = issue
        .comments
        .iter()
        .rposition(|comment| comment.comment_type == "summary");

    let Some(idx) = summary_idx else {
        return;
    };

    if raw {
        return;
    }

    let summary = issue.comments[idx].clone();
    let summary_created_at = summary.created_at;
    if let Some(rewritten_description) = get_summary_rewritten_description(&summary) {
        issue.description = rewritten_description;
    }

    let mut virtualized_comments = vec![summary];
    for comment in &issue.comments {
        if comment.created_at > summary_created_at {
            virtualized_comments.push(comment.clone());
        }
    }
    issue.comments = virtualized_comments;
}

fn issue_has_terminal_summary(issue: &IssueData) -> bool {
    issue
        .comments
        .last()
        .is_some_and(|comment| comment.comment_type == "summary")
}

fn record_llm_usage(
    root: &Path,
    project_directory: &str,
    issue_identifier: &str,
    model: &str,
    operation: &str,
    total_tokens: u64,
    total_cost: f64,
) -> Result<(), KanbusError> {
    let events_dir = root.join(project_directory).join("events");
    std::fs::create_dir_all(&events_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let log_path = events_dir.join("llm_usage.jsonl");
    let log_entry = serde_json::json!({
        "timestamp": Utc::now().to_rfc3339(),
        "issue_id": issue_identifier,
        "model": model,
        "operation": operation,
        "tokens": total_tokens,
        "cost": total_cost,
    });
    let mut log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    writeln!(log_file, "{}", log_entry).map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}

fn mock_completion(
    root: &Path,
    project_directory: &str,
    issue_identifier: &str,
    model: &str,
    operation: &str,
) -> Result<String, KanbusError> {
    let text = if operation == MOCK_REWRITTEN_OPERATION {
        format!("Mock rewritten description for {issue_identifier}.")
    } else {
        format!("Mock activity summary for {issue_identifier}.")
    };
    record_llm_usage(
        root,
        project_directory,
        issue_identifier,
        model,
        operation,
        21,
        0.0005,
    )?;
    Ok(text)
}

/// Create a structured compaction summary comment.
///
/// # Arguments
/// * `rewritten_description` - Rewritten issue description text.
/// * `activity_summary` - Activity summary text.
///
/// # Returns
/// Summary comment with structured data fields.
pub fn build_summary_comment(
    rewritten_description: String,
    activity_summary: String,
) -> IssueComment {
    let mut data = BTreeMap::new();
    data.insert(
        SUMMARY_REWRITTEN_DESCRIPTION_KEY.to_string(),
        serde_json::Value::String(rewritten_description),
    );
    data.insert(
        SUMMARY_ACTIVITY_SUMMARY_KEY.to_string(),
        serde_json::Value::String(activity_summary),
    );
    IssueComment {
        id: Some(Uuid::new_v4().to_string()),
        author: "system:summary".to_string(),
        text: None,
        created_at: Utc::now(),
        comment_type: "summary".to_string(),
        data,
    }
}

fn summarize_children_first(
    root: &Path,
    parent_identifier: &str,
) -> Result<Vec<String>, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&configuration_path)?;
    let issues_dir = root.join(&configuration.project_directory).join("issues");
    let all_issues = load_issues_from_directory(&issues_dir)?;
    let mut messages = Vec::new();
    for child in all_issues
        .iter()
        .filter(|issue| issue.parent.as_deref() == Some(parent_identifier))
    {
        if !issue_has_terminal_summary(child) {
            messages.extend(compaction_summarize(root, &child.identifier, false)?);
        }
    }
    Ok(messages)
}

/// Summarize an issue using compaction profiles and structured summary comments.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier to summarize.
/// * `dry_run` - Whether to print context without saving.
///
/// # Errors
/// Returns `KanbusError` when configuration, AI, or persistence fails.
pub fn compaction_summarize(
    root: &Path,
    identifier: &str,
    dry_run: bool,
) -> Result<Vec<String>, KanbusError> {
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

    let _lookup = load_issue_from_project(root, identifier)?;
    if dry_run {
        return Ok(Vec::new());
    }

    if std::env::var("KANBUS_TEST_AI_MOCK").ok().as_deref() != Some("1") {
        return Err(KanbusError::IssueOperation(
            "Issue compaction requires mock AI in tests or LiteLLM integration in Rust".to_string(),
        ));
    }

    let mut messages = summarize_children_first(root, identifier)?;

    let rewritten_description = mock_completion(
        root,
        &configuration.project_directory,
        identifier,
        &ai_configuration.model,
        MOCK_REWRITTEN_OPERATION,
    )?;
    let activity_summary = mock_completion(
        root,
        &configuration.project_directory,
        identifier,
        &ai_configuration.model,
        MOCK_ACTIVITY_OPERATION,
    )?;

    let lookup = load_issue_from_project(root, identifier)?;
    let mut updated_issue = lookup.issue;
    updated_issue
        .comments
        .retain(|comment| comment.comment_type != "summary");
    updated_issue.comments.push(build_summary_comment(
        rewritten_description.clone(),
        activity_summary,
    ));
    updated_issue.updated_at = Utc::now();
    write_issue_to_file(&updated_issue, &lookup.issue_path)?;

    messages.push(format!("Summary saved for {identifier}"));
    Ok(messages)
}
