//! Standup rollup shapes and WIP close-out helpers.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use chrono::{DateTime, Utc};
use regex::Regex;

use crate::error::KanbusError;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueData, ProjectConfiguration};
use crate::standup::{
    is_event_within_lookback, is_stale_in_progress, is_within_lookback, truncate_bullet,
};
use crate::standup_rollup_reduce::reduce_summaries_for_standup_rollup;
use crate::standup_window::StandupWindowSettings;
use serde_json::Value;

pub const ROLLUP_FLAT: &str = "flat";
pub const ROLLUP_PROJECT: &str = "project";
pub const ROLLUP_TREE: &str = "tree";
pub const CLOSE_OUT_SECTION: &str = "Close-out";
pub const EMPTY_YESTERDAY_BULLET: &str = "No completions yesterday.";
pub const CLOSE_OUT_MAX_BULLETS: usize = 6;

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

/// Normalize a raw project label to a congregation partition key.
pub fn resolve_standup_partition_key(
    raw_label: &str,
    configuration: &ProjectConfiguration,
) -> String {
    let trimmed = raw_label.trim();
    if trimmed.is_empty() {
        return configuration.project_key.clone();
    }
    if trimmed == configuration.project_key {
        return configuration.project_key.clone();
    }
    if configuration.virtual_projects.contains_key(trimmed) {
        return trimmed.to_string();
    }
    let lowered = trimmed.to_lowercase();
    if configuration
        .name
        .as_ref()
        .map(|name| name.trim().eq_ignore_ascii_case(trimmed))
        .unwrap_or(false)
    {
        return configuration.project_key.clone();
    }
    if lowered == configuration.project_key.to_lowercase() {
        return configuration.project_key.clone();
    }
    for (partition_key, virtual_project) in &configuration.virtual_projects {
        if partition_key.to_lowercase() == lowered {
            return partition_key.clone();
        }
        if virtual_project
            .display_name
            .as_ref()
            .map(|name| name.trim().eq_ignore_ascii_case(trimmed))
            .unwrap_or(false)
        {
            return partition_key.clone();
        }
    }
    trimmed.to_string()
}

/// Return the stable human display label for a congregation partition.
pub fn canonical_standup_project_display_label(
    partition_key: &str,
    configuration: &ProjectConfiguration,
) -> String {
    if partition_key == configuration.project_key {
        if let Some(name) = configuration.name.as_ref() {
            let trimmed = name.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
        return configuration.project_key.clone();
    }
    let virtual_project = configuration.virtual_projects.get(partition_key);
    if let Some(virtual_project) = virtual_project {
        if let Some(display_name) = virtual_project.display_name.as_ref() {
            let trimmed = display_name.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
    }
    partition_key.to_string()
}

/// Return the congregation partition key for an issue.
pub fn issue_project_partition_key(
    issue: &IssueData,
    configuration: &ProjectConfiguration,
) -> String {
    if let Some(label) = issue
        .custom
        .get("project_label")
        .and_then(|value| value.as_str())
    {
        let trimmed = label.trim();
        if !trimmed.is_empty() {
            return resolve_standup_partition_key(trimmed, configuration);
        }
    }
    configuration.project_key.clone()
}

/// Return the congregation project display label for an issue.
pub fn issue_project_label(issue: &IssueData, configuration: &ProjectConfiguration) -> String {
    let partition_key = issue_project_partition_key(issue, configuration);
    canonical_standup_project_display_label(&partition_key, configuration)
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

pub fn dedupe_summary_list(summaries: &[String]) -> Vec<String> {
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

#[allow(clippy::too_many_arguments)]
fn compute_issue_rollup_summary(
    root: &Path,
    issue: &IssueData,
    children_by_parent: &HashMap<String, Vec<IssueData>>,
    right_now_texts: &HashMap<String, String>,
    cache: &mut HashMap<String, String>,
) -> Result<String, KanbusError> {
    if let Some(cached) = cache.get(&issue.identifier) {
        return Ok(cached.clone());
    }
    let own_summary = right_now_texts
        .get(&issue.identifier)
        .cloned()
        .unwrap_or_default();
    let children = children_by_parent
        .get(&issue.identifier)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if children.is_empty() {
        cache.insert(issue.identifier.clone(), own_summary.clone());
        return Ok(own_summary);
    }
    let mut child_summaries = Vec::new();
    for child in children {
        child_summaries.push(compute_issue_rollup_summary(
            root,
            child,
            children_by_parent,
            right_now_texts,
            cache,
        )?);
    }
    child_summaries = dedupe_summary_list(&child_summaries);
    if child_summaries.len() == 1 && summaries_near_identical(&child_summaries[0], &own_summary) {
        cache.insert(issue.identifier.clone(), own_summary.clone());
        return Ok(own_summary);
    }
    let mut combined = vec![own_summary.clone()];
    combined.extend(child_summaries);
    let combined = dedupe_summary_list(&combined);
    let result = if combined.len() == 1 {
        combined[0].clone()
    } else {
        reduce_summaries_for_standup_rollup(root, &combined)?
    };
    cache.insert(issue.identifier.clone(), result.clone());
    Ok(result)
}

#[allow(clippy::too_many_arguments)]
fn emit_tree_lines(
    root: &Path,
    issue: &IssueData,
    depth: usize,
    children_by_parent: &HashMap<String, Vec<IssueData>>,
    right_now_texts: &HashMap<String, String>,
    rollup_cache: &mut HashMap<String, String>,
    parent_summary: Option<&str>,
    lines: &mut Vec<String>,
) -> Result<(), KanbusError> {
    let summary = compute_issue_rollup_summary(
        root,
        issue,
        children_by_parent,
        right_now_texts,
        rollup_cache,
    )?;
    let include = parent_summary.is_none()
        || !summaries_near_identical(&summary, parent_summary.unwrap_or(""));
    if include {
        let indent = TREE_INDENT.repeat(depth);
        lines.push(truncate_bullet(&format!("{indent}{summary}")));
    }
    let effective_parent = if include {
        Some(summary.as_str())
    } else {
        parent_summary
    };
    for child in children_by_parent
        .get(&issue.identifier)
        .map(Vec::as_slice)
        .unwrap_or(&[])
    {
        emit_tree_lines(
            root,
            child,
            depth + 1,
            children_by_parent,
            right_now_texts,
            rollup_cache,
            effective_parent,
            lines,
        )?;
    }
    Ok(())
}

/// Build Today (or Momentum) bullets for the requested rollup mode.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when upward rollup summarization fails.
#[allow(clippy::too_many_arguments)]
pub fn roll_up_active_bullets(
    root: &Path,
    active_issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    configuration: &ProjectConfiguration,
    rollup_settings: &StandupRollupSettings,
    prefix_issue_identifiers: bool,
) -> Result<Vec<String>, KanbusError> {
    if active_issues.is_empty() {
        return Ok(Vec::new());
    }
    if rollup_settings.mode == ROLLUP_FLAT {
        return Ok(active_issues
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
            .collect());
    }

    let mut by_partition: HashMap<String, Vec<IssueData>> = HashMap::new();
    for issue in active_issues {
        let partition_key = issue_project_partition_key(issue, configuration);
        by_partition
            .entry(partition_key)
            .or_default()
            .push(issue.clone());
    }

    let mut partition_keys: Vec<String> = by_partition.keys().cloned().collect();
    partition_keys.sort();

    let mut bullets = Vec::new();
    for partition_key in partition_keys {
        let display_label = canonical_standup_project_display_label(&partition_key, configuration);
        let project_issues = by_partition.get(&partition_key).expect("partition");
        let roots = forest_roots(project_issues);
        let children_by_parent = children_map(project_issues);
        let mut rollup_cache: HashMap<String, String> = HashMap::new();

        if rollup_settings.mode == ROLLUP_PROJECT {
            let mut root_summaries = Vec::new();
            for forest_root in &roots {
                root_summaries.push(compute_issue_rollup_summary(
                    root,
                    forest_root,
                    &children_by_parent,
                    right_now_texts,
                    &mut rollup_cache,
                )?);
            }
            root_summaries = dedupe_summary_list(&root_summaries);
            let project_summary = if root_summaries.len() == 1 {
                root_summaries[0].clone()
            } else {
                reduce_summaries_for_standup_rollup(root, &root_summaries)?
            };
            bullets.push(truncate_bullet(&format!(
                "[{display_label}] {project_summary}"
            )));
            continue;
        }

        let prefix = format!("[{display_label}] ");
        for forest_root in roots {
            let mut tree_lines: Vec<String> = Vec::new();
            emit_tree_lines(
                root,
                &forest_root,
                0,
                &children_by_parent,
                right_now_texts,
                &mut rollup_cache,
                None,
                &mut tree_lines,
            )?;
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
    Ok(bullets)
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

fn finishable_stale_pattern() -> &'static Regex {
    static PATTERN: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(
            r"(?i)waiting on review|waiting for review|awaiting review|waiting on deploy|waiting for deploy|deploy toggle|\bmerged\b|ready to merge",
        )
        .expect("valid regex")
    })
}

fn children_by_parent_for_issues(issues: &[IssueData]) -> HashMap<String, Vec<IssueData>> {
    children_map(issues)
}

fn collect_descendant_identifiers(
    root_identifier: &str,
    children_by_parent: &HashMap<String, Vec<IssueData>>,
) -> HashSet<String> {
    let mut descendants = HashSet::new();
    let mut stack: Vec<IssueData> = children_by_parent
        .get(root_identifier)
        .cloned()
        .unwrap_or_default();
    while let Some(child) = stack.pop() {
        if descendants.contains(&child.identifier) {
            continue;
        }
        descendants.insert(child.identifier.clone());
        if let Some(grandchildren) = children_by_parent.get(&child.identifier) {
            stack.extend(grandchildren.iter().cloned());
        }
    }
    descendants
}

fn issue_had_activity_within_lookback(
    issue: &IssueData,
    events: &[Value],
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    let lookback_hours = window_settings.lookback_hours;
    if is_within_lookback(Some(&issue.updated_at), report_time, lookback_hours) {
        return true;
    }
    for event in events {
        if is_event_within_lookback(event, report_time, lookback_hours) {
            return true;
        }
    }
    false
}

fn has_recent_descendant_activity(
    issue: &IssueData,
    issues: &[IssueData],
    events_by_issue: &HashMap<String, Vec<Value>>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    let children_by_parent = children_by_parent_for_issues(issues);
    let descendants = collect_descendant_identifiers(&issue.identifier, &children_by_parent);
    let issues_by_identifier: HashMap<String, IssueData> = issues
        .iter()
        .map(|item| (item.identifier.clone(), item.clone()))
        .collect();
    for descendant_identifier in descendants {
        let descendant = issues_by_identifier.get(&descendant_identifier);
        let Some(descendant) = descendant else {
            continue;
        };
        let events = events_by_issue
            .get(&descendant_identifier)
            .map(Vec::as_slice)
            .unwrap_or(&[]);
        if issue_had_activity_within_lookback(descendant, events, report_time, window_settings) {
            return true;
        }
    }
    false
}

#[allow(clippy::too_many_arguments)]
fn qualifies_for_close_out_stale(
    issue: &IssueData,
    summary: &str,
    issues: &[IssueData],
    events_by_issue: &HashMap<String, Vec<Value>>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> bool {
    if !is_stale_in_progress(issue, report_time, window_settings) {
        return false;
    }
    if !finishable_stale_pattern().is_match(summary) {
        return false;
    }
    !has_recent_descendant_activity(issue, issues, events_by_issue, report_time, window_settings)
}

/// Extract issue identifiers referenced in Close-out bullets.
pub fn close_out_issue_identifiers(bullets: &[String]) -> HashSet<String> {
    let mut identifiers = HashSet::new();
    for bullet in bullets {
        if let Some((prefix, _)) = bullet.split_once(':') {
            let trimmed = prefix.trim();
            if !trimmed.is_empty() {
                identifiers.insert(trimmed.to_string());
            }
        }
    }
    identifiers
}

/// Build Close-out bullets for WIP cards that should finish soon.
#[allow(clippy::too_many_arguments)]
pub fn build_close_out_bullets(
    issues: &[IssueData],
    right_now_texts: &HashMap<String, String>,
    events_by_issue: &HashMap<String, Vec<Value>>,
    report_time: DateTime<Utc>,
    window_settings: &StandupWindowSettings,
) -> Vec<String> {
    let mut ranked_candidates: Vec<(u8, String)> = Vec::new();
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
                Some((
                    0u8,
                    format!(
                        "{}: merged but still in progress — {}",
                        issue.identifier,
                        truncate_bullet(summary)
                    ),
                ))
            } else if ready_to_close_pattern().is_match(summary) {
                Some((
                    1u8,
                    format!("{}: {}", issue.identifier, truncate_bullet(summary)),
                ))
            } else if qualifies_for_close_out_stale(
                issue,
                summary,
                issues,
                events_by_issue,
                report_time,
                window_settings,
            ) {
                Some((
                    3u8,
                    format!(
                        "{}: stale WIP — {}",
                        issue.identifier,
                        truncate_bullet(summary)
                    ),
                ))
            } else {
                None
            }
        } else if issue.status == "blocked" && external_block_pattern().is_match(summary) {
            Some((
                2u8,
                format!("{}: {}", issue.identifier, truncate_bullet(summary)),
            ))
        } else {
            None
        };
        if let Some((priority, text)) = candidate {
            let normalized = normalize_summary_text(&text);
            if seen.contains(&normalized) {
                continue;
            }
            seen.insert(normalized);
            ranked_candidates.push((priority, truncate_bullet(&text)));
        }
    }
    ranked_candidates.sort_by(|left, right| left.0.cmp(&right.0).then(left.1.cmp(&right.1)));
    ranked_candidates
        .into_iter()
        .take(CLOSE_OUT_MAX_BULLETS)
        .map(|(_priority, bullet)| bullet)
        .collect()
}
