//! Query utilities for issue listing.

use std::collections::HashSet;

use crate::error::KanbusError;
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

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::collections::BTreeMap;

    fn sample_issue(identifier: &str, title: &str) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: title.to_string(),
            description: "Desc".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: vec!["alpha".to_string()],
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn filter_issues_by_fields() {
        let mut issue = sample_issue("kanbus-abc", "Alpha");
        issue.assignee = Some("ryan".to_string());
        issue.labels.push("beta".to_string());
        let issue_two = sample_issue("kanbus-def", "Beta");
        let filtered = filter_issues(
            vec![issue, issue_two],
            Some("open"),
            Some("task"),
            Some("ryan"),
            Some("beta"),
        );
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].identifier, "kanbus-abc");
    }

    #[test]
    fn sort_issues_by_priority() {
        let mut low = sample_issue("kanbus-low", "Low");
        low.priority = 3;
        let mut high = sample_issue("kanbus-high", "High");
        high.priority = 1;
        let sorted = sort_issues(vec![low, high], Some("priority")).unwrap();
        assert_eq!(sorted[0].identifier, "kanbus-high");
    }

    #[test]
    fn sort_issues_rejects_invalid_key() {
        let err =
            sort_issues(vec![sample_issue("kanbus-abc", "Alpha")], Some("unknown")).unwrap_err();
        assert!(err.to_string().contains("invalid sort key"));
    }

    #[test]
    fn search_issues_matches_title_description_or_comments() {
        let mut issue = sample_issue("kanbus-abc", "Alpha");
        issue.description = "Needs Review".to_string();
        let mut issue_two = sample_issue("kanbus-def", "Other");
        issue_two.comments.push(crate::models::IssueComment {
            id: None,
            author: "author".to_string(),
            text: "Please review".to_string(),
            created_at: Utc::now(),
        });
        let matches = search_issues(vec![issue, issue_two], Some("review"));
        assert_eq!(matches.len(), 2);
    }
}
