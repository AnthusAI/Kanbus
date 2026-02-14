//! Issue comment management.

use chrono::Utc;
use std::path::Path;

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
        author: author.to_string(),
        text: text.to_string(),
        created_at: timestamp,
    };
    let mut comments = lookup.issue.comments.clone();
    comments.push(comment.clone());
    let updated = IssueData {
        comments,
        updated_at: timestamp,
        ..lookup.issue
    };
    write_issue_to_file(&updated, &lookup.issue_path)?;
    Ok(IssueCommentResult {
        issue: updated,
        comment,
    })
}
