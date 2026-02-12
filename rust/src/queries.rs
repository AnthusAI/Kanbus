//! Query utilities for issue listing.

use std::collections::HashSet;

use crate::error::TaskulusError;
use crate::models::IssueData;

/// Filter issues by common fields.
///
/// # Arguments
/// * `issues` - Issues to filter.
/// * `status` - Status filter.
/// * `issue_type` - Type filter.
/// * `assignee` - Assignee filter.
/// * `label` - Label filter.
pub fn filter_issues(
    issues: Vec<IssueData>,
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
) -> Vec<IssueData> {
    issues
        .into_iter()
        .filter(|issue| status.is_none_or(|value| issue.status == value))
        .filter(|issue| issue_type.is_none_or(|value| issue.issue_type == value))
        .filter(|issue| assignee.is_none_or(|value| issue.assignee.as_deref() == Some(value)))
        .filter(|issue| label.is_none_or(|value| issue.labels.iter().any(|label| label == value)))
        .collect()
}

/// Sort issues by a supported key.
///
/// # Arguments
/// * `issues` - Issues to sort.
/// * `sort_key` - Sort key name.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if the sort key is unsupported.
pub fn sort_issues(
    mut issues: Vec<IssueData>,
    sort_key: Option<&str>,
) -> Result<Vec<IssueData>, TaskulusError> {
    let Some(key) = sort_key else {
        return Ok(issues);
    };

    if key == "priority" {
        issues.sort_by_key(|issue| issue.priority);
        return Ok(issues);
    }

    Err(TaskulusError::IssueOperation(
        "invalid sort key".to_string(),
    ))
}

/// Search issues by title, description, and comments.
///
/// # Arguments
/// * `issues` - Issues to search.
/// * `term` - Search term.
pub fn search_issues(issues: Vec<IssueData>, term: Option<&str>) -> Vec<IssueData> {
    let Some(value) = term.filter(|value| !value.is_empty()) else {
        return issues;
    };

    let lowered = value.to_lowercase();
    let mut matches = Vec::new();
    let mut seen = HashSet::new();

    for issue in issues {
        if issue.title.to_lowercase().contains(&lowered)
            || issue.description.to_lowercase().contains(&lowered)
        {
            if seen.insert(issue.identifier.clone()) {
                matches.push(issue);
            }
            continue;
        }

        let found = issue
            .comments
            .iter()
            .any(|comment| comment.text.to_lowercase().contains(&lowered));
        if found && seen.insert(issue.identifier.clone()) {
            matches.push(issue);
        }
    }

    matches
}
