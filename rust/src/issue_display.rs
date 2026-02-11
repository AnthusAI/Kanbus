//! Issue display formatting helpers.

use crate::models::IssueData;

/// Format an issue for human-readable display.
pub fn format_issue_for_display(issue: &IssueData) -> String {
    let labels = if issue.labels.is_empty() {
        "None".to_string()
    } else {
        issue.labels.join(", ")
    };
    let assignee = issue.assignee.clone().unwrap_or_else(|| "None".to_string());
    let parent = issue.parent.clone().unwrap_or_else(|| "None".to_string());

    let mut lines = vec![
        format!("ID: {}", issue.identifier),
        format!("Title: {}", issue.title),
        format!("Type: {}", issue.issue_type),
        format!("Status: {}", issue.status),
        format!("Priority: {}", issue.priority),
        format!("Assignee: {}", assignee),
        format!("Parent: {}", parent),
        format!("Labels: {}", labels),
    ];
    if !issue.description.is_empty() {
        lines.push("Description:".to_string());
        lines.push(issue.description.clone());
    }
    lines.join("\n")
}
