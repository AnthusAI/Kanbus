//! Right-now CLI listing and formatting.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;

use chrono::{DateTime, SecondsFormat, Utc};
use serde::Serialize;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_listing::list_issues;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueData, ProjectConfiguration};
use crate::queries::sort_issues_by_recently_updated;
use crate::right_now::get_right_now_summary;

const RIGHT_NOW_PLACEHOLDER: &str = "(no right-now summary)";
const DEFAULT_RIGHT_NOW_LIMIT: usize = 30;
const CANNOT_COMBINE_ALL_WITH_LIMIT: &str = "cannot combine --all with --limit";
const CANNOT_COMBINE_ALL_WITH_ISSUE_IDENTIFIERS: &str =
    "cannot combine --all with issue identifiers";
const NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS: &str =
    "--no-recursive requires one or more issue identifiers";

/// Options for the right-now CLI command.
#[derive(Debug, Clone)]
pub struct RightNowCommandOptions {
    /// Maximum number of issues to include after sorting.
    pub limit: Option<usize>,
    /// Whether to render a hierarchical tree.
    pub tree: bool,
    /// Whether tree nodes default to expanded markers.
    pub expanded: bool,
    /// Whether tree nodes default to collapsed markers.
    pub collapsed: bool,
    /// Whether to omit right-now summaries.
    pub raw: bool,
    /// Whether to emit JSON output.
    pub as_json: bool,
    /// Whether to list every issue without the default cap.
    pub show_all: bool,
    /// Whether to include descendants of selected issues.
    pub recursive: bool,
    /// Optional issue identifiers to select.
    pub issue_ids: Vec<String>,
}

/// Default right-now command options: hierarchical tree with recursive descendants.
impl Default for RightNowCommandOptions {
    fn default() -> Self {
        Self {
            limit: None,
            tree: true,
            expanded: false,
            collapsed: false,
            raw: false,
            as_json: false,
            show_all: false,
            recursive: true,
            issue_ids: Vec::new(),
        }
    }
}

/// List recently-updated issues for the right-now CLI command.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `options` - Right-now command options.
///
/// # Errors
/// Returns `KanbusError` when issue listing fails or options are invalid.
pub fn run_right_now_command(
    root: &Path,
    options: &RightNowCommandOptions,
) -> Result<String, KanbusError> {
    validate_right_now_options(options)?;
    let mut issues = select_right_now_issues(root, options)?;
    issues = sort_issues_by_recently_updated(issues);
    let effective_limit = effective_right_now_limit(options);
    if effective_limit > 0 {
        issues.truncate(effective_limit);
    }
    let configuration = load_configuration(root);
    let tree_expanded = resolve_tree_expanded(options, configuration.as_ref());
    if options.as_json {
        if options.tree {
            let roots = build_right_now_tree(&issues);
            let payload: Vec<RightNowTreeJsonEntry> = roots
                .iter()
                .map(|node| serialize_tree_json_node(node, options.raw))
                .collect();
            let output = serde_json::to_string_pretty(&payload)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            return Ok(format!("{output}\n"));
        }
        let payload: Vec<RightNowFlatJsonEntry> = issues
            .iter()
            .map(|issue| serialize_flat_json_entry(issue, options.raw))
            .collect();
        let output = serde_json::to_string_pretty(&payload)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        return Ok(format!("{output}\n"));
    }
    if options.tree {
        let roots = build_right_now_tree(&issues);
        let mut lines = Vec::new();
        for node in &roots {
            render_tree_node(node, tree_expanded, options.raw, 0, &mut lines);
        }
        if lines.is_empty() {
            return Ok(String::new());
        }
        lines.push(String::new());
        return Ok(lines.join("\n"));
    }
    let mut lines = Vec::new();
    for issue in &issues {
        render_flat_issue(issue, options.raw, &mut lines);
    }
    if lines.is_empty() {
        return Ok(String::new());
    }
    lines.push(String::new());
    Ok(lines.join("\n"))
}

fn validate_right_now_options(options: &RightNowCommandOptions) -> Result<(), KanbusError> {
    if options.show_all && options.limit.is_some() {
        return Err(KanbusError::IssueOperation(
            CANNOT_COMBINE_ALL_WITH_LIMIT.to_string(),
        ));
    }
    if options.show_all && !options.issue_ids.is_empty() {
        return Err(KanbusError::IssueOperation(
            CANNOT_COMBINE_ALL_WITH_ISSUE_IDENTIFIERS.to_string(),
        ));
    }
    if !options.recursive && options.issue_ids.is_empty() {
        return Err(KanbusError::IssueOperation(
            NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS.to_string(),
        ));
    }
    Ok(())
}

fn effective_right_now_limit(options: &RightNowCommandOptions) -> usize {
    if options.show_all {
        return 0;
    }
    if !options.issue_ids.is_empty() {
        return options.limit.unwrap_or(0);
    }
    options.limit.unwrap_or(DEFAULT_RIGHT_NOW_LIMIT)
}

fn select_right_now_issues(
    root: &Path,
    options: &RightNowCommandOptions,
) -> Result<Vec<IssueData>, KanbusError> {
    let issues = list_issues(
        root,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        &[],
        true,
        false,
    )?;
    if options.issue_ids.is_empty() {
        return Ok(issues);
    }
    let mut issues_by_identifier: HashMap<String, IssueData> = issues
        .into_iter()
        .map(|issue| (issue.identifier.clone(), issue))
        .collect();
    let mut selected: HashSet<String> = HashSet::new();
    for raw_identifier in &options.issue_ids {
        let lookup = load_issue_from_project(root, raw_identifier)?;
        let identifier = lookup.issue.identifier.clone();
        issues_by_identifier
            .entry(identifier.clone())
            .or_insert(lookup.issue);
        selected.insert(identifier);
    }
    if options.recursive {
        let mut children_by_parent: HashMap<String, Vec<String>> = HashMap::new();
        for issue in issues_by_identifier.values() {
            if let Some(parent) = &issue.parent {
                children_by_parent
                    .entry(parent.clone())
                    .or_default()
                    .push(issue.identifier.clone());
            }
        }
        let mut queue: Vec<String> = selected.iter().cloned().collect();
        while let Some(current) = queue.pop() {
            if let Some(children) = children_by_parent.get(&current) {
                for child_identifier in children {
                    if selected.insert(child_identifier.clone()) {
                        queue.push(child_identifier.clone());
                    }
                }
            }
        }
    }
    Ok(issues_by_identifier
        .into_iter()
        .filter(|(identifier, _)| selected.contains(identifier))
        .map(|(_, issue)| issue)
        .collect())
}

fn load_configuration(root: &Path) -> Option<ProjectConfiguration> {
    let configuration_path = get_configuration_path(root).ok()?;
    load_project_configuration(&configuration_path).ok()
}

fn resolve_tree_expanded(
    options: &RightNowCommandOptions,
    configuration: Option<&ProjectConfiguration>,
) -> bool {
    if options.expanded {
        return true;
    }
    if options.collapsed {
        return false;
    }
    configuration
        .map(|value| value.right_now.default_tree_expanded)
        .unwrap_or(false)
}

fn format_updated_at(value: DateTime<Utc>) -> String {
    value.to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn render_flat_issue(issue: &IssueData, raw: bool, lines: &mut Vec<String>) {
    lines.push(format!(
        "{}  {}  {}",
        format_updated_at(issue.updated_at),
        issue.identifier,
        issue.title
    ));
    if raw {
        return;
    }
    let summary_text = get_right_now_summary(issue).unwrap_or(RIGHT_NOW_PLACEHOLDER);
    lines.push(format!("    {summary_text}"));
}

/// Hierarchy node for right-now tree rendering.
#[derive(Debug, Clone)]
pub struct RightNowTreeNode {
    /// Issue represented by this node.
    pub issue: IssueData,
    /// Child nodes in display order.
    pub children: Vec<RightNowTreeNode>,
}

fn build_right_now_tree(issues: &[IssueData]) -> Vec<RightNowTreeNode> {
    let identifiers: HashSet<&str> = issues
        .iter()
        .map(|issue| issue.identifier.as_str())
        .collect();
    let mut children_by_parent: BTreeMap<&str, Vec<IssueData>> = BTreeMap::new();
    for issue in issues {
        if let Some(parent) = issue.parent.as_deref() {
            children_by_parent
                .entry(parent)
                .or_default()
                .push(issue.clone());
        }
    }
    for children in children_by_parent.values_mut() {
        *children = sort_issues_by_recently_updated(std::mem::take(children));
    }
    let mut roots: Vec<IssueData> = issues
        .iter()
        .filter(|issue| {
            issue
                .parent
                .as_deref()
                .is_none_or(|parent| !identifiers.contains(parent))
        })
        .cloned()
        .collect();
    roots = sort_issues_by_recently_updated(roots);

    fn build_node(
        issue: IssueData,
        children_by_parent: &BTreeMap<&str, Vec<IssueData>>,
    ) -> RightNowTreeNode {
        let children = children_by_parent
            .get(issue.identifier.as_str())
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(|child| build_node(child, children_by_parent))
            .collect();
        RightNowTreeNode { issue, children }
    }

    roots
        .into_iter()
        .map(|issue| build_node(issue, &children_by_parent))
        .collect()
}

fn collapse_marker(tree_expanded: bool) -> &'static str {
    if tree_expanded {
        "[-]"
    } else {
        "[+]"
    }
}

fn render_tree_node(
    node: &RightNowTreeNode,
    tree_expanded: bool,
    raw: bool,
    depth: usize,
    lines: &mut Vec<String>,
) {
    let indent = "  ".repeat(depth);
    let marker = collapse_marker(tree_expanded);
    let issue = &node.issue;
    lines.push(format!(
        "{indent}{marker} {}  {}  {}",
        format_updated_at(issue.updated_at),
        issue.identifier,
        issue.title
    ));
    if !raw {
        let summary_text = get_right_now_summary(issue).unwrap_or(RIGHT_NOW_PLACEHOLDER);
        lines.push(format!("{indent}    {summary_text}"));
    }
    for child in &node.children {
        render_tree_node(child, tree_expanded, raw, depth + 1, lines);
    }
}

#[derive(Debug, Serialize)]
struct RightNowFlatJsonEntry {
    id: String,
    title: String,
    #[serde(rename = "type")]
    issue_type: String,
    status: String,
    updated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    right_now_summary: Option<Option<String>>,
    parent: Option<String>,
}

fn serialize_flat_json_entry(issue: &IssueData, raw: bool) -> RightNowFlatJsonEntry {
    RightNowFlatJsonEntry {
        id: issue.identifier.clone(),
        title: issue.title.clone(),
        issue_type: issue.issue_type.clone(),
        status: issue.status.clone(),
        updated_at: format_updated_at(issue.updated_at),
        right_now_summary: if raw {
            None
        } else {
            Some(get_right_now_summary(issue).map(str::to_string))
        },
        parent: issue.parent.clone(),
    }
}

#[derive(Debug, Serialize)]
struct RightNowTreeJsonEntry {
    id: String,
    title: String,
    updated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    right_now_summary: Option<Option<String>>,
    children: Vec<RightNowTreeJsonEntry>,
}

fn serialize_tree_json_node(node: &RightNowTreeNode, raw: bool) -> RightNowTreeJsonEntry {
    RightNowTreeJsonEntry {
        id: node.issue.identifier.clone(),
        title: node.issue.title.clone(),
        updated_at: format_updated_at(node.issue.updated_at),
        right_now_summary: if raw {
            None
        } else {
            Some(get_right_now_summary(&node.issue).map(str::to_string))
        },
        children: node
            .children
            .iter()
            .map(|child| serialize_tree_json_node(child, raw))
            .collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::IssueData;
    use chrono::{TimeZone, Utc};
    use std::collections::BTreeMap;

    fn make_issue(id: &str, title: &str) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: title.to_string(),
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
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn default_options_use_board_cap_tree_and_recursive() {
        let options = RightNowCommandOptions::default();
        assert_eq!(options.limit, None);
        assert!(options.tree);
        assert!(!options.expanded);
        assert!(!options.collapsed);
        assert!(!options.raw);
        assert!(!options.as_json);
        assert!(!options.show_all);
        assert!(options.recursive);
        assert!(options.issue_ids.is_empty());
        assert_eq!(effective_right_now_limit(&options), DEFAULT_RIGHT_NOW_LIMIT);
    }

    #[test]
    fn resolve_tree_expanded_prefers_flags_then_configuration() {
        let expanded = RightNowCommandOptions {
            expanded: true,
            ..RightNowCommandOptions::default()
        };
        assert!(resolve_tree_expanded(&expanded, None));
        let collapsed = RightNowCommandOptions {
            collapsed: true,
            ..RightNowCommandOptions::default()
        };
        assert!(!resolve_tree_expanded(&collapsed, None));
        assert!(!resolve_tree_expanded(
            &RightNowCommandOptions::default(),
            None
        ));
    }

    #[test]
    fn format_updated_at_uses_millis_and_zulu() {
        let stamp = Utc.with_ymd_and_hms(2026, 9, 2, 12, 0, 0).unwrap();
        assert_eq!(format_updated_at(stamp), "2026-09-02T12:00:00.000Z");
    }

    #[test]
    fn render_flat_issue_includes_placeholder_and_raw_omits_summary() {
        let issue = make_issue("kanbus-flat", "Flat title");
        let mut lines = Vec::new();
        render_flat_issue(&issue, false, &mut lines);
        assert_eq!(lines.len(), 2);
        assert!(lines[1].contains(RIGHT_NOW_PLACEHOLDER));
        lines.clear();
        render_flat_issue(&issue, true, &mut lines);
        assert_eq!(lines.len(), 1);
    }

    #[test]
    fn serialize_flat_json_entry_omits_summary_when_raw() {
        let issue = make_issue("kanbus-json", "JSON title");
        let raw = serialize_flat_json_entry(&issue, true);
        assert!(raw.right_now_summary.is_none());
        let with_summary = serialize_flat_json_entry(&issue, false);
        assert_eq!(with_summary.right_now_summary, Some(None));
    }

    #[test]
    fn validate_right_now_options_rejects_conflicts() {
        let all_with_limit = RightNowCommandOptions {
            show_all: true,
            limit: Some(2),
            ..RightNowCommandOptions::default()
        };
        let error = validate_right_now_options(&all_with_limit).expect_err("limit");
        assert_eq!(error.to_string(), CANNOT_COMBINE_ALL_WITH_LIMIT);
        let all_with_ids = RightNowCommandOptions {
            show_all: true,
            issue_ids: vec!["kanbus-a".to_string()],
            ..RightNowCommandOptions::default()
        };
        let error = validate_right_now_options(&all_with_ids).expect_err("ids");
        assert_eq!(error.to_string(), CANNOT_COMBINE_ALL_WITH_ISSUE_IDENTIFIERS);
        let no_recursive = RightNowCommandOptions {
            recursive: false,
            ..RightNowCommandOptions::default()
        };
        let error = validate_right_now_options(&no_recursive).expect_err("no-recursive");
        assert_eq!(error.to_string(), NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS);
        validate_right_now_options(&RightNowCommandOptions::default()).expect("ok");
    }

    #[test]
    fn effective_right_now_limit_uses_selection_policy() {
        assert_eq!(
            effective_right_now_limit(&RightNowCommandOptions::default()),
            DEFAULT_RIGHT_NOW_LIMIT
        );
        let show_all = RightNowCommandOptions {
            show_all: true,
            ..RightNowCommandOptions::default()
        };
        assert_eq!(effective_right_now_limit(&show_all), 0);
        let selected = RightNowCommandOptions {
            issue_ids: vec!["kanbus-a".to_string()],
            ..RightNowCommandOptions::default()
        };
        assert_eq!(effective_right_now_limit(&selected), 0);
        let selected_limited = RightNowCommandOptions {
            issue_ids: vec!["kanbus-a".to_string()],
            limit: Some(1),
            ..RightNowCommandOptions::default()
        };
        assert_eq!(effective_right_now_limit(&selected_limited), 1);
        let limited = RightNowCommandOptions {
            limit: Some(5),
            ..RightNowCommandOptions::default()
        };
        assert_eq!(effective_right_now_limit(&limited), 5);
    }
}
