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
        if let Some(color) = config.status_colors.get(status) {
            return parse_color(color);
        }
    }
    parse_color(match status {
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
