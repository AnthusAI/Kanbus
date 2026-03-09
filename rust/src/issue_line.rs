//! Single-line issue formatting for list output.

use owo_colors::{AnsiColors, OwoColorize};

use crate::ids::format_issue_key;
use crate::models::{IssueData, ProjectConfiguration};

/// Column widths for list output.
#[derive(Debug, Clone, Copy)]
pub struct Widths {
    pub issue_type: usize,
    pub identifier: usize,
    pub parent: usize,
    pub status: usize,
    pub priority: usize,
}

/// Compute printable column widths for aligned normal-mode output.
pub fn compute_widths(issues: &[IssueData], project_context: bool) -> Widths {
    let mut widths = Widths {
        issue_type: 1,
        identifier: 0,
        parent: 0,
        status: 0,
        priority: 0,
    };

    for issue in issues {
        widths.issue_type = widths.issue_type.max(1);
        widths.status = widths.status.max(issue.status.len());
        widths.priority = widths.priority.max(format!("P{}", issue.priority).len());
        let formatted_identifier = format_issue_key(&issue.identifier, project_context);
        widths.identifier = widths.identifier.max(formatted_identifier.len());
        let parent_value = issue.parent.as_deref().unwrap_or("-");
        let parent_display = if parent_value == "-" {
            parent_value.to_string()
        } else {
            format_issue_key(parent_value, project_context)
        };
        widths.parent = widths.parent.max(parent_display.len());
    }

    widths
}

/// Render a single-line summary similar to Beads.
///
/// When `use_color_override` is `None`, color is determined by NO_COLOR and
/// stdout TTY (interactive). When `Some(true)` or `Some(false)`, that value
/// is used instead (for tests or callers that know the context).
pub fn format_issue_line(
    issue: &IssueData,
    widths: Option<&Widths>,
    porcelain: bool,
    project_context: bool,
    configuration: Option<&ProjectConfiguration>,
    use_color_override: Option<bool>,
) -> String {
    let parent_value = issue.parent.clone().unwrap_or_else(|| "-".to_string());
    let formatted_identifier = format_issue_key(&issue.identifier, project_context);
    let parent_display = if parent_value == "-" {
        parent_value.clone()
    } else {
        format_issue_key(&parent_value, project_context)
    };
    if porcelain {
        return format!(
            "{} | {} | {} | {} | P{} | {}",
            issue
                .issue_type
                .chars()
                .next()
                .unwrap_or(' ')
                .to_ascii_uppercase(),
            formatted_identifier,
            parent_display,
            issue.status,
            issue.priority,
            issue.title
        );
    }

    let computed_widths = widths
        .copied()
        .unwrap_or_else(|| compute_widths(std::slice::from_ref(issue), project_context));
    let use_color = use_color_override.unwrap_or_else(should_use_color);
    let prefix = issue
        .custom
        .get("project_path")
        .and_then(|value| value.as_str())
        .map(|value| format!("{value} "))
        .unwrap_or_default();

    let type_initial = issue
        .issue_type
        .chars()
        .next()
        .unwrap_or(' ')
        .to_ascii_uppercase()
        .to_string();
    let type_part = paint(
        &format!(
            "{:width$}",
            type_initial,
            width = computed_widths.issue_type
        ),
        type_color(&issue.issue_type, configuration),
        use_color,
    );

    let identifier_part = format!(
        "{:width$}",
        formatted_identifier,
        width = computed_widths.identifier
    );
    let parent_plain = format!("{:width$}", parent_display, width = computed_widths.parent);
    let parent_part = if parent_value == "-" && use_color {
        parent_plain.color(AnsiColors::BrightBlack).to_string()
    } else {
        parent_plain
    };
    let status_part = paint(
        &format!("{:width$}", issue.status, width = computed_widths.status),
        status_color(&issue.status, configuration),
        use_color,
    );
    let priority_value = format!("P{}", issue.priority);
    let priority_part = paint(
        &format!(
            "{:width$}",
            priority_value,
            width = computed_widths.priority
        ),
        priority_color(issue.priority, configuration),
        use_color,
    );
    format!(
        "{prefix}{type_part} {identifier_part} {parent_part} {status_part} {priority_part} {}",
        issue.title
    )
}

fn should_use_color() -> bool {
    use std::io::IsTerminal;
    // Disable colors if NO_COLOR is set or if stdout is not a TTY
    std::env::var_os("NO_COLOR").is_none() && std::io::stdout().is_terminal()
}

fn paint(text: &str, color: Option<AnsiColors>, use_color: bool) -> String {
    match (use_color, color) {
        (true, Some(color_value)) => text.color(color_value).to_string(),
        _ => text.to_string(),
    }
}

fn parse_color(name: &str) -> Option<AnsiColors> {
    match name {
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
        "backlog" => "grey",
        "open" => "cyan",
        "in_progress" => "blue",
        "blocked" => "red",
        "closed" => "green",
        "deferred" => "yellow",
        _ => "white",
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
        _ => "white",
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
        "epic" => "magenta",
        "initiative" => "bright_magenta",
        "task" => "white",
        "sub-task" => "white",
        "bug" => "red",
        "story" => "cyan",
        "chore" => "blue",
        "event" => "bright_blue",
        _ => "white",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::collections::BTreeMap;

    use crate::models::{CategoryDefinition, PriorityDefinition, StatusDefinition};

    fn sample_issue(id: &str, issue_type: &str, status: &str, parent: Option<&str>) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: format!("Title {id}"),
            description: String::new(),
            issue_type: issue_type.to_string(),
            status: status.to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: parent.map(std::string::ToString::to_string),
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    fn sample_configuration() -> ProjectConfiguration {
        let mut workflows = BTreeMap::new();
        workflows.insert("default".to_string(), BTreeMap::new());

        let mut priorities = BTreeMap::new();
        priorities.insert(
            2u8,
            PriorityDefinition {
                name: "medium".to_string(),
                color: Some("bright_cyan".to_string()),
            },
        );

        ProjectConfiguration {
            project_directory: "project".to_string(),
            virtual_projects: BTreeMap::new(),
            new_issue_project: None,
            ignore_paths: Vec::new(),
            console_port: None,
            project_key: "kanbus".to_string(),
            project_management_template: None,
            hierarchy: vec!["task".to_string()],
            types: vec!["task".to_string()],
            workflows,
            transition_labels: BTreeMap::new(),
            initial_status: "open".to_string(),
            priorities,
            default_priority: 2,
            assignee: None,
            time_zone: None,
            statuses: vec![StatusDefinition {
                key: "open".to_string(),
                name: "Open".to_string(),
                category: "todo".to_string(),
                color: Some("bright_green".to_string()),
                collapsed: false,
            }],
            categories: vec![CategoryDefinition {
                name: "todo".to_string(),
                color: None,
            }],
            sort_order: BTreeMap::new(),
            type_colors: BTreeMap::from([("task".to_string(), "bright_magenta".to_string())]),
            beads_compatibility: false,
            wiki_directory: None,
            ai: None,
            jira: None,
            snyk: None,
            realtime: Default::default(),
            overlay: Default::default(),
            hooks: Default::default(),
        }
    }

    #[test]
    fn compute_widths_accounts_for_formatted_identifier_and_parent() {
        let issues = vec![
            sample_issue("kanbus-123456789abc", "task", "open", None),
            sample_issue(
                "kanbus-999999999999",
                "epic",
                "in_progress",
                Some("kanbus-123456789abc"),
            ),
        ];
        let widths = compute_widths(&issues, true);
        assert!(widths.identifier >= 6);
        assert!(widths.parent >= 1);
        assert!(widths.status >= "in_progress".len());
        assert!(widths.priority >= 2);
    }

    #[test]
    fn format_issue_line_handles_porcelain_and_plain_modes() {
        let issue = sample_issue("kanbus-abcdef123456", "task", "open", Some("kanbus-111111111111"));
        let widths = compute_widths(std::slice::from_ref(&issue), false);

        let porcelain = format_issue_line(&issue, Some(&widths), true, false, None, Some(false));
        assert!(porcelain.contains("T |"));
        assert!(porcelain.contains("P2"));

        let plain = format_issue_line(&issue, Some(&widths), false, false, None, Some(false));
        assert!(plain.contains("Title kanbus-abcdef123456"));
        assert!(plain.contains("open"));
        assert!(plain.contains("P2"));
    }

    #[test]
    fn format_issue_line_includes_project_prefix_and_parent_dash() {
        let mut issue = sample_issue("kanbus-aaaaaa111111", "bug", "blocked", None);
        issue.custom.insert(
            "project_path".to_string(),
            serde_json::Value::String("apps/api".to_string()),
        );
        let widths = compute_widths(std::slice::from_ref(&issue), false);

        let line = format_issue_line(&issue, Some(&widths), false, false, None, Some(false));
        assert!(line.starts_with("apps/api "));
        assert!(line.contains(" - "));
        assert!(line.contains("blocked"));
    }

    #[test]
    fn color_helpers_cover_configured_and_fallback_paths() {
        let config = sample_configuration();
        assert_eq!(status_color("open", Some(&config)), Some(AnsiColors::BrightGreen));
        assert_eq!(priority_color(2, Some(&config)), Some(AnsiColors::BrightCyan));
        assert_eq!(type_color("task", Some(&config)), Some(AnsiColors::BrightMagenta));

        assert_eq!(status_color("closed", None), Some(AnsiColors::Green));
        assert_eq!(priority_color(0, None), Some(AnsiColors::Red));
        assert_eq!(type_color("story", None), Some(AnsiColors::Cyan));
        assert_eq!(parse_color("not-a-color"), None);
        assert_eq!(status_color("backlog", None), None);
    }
}
