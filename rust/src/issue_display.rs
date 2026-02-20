//! Issue display formatting helpers.

use owo_colors::{AnsiColors, OwoColorize};

use crate::ids::format_issue_key;
use crate::models::{IssueData, ProjectConfiguration};

fn dim(text: &str, use_color: bool) -> String {
    if use_color {
        text.color(AnsiColors::BrightBlack).to_string()
    } else {
        text.to_string()
    }
}

fn paint(value: &str, color: Option<AnsiColors>, use_color: bool) -> String {
    match (use_color, color) {
        (true, Some(color_value)) => value.color(color_value).to_string(),
        _ => value.to_string(),
    }
}

fn parse_color(name: &str) -> Option<AnsiColors> {
    match name.to_ascii_lowercase().as_str() {
        "black" => Some(AnsiColors::Black),
        "red" => Some(AnsiColors::Red),
        "green" => Some(AnsiColors::Green),
        "yellow" => Some(AnsiColors::Yellow),
        "blue" => Some(AnsiColors::Blue),
        "magenta" => Some(AnsiColors::Magenta),
        "cyan" => Some(AnsiColors::Cyan),
        "white" => Some(AnsiColors::White),
        "bright_black" => Some(AnsiColors::BrightBlack),
        "bright_red" => Some(AnsiColors::BrightRed),
        "bright_green" => Some(AnsiColors::BrightGreen),
        "bright_yellow" => Some(AnsiColors::BrightYellow),
        "bright_blue" => Some(AnsiColors::BrightBlue),
        "bright_magenta" => Some(AnsiColors::BrightMagenta),
        "bright_cyan" => Some(AnsiColors::BrightCyan),
        "bright_white" => Some(AnsiColors::BrightWhite),
        _ => None,
    }
}

fn status_color(status: &str, configuration: Option<&ProjectConfiguration>) -> Option<AnsiColors> {
    if let Some(config) = configuration {
        // Look up color from statuses list
        if let Some(status_def) = config.statuses.iter().find(|s| s.key == status) {
            if let Some(color) = &status_def.color {
                return parse_color(color);
            }
        }
    }
    // Fallback to default colors
    parse_color(match status {
        "open" => "cyan",
        "in_progress" => "blue",
        "blocked" => "red",
        "closed" => "green",
        "deferred" => "yellow",
        _ => "",
    })
}

fn priority_color(
    priority: i32,
    configuration: Option<&ProjectConfiguration>,
) -> Option<AnsiColors> {
    if let Some(config) = configuration {
        if let Some(definition) = config.priorities.get(&(priority as u8)) {
            if let Some(color) = &definition.color {
                return parse_color(color);
            }
        }
    }
    parse_color(match priority {
        0 => "red",
        1 => "bright_red",
        2 => "yellow",
        3 => "blue",
        4 => "white",
        _ => "",
    })
}

fn type_color(
    issue_type: &str,
    configuration: Option<&ProjectConfiguration>,
) -> Option<AnsiColors> {
    if let Some(config) = configuration {
        if let Some(color) = config.type_colors.get(issue_type) {
            return parse_color(color);
        }
    }
    parse_color(match issue_type {
        "initiative" => "bright_blue",
        "epic" => "magenta",
        "task" => "cyan",
        "sub-task" => "bright_cyan",
        "bug" => "red",
        "story" => "yellow",
        "chore" => "green",
        "event" => "bright_blue",
        _ => "",
    })
}

/// Format an issue for human-readable display.
pub fn format_issue_for_display(
    issue: &IssueData,
    configuration: Option<&ProjectConfiguration>,
    use_color: bool,
    project_context: bool,
) -> String {
    let labels = if issue.labels.is_empty() {
        "-".to_string()
    } else {
        issue.labels.join(", ")
    };
    let assignee = issue.assignee.clone().unwrap_or_else(|| "-".to_string());
    let parent = issue.parent.clone().unwrap_or_else(|| "-".to_string());

    let formatted_identifier = format_issue_key(&issue.identifier, project_context);

    let rows = vec![
        ("ID:", formatted_identifier, None, false),
        ("Title:", issue.title.clone(), None, false),
        (
            "Type:",
            issue.issue_type.clone(),
            type_color(&issue.issue_type, configuration),
            false,
        ),
        (
            "Status:",
            issue.status.clone(),
            status_color(&issue.status, configuration),
            false,
        ),
        (
            "Priority:",
            issue.priority.to_string(),
            priority_color(issue.priority, configuration),
            false,
        ),
        ("Assignee:", assignee, None, issue.assignee.is_none()),
        ("Parent:", parent, None, issue.parent.is_none()),
        ("Labels:", labels, None, issue.labels.is_empty()),
    ];

    let mut lines = Vec::new();
    for (label, value, color, muted) in rows {
        let final_color = if muted {
            Some(AnsiColors::BrightBlack)
        } else {
            color
        };
        lines.push(format!(
            "{} {}",
            dim(label, use_color),
            paint(&value, final_color, use_color)
        ));
    }
    if !issue.description.is_empty() {
        lines.push(dim("Description:", use_color));
        lines.push(paint(&issue.description, None, use_color));
    }
    if !issue.dependencies.is_empty() {
        lines.push(dim("Dependencies:", use_color));
        for dependency in &issue.dependencies {
            lines.push(format!(
                "  {}: {}",
                dependency.dependency_type, dependency.target
            ));
        }
    }
    if !issue.comments.is_empty() {
        lines.push(dim("Comments:", use_color));
        for comment in &issue.comments {
            let author = if comment.author.is_empty() {
                "unknown"
            } else {
                comment.author.as_str()
            };
            let prefix = comment
                .id
                .as_deref()
                .unwrap_or("")
                .chars()
                .take(6)
                .collect::<String>();
            if prefix.is_empty() {
                lines.push(format!(
                    "  {} {}",
                    dim(&format!("{author}:"), use_color),
                    comment.text
                ));
            } else {
                lines.push(format!(
                    "  [{prefix}] {} {}",
                    dim(&format!("{author}:"), use_color),
                    comment.text
                ));
            }
        }
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use chrono::{TimeZone, Utc};
    use std::collections::BTreeMap;

    fn sample_issue(identifier: &str) -> IssueData {
        let now = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
        IssueData {
            identifier: identifier.to_string(),
            title: "Title".to_string(),
            description: "Desc".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: Some("dev@example.com".to_string()),
            creator: None,
            parent: Some("kanbus-parent".to_string()),
            labels: vec!["one".to_string(), "two".to_string()],
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now,
            updated_at: now,
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn formats_issue_with_details() {
        let issue = sample_issue("kanbus-abc1234");
        let output = format_issue_for_display(&issue, None, false, false);
        let expected_id = format_issue_key(&issue.identifier, false);
        assert!(output.contains(&format!("ID: {expected_id}")));
        assert!(output.contains("Title: Title"));
        assert!(output.contains("Type: task"));
        assert!(output.contains("Status: open"));
        assert!(output.contains("Priority: 2"));
        assert!(output.contains("Assignee: dev@example.com"));
        assert!(output.contains("Parent: kanbus-parent"));
        assert!(output.contains("Labels: one, two"));
        assert!(output.contains("Description:"));
        assert!(output.contains("Desc"));
    }

    #[test]
    fn formats_issue_with_comments() {
        let mut issue = sample_issue("kanbus-abc1234");
        let now = issue.created_at;
        issue.comments.push(crate::models::IssueComment {
            id: Some("abc123".to_string()),
            author: "dev@example.com".to_string(),
            text: "Hello".to_string(),
            created_at: now,
        });
        let output = format_issue_for_display(&issue, None, false, false);
        assert!(output.contains("Comments:"));
        assert!(output.contains("[abc123] dev@example.com: Hello"));
    }

    #[test]
    fn uses_configured_colors_when_present() {
        let mut config = default_project_configuration();
        if let Some(status) = config.statuses.iter_mut().find(|s| s.key == "open") {
            status.color = Some("bright_white".to_string());
        }
        assert_eq!(
            status_color("open", Some(&config)),
            Some(AnsiColors::BrightWhite)
        );
    }
}
