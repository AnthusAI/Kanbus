//! Right-now summary helpers.

use std::collections::{HashMap, HashSet};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use chrono::Utc;
use serde_json::{json, Value};

use crate::config_loader::{load_project_configuration, load_repository_environment};
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_files::{read_issue_from_file, write_issue_to_file};
use crate::issue_lookup::load_issue_from_project;
use crate::litellm_completion::litellm_chat_completion;
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
/// Status used when Now lists the board without an explicit `--status` filter.
pub const DEFAULT_RIGHT_NOW_STATUS: &str = "in_progress";

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

/// Error message when OpenAI credentials were not loaded from env files.
pub const OPENAI_API_KEY_NOT_LOADED_MESSAGE: &str =
    "OPENAI_API_KEY was not loaded from repository environment files";

/// Error message when right-now generation is disabled in configuration.
pub const RIGHT_NOW_DISABLED_MESSAGE: &str =
    "Right-now summary generation is disabled in .kanbus.yml";

const TEST_RIGHT_NOW_COMPLETION_ENV: &str = "KANBUS_TEST_RIGHT_NOW_COMPLETION";

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

/// Return whether a summary matches the deterministic test mock pattern.
///
/// # Arguments
///
/// * `summary` - Summary text to inspect.
/// * `identifier` - Issue identifier for the mock template.
///
/// # Returns
///
/// `true` when the summary is a persisted test mock string.
pub fn is_persisted_mock_right_now_summary(summary: &str, identifier: &str) -> bool {
    summary == mock_right_now_summary_text(identifier)
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
        .map(|comment| {
            format!(
                "{}: {}",
                comment.author,
                comment.text.as_deref().unwrap_or("")
            )
        })
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
        .map(|comment| {
            format!(
                "{}: {}",
                comment.author,
                comment.text.as_deref().unwrap_or("")
            )
        })
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
    context: &RightNowContext,
) -> Result<String, KanbusError> {
    load_repository_environment(root);
    let configuration = load_configuration(root)?;
    ensure_litellm_provider(&configuration)?;
    let max_length = configuration.right_now.max_length;
    let model = resolve_right_now_model(&configuration)?;
    ensure_openai_credentials_when_required()?;

    if let Ok(stub_completion) = std::env::var(TEST_RIGHT_NOW_COMPLETION_ENV) {
        return Ok(truncate_to_max_length(stub_completion.trim(), max_length));
    }

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

    if std::env::var("KANBUS_TEST_SIMULATE_LITELLM_MISSING").as_deref() == Ok("1") {
        return Err(KanbusError::IssueOperation(
            "litellm is required for right-now summary generation".to_string(),
        ));
    }

    let prompt = build_right_now_prompt(context, max_length);
    let (completion_text, usage) = litellm_chat_completion(&model, &prompt)?;
    record_llm_usage(
        root,
        &configuration,
        &issue.identifier,
        &model,
        RightNowLlmUsageRecord {
            prompt_tokens: usage.prompt_tokens,
            completion_tokens: usage.completion_tokens,
            total_tokens: usage.total_tokens,
            cost: usage.cost,
            mock: false,
        },
    )?;
    Ok(truncate_to_max_length(completion_text.trim(), max_length))
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
/// When `fail_closed` is false, generation failures leave the existing summary
/// unchanged. When true, failures return `KanbusError`.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue_identifier` - Issue identifier to regenerate.
/// * `fail_closed` - Whether generation failures should raise.
///
/// # Errors
///
/// Returns `KanbusError` when `fail_closed` is true and generation cannot run.
pub fn regenerate_right_now_for_issue(
    root: &Path,
    issue_identifier: &str,
    fail_closed: bool,
) -> Result<(), KanbusError> {
    load_repository_environment(root);
    let configuration = match load_configuration(root) {
        Ok(configuration) => configuration,
        Err(error) => {
            if fail_closed {
                return Err(error);
            }
            return Ok(());
        }
    };
    if !configuration.right_now.enabled {
        if fail_closed {
            return Err(KanbusError::IssueOperation(
                RIGHT_NOW_DISABLED_MESSAGE.to_string(),
            ));
        }
        return Ok(());
    }
    let lookup = match load_issue_from_project(root, issue_identifier) {
        Ok(lookup) => lookup,
        Err(error) => {
            if fail_closed {
                return Err(error);
            }
            return Ok(());
        }
    };
    let children = match load_child_issues(root, issue_identifier) {
        Ok(children) => children,
        Err(error) => {
            if fail_closed {
                return Err(error);
            }
            return Ok(());
        }
    };
    let context = build_right_now_context(&lookup.issue, &children);
    let summary = match generate_right_now_summary(root, &lookup.issue, &context) {
        Ok(summary) => summary,
        Err(error) => {
            if fail_closed {
                return Err(error);
            }
            eprintln!("warning: right-now generation failed for {issue_identifier}: {error}");
            return Ok(());
        }
    };
    let current_time = Utc::now();
    match persist_right_now_summary(
        &lookup.project_dir,
        &lookup.issue_path,
        issue_identifier,
        &summary,
        current_time,
    ) {
        Ok(()) => Ok(()),
        Err(error) => {
            if fail_closed {
                Err(error)
            } else {
                eprintln!("warning: right-now persist failed for {issue_identifier}: {error}");
                Ok(())
            }
        }
    }
}

/// Return whether an issue needs a just-in-time right-now summary.
///
/// # Arguments
///
/// * `issue` - Issue to inspect.
///
/// # Returns
///
/// `true` when the summary is absent or older than the issue.
pub fn right_now_summary_is_missing_or_stale(issue: &IssueData) -> bool {
    match issue.right_now_summary.as_deref() {
        None => true,
        Some(summary) if summary.trim().is_empty() => true,
        Some(_) => match issue.right_now_updated_at {
            None => false,
            Some(updated) => issue.updated_at > updated,
        },
    }
}

/// Return whether an issue needs JIT right-now summary regeneration.
///
/// # Arguments
///
/// * `issue` - Issue to inspect.
///
/// # Returns
///
/// `true` when the summary is absent, stale, or a persisted test mock.
pub fn right_now_summary_needs_regeneration(issue: &IssueData) -> bool {
    match issue.right_now_summary.as_deref() {
        None => true,
        Some(summary) if summary.trim().is_empty() => true,
        Some(summary) => {
            if is_persisted_mock_right_now_summary(summary, &issue.identifier)
                && std::env::var("KANBUS_TEST_AI_MOCK").as_deref() != Ok("1")
            {
                return true;
            }
            match issue.right_now_updated_at {
                None => false,
                Some(updated) => issue.updated_at > updated,
            }
        }
    }
}

/// Return the right-now summary for CLI display or an error when invalid.
///
/// # Arguments
///
/// * `issue` - Issue whose summary is required.
///
/// # Errors
///
/// Returns `KanbusError` when the summary is missing or a persisted test mock.
pub fn require_display_right_now_summary(issue: &IssueData) -> Result<String, KanbusError> {
    let summary = issue
        .right_now_summary
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            KanbusError::IssueOperation(format!(
                "right-now summary missing for {}",
                issue.identifier
            ))
        })?;
    if is_persisted_mock_right_now_summary(summary, &issue.identifier)
        && std::env::var("KANBUS_TEST_AI_MOCK").as_deref() != Ok("1")
    {
        return Err(KanbusError::IssueOperation(format!(
            "persisted test mock right-now summary for {} must be regenerated",
            issue.identifier
        )));
    }
    Ok(summary.to_string())
}

/// Clear right-now summary fields from every live store for an issue.
///
/// # Errors
///
/// Returns `KanbusError` when a live store cannot be written.
pub fn clear_right_now_summary(
    project_dir: &Path,
    issue_path: &Path,
    issue_identifier: &str,
) -> Result<(), KanbusError> {
    let overlay_path = overlay_issue_path(project_dir, issue_identifier);
    if issue_path != overlay_path.as_path() && issue_path.exists() {
        let mut stored_issue = read_issue_from_file(issue_path)?;
        stored_issue.right_now_summary = None;
        stored_issue.right_now_updated_at = None;
        write_issue_to_file(&stored_issue, issue_path)?;
    }
    if let Some(overlay_record) = load_overlay_issue(project_dir, issue_identifier)? {
        let mut overlay_issue = overlay_record.issue;
        overlay_issue.right_now_summary = None;
        overlay_issue.right_now_updated_at = None;
        write_overlay_issue(
            project_dir,
            &overlay_issue,
            &overlay_record.overlay_ts,
            overlay_record.overlay_event_id,
        )?;
    }
    Ok(())
}

/// Clear right-now summary fields for every issue on the board.
///
/// # Errors
///
/// Returns `KanbusError` when listing or writing issues fails.
pub fn purge_right_now_summaries(root: &Path) -> Result<usize, KanbusError> {
    let issues = crate::issue_listing::list_issues(
        root,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        &[],
        true,
        false,
    )?;
    let mut purged = 0usize;
    for issue in issues {
        if issue.right_now_summary.is_none() && issue.right_now_updated_at.is_none() {
            continue;
        }
        let lookup = load_issue_from_project(root, &issue.identifier)?;
        clear_right_now_summary(&lookup.project_dir, &lookup.issue_path, &issue.identifier)?;
        purged += 1;
    }
    Ok(purged)
}

/// Backfill right-now summaries for an issue after selected descendants.
///
/// Only children in `selected_identifiers` are visited. Unlisted descendants
/// are left unchanged so a large closed subtree cannot block the parent.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue_identifier` - Issue identifier to ensure.
/// * `selected_identifiers` - Issue identifiers in the current Now view.
/// * `memo` - Per-walk cache of whether a subtree generated a summary.
///
/// # Returns
///
/// `true` when this subtree generated or refreshed a summary.
pub fn ensure_right_now_subtree(
    root: &Path,
    issue_identifier: &str,
    selected_identifiers: &HashSet<String>,
    memo: &mut HashMap<String, bool>,
    fail_closed: bool,
) -> Result<bool, KanbusError> {
    if let Some(generated) = memo.get(issue_identifier) {
        return Ok(*generated);
    }
    let children = match load_child_issues(root, issue_identifier) {
        Ok(children) => children,
        Err(error) => {
            if fail_closed {
                return Err(error);
            }
            memo.insert(issue_identifier.to_string(), false);
            return Ok(false);
        }
    };
    let mut descendant_generated = false;
    for child in &children {
        if !selected_identifiers.contains(&child.identifier) {
            continue;
        }
        if ensure_right_now_subtree(
            root,
            &child.identifier,
            selected_identifiers,
            memo,
            fail_closed,
        )? {
            descendant_generated = true;
        }
    }
    let lookup = match load_issue_from_project(root, issue_identifier) {
        Ok(lookup) => lookup,
        Err(error) => {
            if fail_closed {
                return Err(error);
            }
            memo.insert(issue_identifier.to_string(), false);
            return Ok(false);
        }
    };
    let should_generate =
        descendant_generated || right_now_summary_needs_regeneration(&lookup.issue);
    let mut generated = false;
    if should_generate {
        let previous_summary = lookup.issue.right_now_summary.clone();
        let previous_updated = lookup.issue.right_now_updated_at;
        regenerate_right_now_for_issue(root, issue_identifier, fail_closed)?;
        if let Ok(after) = load_issue_from_project(root, issue_identifier) {
            generated = after.issue.right_now_summary != previous_summary
                || after.issue.right_now_updated_at != previous_updated;
            if fail_closed {
                require_display_right_now_summary(&after.issue)?;
            }
        } else if fail_closed {
            return Err(KanbusError::IssueOperation(format!(
                "issue not found after regeneration: {issue_identifier}"
            )));
        }
    }
    let result = generated || descendant_generated;
    memo.insert(issue_identifier.to_string(), result);
    Ok(result)
}

/// Backfill right-now summaries for the issues in the current Now view.
///
/// Descendants that are not in `issue_identifiers` are not generated.
///
/// # Arguments
///
/// * `root` - Repository root path.
/// * `issue_identifiers` - Issue identifiers in the current Now view.
/// * `fail_closed` - Whether generation failures should raise.
///
/// # Errors
///
/// Returns `KanbusError` when `fail_closed` is true and generation cannot run.
pub fn ensure_right_now_summaries(
    root: &Path,
    issue_identifiers: &[String],
    fail_closed: bool,
) -> Result<(), KanbusError> {
    let selected_identifiers: HashSet<String> = issue_identifiers.iter().cloned().collect();
    let mut memo = HashMap::new();
    for identifier in issue_identifiers {
        ensure_right_now_subtree(
            root,
            identifier,
            &selected_identifiers,
            &mut memo,
            fail_closed,
        )?;
    }
    Ok(())
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
        let _ = regenerate_right_now_for_issue(root, &identifier, false);
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

pub(crate) fn ensure_litellm_provider(
    configuration: &ProjectConfiguration,
) -> Result<(), KanbusError> {
    match configuration.ai.as_ref() {
        Some(ai_configuration) if ai_configuration.provider == "litellm" => Ok(()),
        _ => Err(KanbusError::IssueOperation(
            AI_PROVIDER_NOT_CONFIGURED_MESSAGE.to_string(),
        )),
    }
}

fn ensure_openai_credentials_when_required() -> Result<(), KanbusError> {
    if std::env::var("KANBUS_TEST_AI_REQUIRE_ENV_CREDENTIALS").as_deref() != Ok("1") {
        return Ok(());
    }
    match std::env::var("OPENAI_API_KEY") {
        Ok(value) if !value.trim().is_empty() => Ok(()),
        _ => Err(KanbusError::IssueOperation(
            OPENAI_API_KEY_NOT_LOADED_MESSAGE.to_string(),
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
                .as_deref()
                .unwrap_or("")
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

fn build_right_now_prompt(context: &RightNowContext, max_length: usize) -> String {
    let child_section = match context.child_summaries.as_ref() {
        Some(child_summaries) if !child_summaries.is_empty() => {
            let lines = child_summaries
                .iter()
                .map(|child| format!("- {}: {}", child.identifier, child.summary))
                .collect::<Vec<_>>()
                .join("\n");
            format!("Child summaries:\n{lines}\n\n")
        }
        _ => String::new(),
    };
    format!(
        "Write exactly one short sentence describing what is happening with this \
issue right now. Use plain, direct language in Hemingway style. \
Do not mention issue status labels such as open, closed, blocked, done, \
or in progress. Maximum {max_length} characters.\n\n\
Title: {title}\n\
Description: {description}\n\
Recent activity:\n{recent_activity}\n\n\
{child_section}",
        title = context.title,
        description = context.description,
        recent_activity = context.recent_activity,
    )
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
    use crate::issue_files::{read_issue_from_file, write_issue_to_file};
    use crate::models::IssueData;
    use crate::overlay::{load_overlay_issue, write_overlay_issue};
    use chrono::Utc;
    use std::collections::BTreeMap;
    use std::fs;

    fn make_issue(id: &str, title: &str) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: title.to_string(),
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
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        }
    }

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

    #[test]
    fn persist_right_now_summary_updates_canonical_and_overlay() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        let issue_path = project_dir.join("issues/kanbus-rn1.json");
        fs::create_dir_all(issue_path.parent().expect("parent")).expect("mkdir");
        let issue = make_issue("kanbus-rn1", "Canonical");
        write_issue_to_file(&issue, &issue_path).expect("write canonical");
        write_overlay_issue(
            &project_dir,
            &issue,
            "2099-01-01T00:00:00.000Z",
            Some("evt-overlay".to_string()),
        )
        .expect("write overlay");
        persist_right_now_summary(
            &project_dir,
            &issue_path,
            "kanbus-rn1",
            "Canonical work continues.",
            Utc::now(),
        )
        .expect("persist");
        let stored = read_issue_from_file(&issue_path).expect("read canonical");
        assert_eq!(
            stored.right_now_summary.as_deref(),
            Some("Canonical work continues.")
        );
        let overlay = load_overlay_issue(&project_dir, "kanbus-rn1")
            .expect("load overlay")
            .expect("overlay present");
        assert_eq!(
            overlay.issue.right_now_summary.as_deref(),
            Some("Canonical work continues.")
        );
        assert_eq!(overlay.overlay_ts, "2099-01-01T00:00:00.000Z");
    }

    #[test]
    fn persist_right_now_summary_updates_overlay_when_canonical_path_is_overlay() {
        let temp = tempfile::tempdir().expect("tempdir");
        let project_dir = temp.path().join("project");
        fs::create_dir_all(project_dir.join("issues")).expect("mkdir");
        let issue = make_issue("kanbus-rn-overlay", "Overlay only");
        write_overlay_issue(&project_dir, &issue, "2099-01-01T00:00:00.000Z", None)
            .expect("write overlay");
        let overlay_path = overlay_issue_path(&project_dir, "kanbus-rn-overlay");
        persist_right_now_summary(
            &project_dir,
            &overlay_path,
            "kanbus-rn-overlay",
            "Overlay work continues.",
            Utc::now(),
        )
        .expect("persist");
        let overlay = load_overlay_issue(&project_dir, "kanbus-rn-overlay")
            .expect("load overlay")
            .expect("overlay present");
        assert_eq!(
            overlay.issue.right_now_summary.as_deref(),
            Some("Overlay work continues.")
        );
    }

    #[test]
    fn resolve_child_summary_uses_raw_when_right_now_and_full_are_absent() {
        let issue = make_issue("kanbus-raw", "Raw child");
        let rendered = resolve_child_summary(&issue);
        assert!(rendered.contains("Title: Raw child"));
    }

    #[test]
    fn truncate_to_max_length_without_spaces_cuts_at_limit() {
        assert_eq!(truncate_to_max_length("abcdefghij", 4), "abcd");
        assert_eq!(truncate_to_max_length("abc", 10), "abc");
    }

    #[test]
    fn regenerate_right_now_for_issue_returns_when_configuration_is_missing() {
        let temp = tempfile::tempdir().expect("tempdir");
        regenerate_right_now_for_issue(temp.path(), "kanbus-missing", false).expect("ok");
        regenerate_right_now_for_issue_and_ancestors(temp.path(), "kanbus-missing");
    }

    #[test]
    fn regenerate_right_now_for_issue_skips_when_disabled() {
        let temp = tempfile::tempdir().expect("tempdir");
        let mut configuration = crate::config::default_project_configuration();
        configuration.right_now.enabled = false;
        let yaml = serde_yaml::to_string(&configuration).expect("serialize config");
        fs::write(temp.path().join(".kanbus.yml"), yaml).expect("write config");
        regenerate_right_now_for_issue(temp.path(), "kanbus-disabled", false).expect("ok");
    }

    #[test]
    fn regenerate_right_now_for_issue_skips_missing_issue() {
        let temp = tempfile::tempdir().expect("tempdir");
        let configuration = crate::config::default_project_configuration();
        let yaml = serde_yaml::to_string(&configuration).expect("serialize config");
        fs::write(temp.path().join(".kanbus.yml"), yaml).expect("write config");
        fs::create_dir_all(temp.path().join("project/issues")).expect("mkdir");
        regenerate_right_now_for_issue(temp.path(), "kanbus-absent", false).expect("ok");
    }

    #[test]
    fn read_right_now_llm_usage_entries_returns_empty_when_log_missing() {
        let temp = tempfile::tempdir().expect("tempdir");
        let entries = read_right_now_llm_usage_entries(temp.path()).expect("read");
        assert!(entries.is_empty());
    }

    #[test]
    fn summary_contains_status_keyword_detects_bare_tokens() {
        assert!(summary_contains_status_keyword("Work is blocked on review"));
        assert!(!summary_contains_status_keyword("Agents keep shipping"));
    }

    #[test]
    fn build_right_now_prompt_includes_child_summaries() {
        let context = RightNowContext {
            title: "Parent".to_string(),
            description: "Parent description".to_string(),
            recent_activity: "Recent parent activity".to_string(),
            child_summaries: Some(vec![RightNowChildSummary {
                identifier: "kanbus-child".to_string(),
                summary: "Child summary.".to_string(),
            }]),
        };
        let prompt = build_right_now_prompt(&context, 80);
        assert!(prompt.contains("Child summaries:"));
        assert!(prompt.contains("kanbus-child: Child summary."));
    }
}
