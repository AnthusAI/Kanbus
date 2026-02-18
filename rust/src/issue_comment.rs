//! Issue comment management.

use chrono::Utc;
use std::path::Path;
use uuid::Uuid;

use crate::error::KanbusError;
use crate::issue_files::write_issue_to_file;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueComment, IssueData};

/// Result of adding a comment to an issue.
#[derive(Debug, Clone)]
pub struct IssueCommentResult {
    pub issue: IssueData,
    pub comment: IssueComment,
}

fn generate_comment_id() -> String {
    Uuid::new_v4().to_string()
}

fn ensure_comment_ids(issue: &IssueData) -> (IssueData, bool) {
    let mut changed = false;
    let comments = issue
        .comments
        .iter()
        .map(|comment| {
            if comment.id.as_deref().unwrap_or("").is_empty() {
                changed = true;
                IssueComment {
                    id: Some(generate_comment_id()),
                    author: comment.author.clone(),
                    text: comment.text.clone(),
                    created_at: comment.created_at,
                }
            } else {
                comment.clone()
            }
        })
        .collect::<Vec<_>>();
    if !changed {
        return (issue.clone(), false);
    }
    (
        IssueData {
            comments,
            ..issue.clone()
        },
        true,
    )
}

fn normalize_prefix(prefix: &str) -> Result<String, KanbusError> {
    let trimmed = prefix.trim();
    if trimmed.is_empty() {
        return Err(KanbusError::IssueOperation(
            "comment id is required".to_string(),
        ));
    }
    Ok(trimmed.to_ascii_lowercase())
}

fn find_comment_by_prefix(
    issue: &IssueData,
    prefix: &str,
) -> Result<usize, KanbusError> {
    let normalized = normalize_prefix(prefix)?;
    let mut matches = Vec::new();
    for (index, comment) in issue.comments.iter().enumerate() {
        let Some(id) = comment.id.as_deref() else {
            continue;
        };
        if id.to_ascii_lowercase().starts_with(&normalized) {
            matches.push(index);
        }
    }
    match matches.len() {
        0 => Err(KanbusError::IssueOperation("comment not found".to_string())),
        1 => Ok(matches[0]),
        _ => {
            let ids = matches
                .iter()
                .filter_map(|index| issue.comments.get(*index))
                .filter_map(|comment| comment.id.as_deref())
                .map(|id| id.chars().take(6).collect::<String>())
                .collect::<Vec<_>>()
                .join(", ");
            Err(KanbusError::IssueOperation(format!(
                "comment id prefix is ambiguous; matches: {ids}"
            )))
        }
    }
}

/// Add a comment to an issue.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
/// * `author` - Comment author.
/// * `text` - Comment text.
///
/// # Errors
/// Returns `KanbusError` if the issue cannot be found or updated.
pub fn add_comment(
    root: &Path,
    identifier: &str,
    author: &str,
    text: &str,
) -> Result<IssueCommentResult, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let timestamp = Utc::now();
    let comment = IssueComment {
        id: Some(generate_comment_id()),
        author: author.to_string(),
        text: text.to_string(),
        created_at: timestamp,
    };
    let (base_issue, _) = ensure_comment_ids(&lookup.issue);
    let mut comments = base_issue.comments.clone();
    comments.push(comment.clone());
    let updated = IssueData {
        comments,
        updated_at: timestamp,
        ..base_issue
    };
    write_issue_to_file(&updated, &lookup.issue_path)?;
    Ok(IssueCommentResult {
        issue: updated,
        comment,
    })
}

/// Ensure comment IDs exist for an issue and persist any changes.
pub fn ensure_issue_comment_ids(
    root: &Path,
    identifier: &str,
) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let (updated, changed) = ensure_comment_ids(&lookup.issue);
    if changed {
        write_issue_to_file(&updated, &lookup.issue_path)?;
    }
    Ok(updated)
}

/// Update an existing comment by id prefix.
pub fn update_comment(
    root: &Path,
    identifier: &str,
    comment_id_prefix: &str,
    text: &str,
) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let (mut issue, changed) = ensure_comment_ids(&lookup.issue);
    let index = find_comment_by_prefix(&issue, comment_id_prefix)?;
    let timestamp = Utc::now();
    if let Some(comment) = issue.comments.get_mut(index) {
        comment.text = text.to_string();
    }
    issue.updated_at = timestamp;
    write_issue_to_file(&issue, &lookup.issue_path)?;
    if changed {
        // already written updated issue with ids
    }
    Ok(issue)
}

/// Delete an existing comment by id prefix.
pub fn delete_comment(
    root: &Path,
    identifier: &str,
    comment_id_prefix: &str,
) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let (mut issue, _changed) = ensure_comment_ids(&lookup.issue);
    let index = find_comment_by_prefix(&issue, comment_id_prefix)?;
    issue.comments.remove(index);
    issue.updated_at = Utc::now();
    write_issue_to_file(&issue, &lookup.issue_path)?;
    Ok(issue)
}
