//! Standup rollup shapes and WIP close-out helpers.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use chrono::{DateTime, Utc};
use regex::Regex;

use crate::error::KanbusError;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueData, ProjectConfiguration};
use crate::standup::{is_stale_in_progress, truncate_bullet};
use crate::standup_window::StandupWindowSettings;

pub const ROLLUP_FLAT: &str = "flat";
pub const ROLLUP_PROJECT: &str = "project";
pub const ROLLUP_TREE: &str = "tree";
pub const CLOSE_OUT_SECTION: &str = "Close-out";
pub const EMPTY_YESTERDAY_BULLET: &str = "No completions yesterday.";

const TREE_INDENT: &str = "  ";

static STANDUP_ROLLUP_CHOICES: [&str; 3] = [ROLLUP_FLAT, ROLLUP_PROJECT, ROLLUP_TREE];

/// Resolved standup rollup mode for report assembly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StandupRollupSettings {
    /// Rollup mode identifier.
    pub mode: String,
}

/// Resolve standup rollup mode from CLI flag and board shape.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when the rollup mode is unknown.
pub fn resolve_standup_rollup(
    rollup: Option<&str>,
    configuration: &ProjectConfiguration,
    explicit_issue_scope: bool,
) -> Result<StandupRollupSettings, KanbusError> {
    if let Some(mode) = rollup {
        if !STANDUP_ROLLUP_CHOICES.contains(&mode) {
            return Err(KanbusError::IssueOperation(format!(
                "unknown standup rollup: {mode}"
            )));
        }
        return Ok(StandupRollupSettings {
            mode: mode.to_string(),
        });
    }
    if !configuration.virtual_projects.is_empty() {
        return Ok(StandupRollupSettings {
            mode: ROLLUP_PROJECT.to_string(),
        });
    }
    if explicit_issue_scope {
        return Ok(StandupRollupSettings {
            mode: ROLLUP_TREE.to_string(),
        });
    }
    Ok(StandupRollupSettings {
        mode: ROLLUP_FLAT.to_string(),
    })
}

/// Return the congregation project label for an issue.
pub fn issue_project_label(issue: &IssueData, configuration: &ProjectConfiguration) -> String {
    if let Some(label) = issue
        .custom
        .get("project_label")
        .and_then(|value| value.as_str())
    {
        let trimmed = label.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }
    configuration.project_key.clone()
}

/// Include ancestor issues needed for tree and project rollups.
pub fn expand_issues_with_ancestors(
    root: &Path,
    issues: &[IssueData],
) -> Result<Vec<IssueData>, KanbusError> {
    let mut by_identifier: HashMap<String, IssueData> = issues
        .iter()
        .map(|issue| (issue.identifier.clone(), issue.clone()))
        .collect();
    for issue in issues {
        let mut parent_identifier = issue.parent.clone();
        while let Some(parent_id) = parent_identifier {
            if by_identifier.contains_key(&parent_id) {
                break;
            }
            let lookup = match load_issue_from_project(root, &parent_id) {
                Ok(lookup) => lookup,
                Err(_) => break,
            };
            let next_parent = lookup.issue.parent.clone();
            by_identifier.insert(parent_id, lookup.issue);
            parent_identifier = next_parent;
        }
    }
    Ok(by_identifier.into_values().collect())
}

fn normalize_summary_text(text: &str) -> String {
    let lowered = text.trim().to_lowercase();
    let collapsed = Regex::new(r"\s+")
        .expect("valid regex")
        .replace_all(&lowered, " ")
        .to_string();
    collapsed.trim_end_matches('.').to_string()
}

fn summaries_near_identical(first: &str, second: &str) -> bool {
    let normalized_first = normalize_summary_text(first);
    let normalized_second = normalize_summary_text(second);
    if normalized_first == normalized_second {
        return true;
    }
    let (shorter, longer) = if normalized_first.len() <= normalized_second.len() {
        (&normalized_first, &normalized_second)
    } else {
        (&normalized_second, &normalized_first)
    };
    if shorter.is_empty() {
        return false;
    }
    longer.contains(shorter) && shorter.len() >= 12
}

fn dedupe_summary_list(summaries: &[String]) -> Vec<String> {
    let mut kept: Vec<String> = Vec::new();
    for summary in summaries {
        if kept
            .iter()
            .any(|existing| summaries_near_identical(summary, existing))
        {
            continue;
        }
        kept.push(summary.clone());
    }
    kept
}

fn forest_roots(issues: &[IssueData]) -> Vec<IssueData> {
    let identifiers: HashSet<String> = issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    let mut roots = issues
        .iter()
        .filter(|issue| {
            issue
                .parent
                .as_ref()
                .map(|parent| !identifiers.contains(parent))
                .unwrap_or(true)
        })
        .cloned()
        .collect::<Vec<_>>();
    roots.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    roots
}

fn children_map(issues: &[IssueData]) -> HashMap<String, Vec<IssueData>> {
    let identifiers: HashSet<String> = issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    let mut children: HashMap<String, Vec<IssueData>> = HashMap::new();
    for issue in issues {
        let parent = issue.parent.as_ref();
        let Some(parent_id) = parent else {
            continue;
        };
        if !identifiers.contains(parent_id) {
            continue;
        }
        children
            .entry(parent_id.clone())
            .or_default()
            .push(issue.clone());
    }
    for child_list in children.values_mut() {
        child_list.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    }
    children
}

fn emit_tree_lines(
    issue: &IssueData,
    depth: usize,
    children_by_parent: &HashMap<String, Vec<IssueData>>,
    right_now_texts: &HashMap<String, String>,
    parent_summary: Option<&str>,
    lines: &mut Vec<String>,
) {
    let summary = right_now_texts
        .get(&issue.identifier)
        .map(String::as_str)
        .unwrap_or("");
    let include = parent_summary.is_none()
        || !summaries_near_identical(summary, parent_summary.unwrap_or(""));
    if include {
        let indent = TREE_INDENT.repeat(depth);
        lines.push(truncate_bullet(&format!("{indent}{summary}")));
    }
    let effective_parent = if include {
        Some(summary)
    } else {
        parent_summary
    };
    for child in children_by_parent
        .get(&issue.identifier)
        .map(Vec::as_slice)
        .unwrap_or(&[])
    {
        emit_tree_lines(
            child,
            depth + 1,
            children_by_parent,
            right_now_texts,
            effective_parent,
            lines,
        );
    }
}

/// Build Today (or Momentum) bullets for the requested rollup mode.
pub fn roll_up_active_bullets(
    active_issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    configuration: &ProjectConfiguration,
    rollup_settings: &StandupRollupSettings,
    prefix_issue_identifiers: bool,
) -> Vec<String> {
    if active_issues.is_empty() {
        return Vec::new();
    }
    if rollup_settings.mode == ROLLUP_FLAT {
        return active_issues
            .iter()
            .map(|issue| {
                let summary = right_now_texts
                    .get(&issue.identifier)
                    .map(String::as_str)
                    .unwrap_or("");
                if prefix_issue_identifiers {
                    truncate_bullet(&format!("{}: {}", issue.identifier, summary))
                } else {
                    truncate_bullet(summary)
                }
            })
            .collect();
    }

    let mut by_project: HashMap<String, Vec<IssueData>> = HashMap::new();
    for issue in active_issues {
        let label = issue_project_label(issue, configuration);
        by_project.entry(label).or_default().push(issue.clone());
    }

    let mut labels: Vec<String> = by_project.keys().cloned().collect();
    labels.sort();

    let mut bullets = Vec::new();
    for label in labels {
        let project_issues = by_project.get(&label).expect("label");
        let roots = forest_roots(project_issues);
        let children_by_parent = children_map(project_issues);

        if rollup_settings.mode == ROLLUP_PROJECT {
            let root_summaries = dedupe_summary_list(
                &roots
                    .iter()
                    .map(|root| {
                        right_now_texts
                            .get(&root.identifier)
                            .cloned()
                            .unwrap_or_default()
                    })
                    .collect::<Vec<_>>(),
            );
            let joined = root_summaries.join("; ");
            bullets.push(truncate_bullet(&format!("[{label}] {joined}")));
            continue;
        }

        let prefix = format!("[{label}] ");
        for root in roots {
            let mut tree_lines: Vec<String> = Vec::new();
            emit_tree_lines(
                &root,
                0,
                &children_by_parent,
                right_now_texts,
                None,
                &mut tree_lines,
            );
            if tree_lines.is_empty() {
                continue;
            }
            let first_line = &tree_lines[0];
            if first_line.starts_with(TREE_INDENT) {
                tree_lines[0] = truncate_bullet(&format!("{}{}", prefix, first_line.trim_start()));
            } else {
                tree_lines[0] = truncate_bullet(&format!("{prefix}{first_line}"));
            }
            bullets.extend(tree_lines);
        }
    }
    bullets
}

/// Ensure Yesterday always has an explicit empty-state bullet.
pub fn ensure_yesterday_bullets(yesterday_bullets: &[String]) -> Vec<String> {
    if yesterday_bullets.is_empty() {
        return vec![EMPTY_YESTERDAY_BULLET.to_string()];
    }
    yesterday_bullets.to_vec()
}

fn ready_to_close_pattern() -> &'static Regex {
    static PATTERN: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?i)ready to close|ready for close|can be closed|close out|close-out")
            .expect("valid regex")
    })
}

fn merged_still_open_pattern() -> &'static Regex {
    static PATTERN: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"(?i)\bmerged\b").expect("valid regex"))
}

fn external_block_pattern() -> &'static Regex {
    static PATTERN: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"(?i)waiting on|blocked on|awaiting").expect("valid regex"))
}

/// Build Close-out bullets for WIP cards that should finish soon.
pub fn build_close_out_bullets(
    issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> Vec<String> {
    let mut bullets = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for issue in issues {
        let summary = right_now_texts
            .get(&issue.identifier)
            .map(String::as_str)
            .unwrap_or("");
        if summary.is_empty() {
            continue;
        }
        let candidate = if issue.status == "in_progress" {
            if merged_still_open_pattern().is_match(summary) {
                Some(format!(
                    "{}: merged but still in progress — {}",
                    issue.identifier,
                    truncate_bullet(summary)
                ))
            } else if ready_to_close_pattern().is_match(summary) {
                Some(format!(
                    "{}: {}",
                    issue.identifier,
                    truncate_bullet(summary)
                ))
            } else if is_stale_in_progress(issue, report_time, window_settings) {
                Some(format!(
                    "{}: stale WIP — {}",
                    issue.identifier,
                    truncate_bullet(summary)
                ))
            } else {
                None
            }
        } else if issue.status == "blocked" && external_block_pattern().is_match(summary) {
            Some(format!(
                "{}: {}",
                issue.identifier,
                truncate_bullet(summary)
            ))
        } else {
            None
        };
        if let Some(text) = candidate {
            let normalized = normalize_summary_text(&text);
            if seen.contains(&normalized) {
                continue;
            }
            seen.insert(normalized);
            bullets.push(truncate_bullet(&text));
        }
    }
    bullets
}
