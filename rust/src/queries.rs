//! Query utilities for issue listing.

use std::collections::HashSet;

use crate::error::KanbusError;
use crate::ids::issue_identifier_matches;
use crate::models::IssueData;
use crate::summarize::get_comment_display_text;

/// Filter issues by common fields.
///
/// # Arguments
/// * `issues` - Issues to filter.
/// * `status` - Status filter.
/// * `issue_type` - Type filter.
/// * `assignee` - Assignee filter.
/// * `label` - Label filter.
/// * `parent` - Parent identifier filter. Accepts full ids and unique prefixes.
pub fn filter_issues(
    issues: Vec<IssueData>,
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    parent: Option<&str>,
) -> Vec<IssueData> {
    issues
        .into_iter()
        .filter(|issue| status.is_none_or(|value| issue.status == value))
        .filter(|issue| issue_type.is_none_or(|value| issue.issue_type == value))
        .filter(|issue| assignee.is_none_or(|value| issue.assignee.as_deref() == Some(value)))
        .filter(|issue| label.is_none_or(|value| issue.labels.iter().any(|label| label == value)))
        .filter(|issue| {
            parent.is_none_or(|value| {
                issue
                    .parent
                    .as_deref()
                    .is_some_and(|parent_id| issue_identifier_matches(value, parent_id))
            })
        })
        .collect()
}

/// Sort issues by a supported key.
///
/// # Arguments
/// * `issues` - Issues to sort.
/// * `sort_key` - Sort key name.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if the sort key is unsupported.
pub fn sort_issues(
    mut issues: Vec<IssueData>,
    sort_key: Option<&str>,
) -> Result<Vec<IssueData>, KanbusError> {
    let Some(key) = sort_key else {
        return Ok(issues);
    };

    if key == "priority" {
        issues.sort_by_key(|issue| issue.priority);
        return Ok(issues);
    }

    Err(KanbusError::IssueOperation("invalid sort key".to_string()))
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

        let found = issue.comments.iter().any(|comment| {
            get_comment_display_text(comment)
                .to_lowercase()
                .contains(&lowered)
        });
        if found && seen.insert(issue.identifier.clone()) {
            matches.push(issue);
        }
    }

    matches
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{TimeZone, Utc};
    use std::collections::BTreeMap;

    fn issue(identifier: &str) -> IssueData {
        let timestamp = Utc.with_ymd_and_hms(2026, 3, 6, 0, 0, 0).unwrap();
        IssueData {
            identifier: identifier.to_string(),
            title: identifier.to_string(),
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
            created_at: timestamp,
            updated_at: timestamp,
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn filter_issues_matches_parent_by_full_id_and_prefix() {
        let mut child = issue("kanbus-child");
        child.parent = Some("B0-0fb0cdb3-32c3-4b5f-8c00-c2b4d7a78d8b".to_string());
        let mut other = issue("kanbus-other");
        other.parent = Some("kanbus-unrelated".to_string());
        let orphan = issue("kanbus-orphan");

        let prefix_matches = filter_issues(
            vec![child.clone(), other.clone(), orphan.clone()],
            None,
            None,
            None,
            None,
            Some("B0-0fb0cd"),
        );
        assert_eq!(
            prefix_matches
                .iter()
                .map(|issue| issue.identifier.as_str())
                .collect::<Vec<_>>(),
            vec!["kanbus-child"]
        );

        let exact_matches = filter_issues(
            vec![child, other, orphan],
            None,
            None,
            None,
            None,
            Some("B0-0fb0cdb3-32c3-4b5f-8c00-c2b4d7a78d8b"),
        );
        assert_eq!(exact_matches.len(), 1);
        assert_eq!(exact_matches[0].identifier, "kanbus-child");
    }
}
