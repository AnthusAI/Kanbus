//! Issue comment management.

use chrono::Utc;
use std::path::Path;
use uuid::Uuid;

use crate::error::KanbusError;
use crate::event_history::{
    comment_payload, comment_updated_payload, now_timestamp, EventRecord, EventType,
};
use crate::issue_files::write_issue_to_file;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_mutation::{persist_issue_mutation, PersistIssueMutationRequest};
use crate::models::{IssueComment, IssueData};
use crate::users::get_current_user;

/// Result of adding a comment to an issue.
#[derive(Debug, Clone)]
pub struct IssueCommentResult {
    pub issue: IssueData,
    pub comment: IssueComment,
}

fn generate_comment_id() -> String {
    Uuid::new_v4().to_string()
}

pub fn ensure_comment_ids(issue: &IssueData) -> (IssueData, bool) {
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

fn find_comment_by_prefix(issue: &IssueData, prefix: &str) -> Result<usize, KanbusError> {
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

fn persist_comment_mutation(
    root: &Path,
    lookup: &crate::issue_lookup::IssueLookupResult,
    updated_issue: IssueData,
    before_issue: IssueData,
    event_type: EventType,
    payload: serde_json::Value,
) -> Result<IssueData, KanbusError> {
    let actor_id = get_current_user();
    let event = EventRecord::new(
        updated_issue.identifier.clone(),
        event_type,
        actor_id.clone(),
        payload,
        now_timestamp(),
    );
    let event_id = event.event_id.clone();
    let result = persist_issue_mutation(&PersistIssueMutationRequest {
        project_dir: lookup.project_dir.clone(),
        issue_path: lookup.issue_path.clone(),
        issue: updated_issue,
        actor_id,
        events: vec![event],
        root: root.to_path_buf(),
        before_issue: Some(before_issue),
        relocate_to: None,
        regenerate_right_now: true,
    })?;
    if lookup.issue_path.parent() == Some(lookup.project_dir.join("issues").as_path()) {
        crate::gossip::publish_issue_mutation(
            root,
            &lookup.project_dir,
            &result.issue,
            Some(event_id),
            "issue.mutated",
        );
    }
    Ok(result.issue)
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
        ..base_issue
    };
    let comment_id = comment
        .id
        .clone()
        .ok_or_else(|| KanbusError::IssueOperation("comment id is required".to_string()))?;
    let persisted = persist_comment_mutation(
        root,
        &lookup,
        updated,
        lookup.issue.clone(),
        EventType::CommentAdded,
        comment_payload(&comment_id, &comment.author),
    )?;
    Ok(IssueCommentResult {
        issue: persisted,
        comment,
    })
}

/// Ensure comment IDs exist for an issue and persist any changes.
pub fn ensure_issue_comment_ids(root: &Path, identifier: &str) -> Result<IssueData, KanbusError> {
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
    let (mut issue, _) = ensure_comment_ids(&lookup.issue);
    let index = find_comment_by_prefix(&issue, comment_id_prefix)?;
    let existing_comment = issue
        .comments
        .get(index)
        .cloned()
        .ok_or_else(|| KanbusError::IssueOperation("comment not found".to_string()))?;
    if let Some(comment) = issue.comments.get_mut(index) {
        comment.text = text.to_string();
    }
    let comment_id = existing_comment
        .id
        .clone()
        .ok_or_else(|| KanbusError::IssueOperation("comment id is required".to_string()))?;
    persist_comment_mutation(
        root,
        &lookup,
        issue,
        lookup.issue.clone(),
        EventType::CommentUpdated,
        comment_updated_payload(&comment_id, &existing_comment.author),
    )
}

/// Delete an existing comment by id prefix.
pub fn delete_comment(
    root: &Path,
    identifier: &str,
    comment_id_prefix: &str,
) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let (mut issue, _) = ensure_comment_ids(&lookup.issue);
    let index = find_comment_by_prefix(&issue, comment_id_prefix)?;
    let removed = issue.comments.remove(index);
    let comment_id = removed
        .id
        .clone()
        .ok_or_else(|| KanbusError::IssueOperation("comment id is required".to_string()))?;
    persist_comment_mutation(
        root,
        &lookup,
        issue,
        lookup.issue.clone(),
        EventType::CommentDeleted,
        comment_payload(&comment_id, &removed.author),
    )
}
