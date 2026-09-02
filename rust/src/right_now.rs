//! Right-now summary helpers.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::Utc;
use serde_json::{json, Value};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_files::{read_issue_from_file, write_issue_to_file};
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueComment, IssueData, ProjectConfiguration};
use crate::overlay::{load_overlay_issue, overlay_issue_path, write_overlay_issue};

const RIGHT_NOW_SUMMARY_OPERATION: &str = "right_now_summary";
const LLM_USAGE_LOG: &str = "llm_usage.jsonl";
const MOCK_PROMPT_TOKENS: u64 = 42;
const MOCK_COMPLETION_TOKENS: u64 = 12;
const MOCK_TOTAL_TOKENS: u64 = 54;
const MOCK_COST: f64 = 0.0;
const MAX_RECENT_COMMENTS: usize = 5;
const MAX_RECENT_ACTIVITY_CHARACTERS: usize = 2000;
const STATUS_KEYWORDS: [&str; 5] = ["done", "in progress", "blocked", "closed", "open"];

/// LLM usage details for right-now summary generation.
#[derive(Debug, Clone, Copy)]
struct RightNowLlmUsageRecord {
    /// Prompt token count.
    prompt_tokens: u64,
    /// Completion token count.
    completion_tokens: u64,
    /// Total token count.
    total_tokens: u64,
    /// Estimated cost.
    cost: f64,
    /// Whether the usage came from mock mode.
    mock: bool,
}

/// Error message when AI provider is not configured for right-now generation.
pub const AI_PROVIDER_NOT_CONFIGURED_MESSAGE: &str =
    "Right-now summary generation requires ai.provider litellm in .kanbus.yml";

/// Child issue summary for parent context assembly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RightNowChildSummary {
    /// Child issue identifier.
    pub identifier: String,
    /// Child right-now summary text.
    pub summary: String,
}

/// Structured context for right-now summary generation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RightNowContext {
    /// Issue title.
    pub title: String,
    /// Issue description.
    pub description: String,
    /// Recent non-summary comment text.
    pub recent_activity: String,
    /// Optional child summaries for parent roll-up.
    pub child_summaries: Option<Vec<RightNowChildSummary>>,
}

/// Return the right-now summary for an issue.
///
/// # Arguments
///
/// * `issue` - Issue data to read.
///
/// # Returns
///
/// The right-now summary text, or `None` when absent.
pub fn get_right_now_summary(issue: &IssueData) -> Option<&str> {
    issue.right_now_summary.as_deref()
}

/// Return the deterministic mock right-now summary for an issue.
///
/// # Arguments
///
/// * `identifier` - Issue identifier.
///
/// # Returns
///
/// Mock summary text.
pub fn mock_right_now_summary_text(identifier: &str) -> String {
    format!("Mock right-now summary for {identifier}.")
}

/// Return a child's compaction full summary when present.
///
/// On this branch no compaction/full-summary tier exists, so a child
/// full summary is never available and this always returns `None`. When a
/// full-summary tier lands, this helper is updated there (alongside the
/// `IssueComment` comment_type field) rather than speculatively here.
///
/// # Arguments
///
/// * `issue` - Child issue to inspect.
///
/// # Returns
///
/// Full summary text, or `None` when no compaction artifact exists.
pub fn get_child_full_summary(_issue: &IssueData) -> Option<String> {
    None
}

/// Render a bounded raw child summary from title, description, and activity.
///
/// # Arguments
///
/// * `issue` - Child issue to render.
///
/// # Returns
///
/// Bounded raw child summary text.
pub fn build_bounded_raw_child_summary(issue: &IssueData) -> String {
    let recent_comments = select_recent_non_summary_comments(&issue.comments);
    let activity_lines: Vec<String> = recent_comments
        .iter()
        .map(|comment| format!("{}: {}", comment.author, comment.text))
        .collect();
    let recent_activity = bound_activity_text(&activity_lines.join("\n"));
    let raw_text = format!(
        "Title: {}\nDescription: {}\nRecent activity:\n{}",
        issue.title, issue.description, recent_activity
    );
    bound_activity_text(&raw_text)
}

/// Resolve the summary text used when rolling a child into parent context.
///
/// # Arguments
///
/// * `issue` - Child issue to resolve.
///
/// # Returns
///
/// Child summary text from right-now cache, full summary, or raw issue.
pub fn resolve_child_summary(issue: &IssueData) -> String {
    if let Some(summary) = issue.right_now_summary.as_ref() {
        return summary.clone();
    }
    if let Some(full_summary) = get_child_full_summary(issue) {
        return full_summary;
    }
    build_bounded_raw_child_summary(issue)
}

/// Assemble parent-issue context from own fields and child summaries.
///
/// # Arguments
///
/// * `issue` - Parent issue to build context for.
/// * `children` - Direct child issues.
///
/// # Returns
///
/// Structured right-now context with child summaries.
pub fn build_parent_right_now_context(
    issue: &IssueData,
    children: &[IssueData],
) -> RightNowContext {
    let leaf_context = build_leaf_right_now_context(issue);
    let child_summaries = children
        .iter()
        .map(|child| RightNowChildSummary {
            identifier: child.identifier.clone(),
            summary: resolve_child_summary(child),
        })
        .collect();
    RightNowContext {
        title: leaf_context.title,
        description: leaf_context.description,
        recent_activity: leaf_context.recent_activity,
        child_summaries: Some(child_summaries),
    }
}

/// Assemble right-now context for a leaf or parent issue.
///
/// # Arguments
///
/// * `issue` - Issue to build context for.
/// * `children` - Direct child issues, or an empty slice for leaf issues.
///
/// # Returns
///
/// Structured right-now context.
pub fn build_right_now_context(issue: &IssueData, children: &[IssueData]) -> RightNowContext {
    if children.is_empty() {
        build_leaf_right_now_context(issue)
    } else {
        build_parent_right_now_context(issue, children)
    }
}

/// Load direct child issues for a parent issue identifier.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue_identifier` - Parent issue identifier.
///
/// # Returns
///
/// Child issues whose parent matches the identifier.
///
/// # Errors
///
/// Returns `KanbusError` when issue listing fails.
pub fn load_child_issues(
    root: &Path,
    issue_identifier: &str,
) -> Result<Vec<IssueData>, KanbusError> {
    crate::issue_listing::list_issues(
        root,
        None,
        None,
        None,
        None,
        Some(issue_identifier),
        None,
        None,
        &[],
        true,
        false,
    )
}

/// Assemble leaf-issue context from title, description, and recent comments.
///
/// # Arguments
///
/// * `issue` - Issue to build context for.
///
/// # Returns
///
/// Structured right-now context.
pub fn build_leaf_right_now_context(issue: &IssueData) -> RightNowContext {
    let recent_comments = select_recent_non_summary_comments(&issue.comments);
    let activity_lines: Vec<String> = recent_comments
        .iter()
        .map(|comment| format!("{}: {}", comment.author, comment.text))
        .collect();
    let recent_activity = bound_activity_text(&activity_lines.join("\n"));
    RightNowContext {
        title: issue.title.clone(),
        description: issue.description.clone(),
        recent_activity,
        child_summaries: None,
    }
}

/// Generate a right-now summary for an issue using configured AI.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue` - Issue to summarize.
/// * `context` - Assembled right-now context.
///
/// # Returns
///
/// One-sentence right-now summary text.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when AI is not configured or generation fails.
pub fn generate_right_now_summary(
    root: &Path,
    issue: &IssueData,
    _context: &RightNowContext,
) -> Result<String, KanbusError> {
    let configuration = load_configuration(root)?;
    ensure_litellm_provider(&configuration)?;
    let max_length = configuration.right_now.max_length;
    let model = resolve_right_now_model(&configuration)?;

    if std::env::var("KANBUS_TEST_AI_MOCK").as_deref() == Ok("1") {
        let summary = mock_right_now_summary_text(&issue.identifier);
        record_llm_usage(
            root,
            &configuration,
            &issue.identifier,
            &model,
            RightNowLlmUsageRecord {
                prompt_tokens: MOCK_PROMPT_TOKENS,
                completion_tokens: MOCK_COMPLETION_TOKENS,
                total_tokens: MOCK_TOTAL_TOKENS,
                cost: MOCK_COST,
                mock: true,
            },
        )?;
        return Ok(truncate_to_max_length(&summary, max_length));
    }

    let summary = delegate_right_now_summary_to_python(root, &issue.identifier)?;
    Ok(truncate_to_max_length(&summary, max_length))
}

/// Persist only right-now summary fields without re-entering the write gate.
///
/// Writes the two right-now fields onto every live store for the issue:
/// the canonical IssueData file when `issue_path` is that file, and the
/// overlay snapshot when one exists.
///
/// # Arguments
///
/// * `project_dir` - Shared project directory.
/// * `issue_path` - Path used by issue lookup (canonical or overlay).
/// * `issue_identifier` - Issue identifier whose stores are updated.
/// * `summary` - Generated right-now summary text.
/// * `updated_at` - Timestamp for `right_now_updated_at`.
///
/// # Errors
///
/// Returns `KanbusError` when a live store cannot be written.
pub fn persist_right_now_summary(
    project_dir: &Path,
    issue_path: &Path,
    issue_identifier: &str,
    summary: &str,
    updated_at: chrono::DateTime<Utc>,
) -> Result<(), KanbusError> {
    let overlay_path = overlay_issue_path(project_dir, issue_identifier);
    if issue_path != overlay_path.as_path() && issue_path.exists() {
        let mut stored_issue = read_issue_from_file(issue_path)?;
        stored_issue.right_now_summary = Some(summary.to_string());
        stored_issue.right_now_updated_at = Some(updated_at);
        write_issue_to_file(&stored_issue, issue_path)?;
    }
    if let Some(overlay_record) = load_overlay_issue(project_dir, issue_identifier)? {
        let mut overlay_issue = overlay_record.issue;
        overlay_issue.right_now_summary = Some(summary.to_string());
        overlay_issue.right_now_updated_at = Some(updated_at);
        write_overlay_issue(
            project_dir,
            &overlay_issue,
            &overlay_record.overlay_ts,
            overlay_record.overlay_event_id,
        )?;
    }
    Ok(())
}

/// Regenerate and persist the right-now summary for one issue.
///
/// When generation is disabled or fails, the existing summary is left unchanged.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue_identifier` - Issue identifier to regenerate.
pub fn regenerate_right_now_for_issue(root: &Path, issue_identifier: &str) {
    let configuration = match load_configuration(root) {
        Ok(configuration) => configuration,
        Err(_) => return,
    };
    if !configuration.right_now.enabled {
        return;
    }
    let lookup = match load_issue_from_project(root, issue_identifier) {
        Ok(lookup) => lookup,
        Err(_) => return,
    };
    let children = match load_child_issues(root, issue_identifier) {
        Ok(children) => children,
        Err(_) => return,
    };
    let context = build_right_now_context(&lookup.issue, &children);
    let summary = match generate_right_now_summary(root, &lookup.issue, &context) {
        Ok(summary) => summary,
        Err(_) => return,
    };
    let current_time = Utc::now();
    let _ = persist_right_now_summary(
        &lookup.project_dir,
        &lookup.issue_path,
        issue_identifier,
        &summary,
        current_time,
    );
}

/// Regenerate right-now summaries for an issue and each ancestor.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue_identifier` - Starting issue identifier.
pub fn regenerate_right_now_for_issue_and_ancestors(root: &Path, issue_identifier: &str) {
    let mut current_identifier = Some(issue_identifier.to_string());
    while let Some(identifier) = current_identifier {
        regenerate_right_now_for_issue(root, &identifier);
        current_identifier = load_issue_from_project(root, &identifier)
            .ok()
            .and_then(|lookup| lookup.issue.parent.clone());
    }
}

/// Regenerate right-now summaries for ancestors after a child deletion.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `parent_identifier` - Parent issue identifier, if any.
pub fn regenerate_right_now_ancestors(root: &Path, parent_identifier: Option<&str>) {
    if let Some(parent_identifier) = parent_identifier {
        regenerate_right_now_for_issue_and_ancestors(root, parent_identifier);
    }
}

/// Return whether a summary contains a bare status keyword.
///
/// # Arguments
///
/// * `summary` - Summary text to inspect.
///
/// # Returns
///
/// `true` when a status keyword appears as a standalone token.
pub fn summary_contains_status_keyword(summary: &str) -> bool {
    let lowered = summary.to_lowercase();
    for keyword in STATUS_KEYWORDS {
        let pattern = format!(r"\b{}\b", regex::escape(keyword));
        if regex::Regex::new(&pattern)
            .map(|expression| expression.is_match(&lowered))
            .unwrap_or(false)
        {
            return true;
        }
    }
    false
}

fn load_configuration(root: &Path) -> Result<ProjectConfiguration, KanbusError> {
    load_project_configuration(&get_configuration_path(root)?)
}

fn ensure_litellm_provider(configuration: &ProjectConfiguration) -> Result<(), KanbusError> {
    match configuration.ai.as_ref() {
        Some(ai_configuration) if ai_configuration.provider == "litellm" => Ok(()),
        _ => Err(KanbusError::IssueOperation(
            AI_PROVIDER_NOT_CONFIGURED_MESSAGE.to_string(),
        )),
    }
}

fn resolve_right_now_model(configuration: &ProjectConfiguration) -> Result<String, KanbusError> {
    if let Some(model) = configuration.right_now.model.as_ref() {
        return Ok(model.clone());
    }
    configuration
        .ai
        .as_ref()
        .map(|ai_configuration| ai_configuration.model.clone())
        .ok_or_else(|| KanbusError::IssueOperation(AI_PROVIDER_NOT_CONFIGURED_MESSAGE.to_string()))
}

fn select_recent_non_summary_comments(comments: &[IssueComment]) -> Vec<IssueComment> {
    let filtered: Vec<IssueComment> = comments
        .iter()
        .filter(|comment| {
            !comment
                .text
                .trim()
                .to_ascii_lowercase()
                .starts_with("summary:")
        })
        .cloned()
        .collect();
    let start = filtered.len().saturating_sub(MAX_RECENT_COMMENTS);
    filtered[start..].to_vec()
}

fn bound_activity_text(activity_text: &str) -> String {
    if activity_text.len() <= MAX_RECENT_ACTIVITY_CHARACTERS {
        return activity_text.to_string();
    }
    activity_text[activity_text.len() - MAX_RECENT_ACTIVITY_CHARACTERS..].to_string()
}

fn truncate_to_max_length(text: &str, max_length: usize) -> String {
    if text.len() <= max_length {
        return text.to_string();
    }
    let truncated = &text[..max_length];
    if let Some(last_space) = truncated.rfind(' ') {
        if last_space > 0 {
            return truncated[..last_space].trim_end().to_string();
        }
    }
    truncated.trim_end().to_string()
}

fn record_llm_usage(
    root: &Path,
    configuration: &ProjectConfiguration,
    issue_identifier: &str,
    model: &str,
    usage: RightNowLlmUsageRecord,
) -> Result<(), KanbusError> {
    let events_dir = root.join(&configuration.project_directory).join("events");
    fs::create_dir_all(&events_dir)
        .map_err(|error| KanbusError::Io(format!("create events directory: {error}")))?;
    let log_path = events_dir.join(LLM_USAGE_LOG);
    let entry = json!({
        "completion_tokens": usage.completion_tokens,
        "cost": usage.cost,
        "issue_id": issue_identifier,
        "mock": usage.mock,
        "model": model,
        "operation": RIGHT_NOW_SUMMARY_OPERATION,
        "prompt_tokens": usage.prompt_tokens,
        "timestamp": Utc::now().to_rfc3339(),
        "total_tokens": usage.total_tokens,
    });
    let mut handle = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|error| KanbusError::Io(format!("open llm usage log: {error}")))?;
    serde_json::to_writer(&mut handle, &entry)
        .map_err(|error| KanbusError::Io(format!("write llm usage log: {error}")))?;
    handle
        .write_all(b"\n")
        .map_err(|error| KanbusError::Io(format!("append llm usage log: {error}")))?;
    Ok(())
}

fn delegate_right_now_summary_to_python(
    root: &Path,
    issue_identifier: &str,
) -> Result<String, KanbusError> {
    let output = Command::new("python3")
        .args([
            "-m",
            "kanbus.cli",
            "now-generate-internal",
            issue_identifier,
        ])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(format!("invoke python right-now generator: {error}")))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(KanbusError::IssueOperation(stderr.trim().to_string()));
    }
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout.is_empty() {
        return Err(KanbusError::IssueOperation(
            "right-now summary generation returned empty content".to_string(),
        ));
    }
    Ok(stdout)
}

/// Read llm usage entries for right-now summary operations.
///
/// # Arguments
///
/// * `events_dir` - Project events directory path.
///
/// # Returns
///
/// Parsed usage log entries for right-now summary operations.
///
/// # Errors
///
/// Returns `KanbusError::Io` when the log cannot be read.
pub fn read_right_now_llm_usage_entries(events_dir: &Path) -> Result<Vec<Value>, KanbusError> {
    let log_path = events_dir.join(LLM_USAGE_LOG);
    if !log_path.exists() {
        return Ok(Vec::new());
    }
    let contents = fs::read_to_string(&log_path)
        .map_err(|error| KanbusError::Io(format!("read llm usage log: {error}")))?;
    let entries = contents
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|entry| {
            entry.get("operation").and_then(Value::as_str) == Some(RIGHT_NOW_SUMMARY_OPERATION)
        })
        .collect();
    Ok(entries)
}

/// Return the project events directory for a repository root.
///
/// # Arguments
///
/// * `root` - Repository root path.
///
/// # Returns
///
/// Path to the events directory.
///
/// # Errors
///
/// Returns `KanbusError` when configuration cannot be loaded.
pub fn project_events_directory(root: &Path) -> Result<PathBuf, KanbusError> {
    let configuration = load_configuration(root)?;
    Ok(root.join(configuration.project_directory).join("events"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mock_summary_matches_python_format() {
        assert_eq!(
            mock_right_now_summary_text("kanbus-rn1"),
            "Mock right-now summary for kanbus-rn1."
        );
    }

    #[test]
    fn truncate_to_max_length_uses_word_boundary() {
        let text = "Mock right-now summary for kanbus-rn2.";
        let truncated = truncate_to_max_length(text, 20);
        assert!(truncated.len() <= 20);
        assert_eq!(truncated, "Mock right-now");
    }
}
