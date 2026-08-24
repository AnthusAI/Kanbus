//! Issue summarization helpers shared by CLI display paths.

use crate::models::{IssueComment, IssueData};

pub const SUMMARY_REWRITTEN_DESCRIPTION_KEY: &str = "rewritten_description";
pub const SUMMARY_ACTIVITY_SUMMARY_KEY: &str = "activity_summary";

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
        if let Some(rewritten_description) =
            get_summary_rewritten_description(summary_comment)
        {
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
