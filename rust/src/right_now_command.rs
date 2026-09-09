//! Right-now CLI listing and formatting.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;

use chrono::{DateTime, SecondsFormat, Utc};
use serde::Serialize;

use crate::config_loader::load_project_configuration;
use crate::console_backend::active_right_now_tree;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_listing::list_issues;
use crate::issue_lookup::load_issue_from_project;
use crate::models::{IssueData, ProjectConfiguration};
use crate::queries::sort_issues_by_recently_updated;
use crate::right_now::{
    ensure_right_now_summaries, ensure_right_now_summary_subtrees, get_right_now_summary,
    DEFAULT_RIGHT_NOW_STATUS,
};

const RIGHT_NOW_PLACEHOLDER: &str = "(no right-now summary)";
const DEFAULT_RIGHT_NOW_LIMIT: usize = 30;
const RIGHT_NOW_STATUS_ALL: &str = "all";
const EMPTY_STATUS_FILTER: &str = "status filter must not be empty";
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
    /// Status filter. `None` defaults to in-progress for board listings.
    pub status: Option<String>,
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
            status: None,
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
    if !options.raw {
        if !options.issue_ids.is_empty() || options.status.is_some() {
            if effective_limit > 0 {
                issues.truncate(effective_limit);
            }
            let identifiers: Vec<String> = issues
                .iter()
                .map(|issue| issue.identifier.clone())
                .collect();
            ensure_right_now_summaries(root, &identifiers);
            issues = reload_right_now_issues(root, issues);
        } else {
            let all_issues = list_issues(
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
            let (roots, selected_identifiers) = active_right_now_tree(&all_issues);
            ensure_right_now_summary_subtrees(root, &roots, &selected_identifiers);
            let issues_by_identifier: HashMap<String, IssueData> = all_issues
                .into_iter()
                .map(|issue| (issue.identifier.clone(), issue))
                .collect();
            let expanded_issues =
                expand_active_right_now_issues(root, &selected_identifiers, &issues_by_identifier);
            issues = sort_issues_by_recently_updated(expanded_issues);
            if effective_limit > 0 {
                issues.truncate(effective_limit);
            }
        }
    } else if effective_limit > 0 {
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

fn reload_right_now_issues(root: &Path, issues: Vec<IssueData>) -> Vec<IssueData> {
    let mut reloaded = Vec::new();
    for issue in issues {
        match load_issue_from_project(root, &issue.identifier) {
            Ok(lookup) => reloaded.push(lookup.issue),
            Err(_) => reloaded.push(issue),
        }
    }
    reloaded
}

fn expand_active_right_now_issues(
    root: &Path,
    selected_identifiers: &HashSet<String>,
    issues_by_identifier: &HashMap<String, IssueData>,
) -> Vec<IssueData> {
    let mut expanded_issues = Vec::new();
    for identifier in selected_identifiers {
        match load_issue_from_project(root, identifier) {
            Ok(lookup) => expanded_issues.push(lookup.issue),
            Err(_) => {
                if let Some(fallback) = issues_by_identifier.get(identifier) {
                    expanded_issues.push(fallback.clone());
                }
            }
        }
    }
    expanded_issues
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
    resolve_right_now_statuses(options.status.as_deref(), !options.issue_ids.is_empty())?;
    Ok(())
}

/// Return allowed statuses, or `None` to include every status.
///
/// # Errors
///
/// Returns `KanbusError` when the status filter is empty.
fn resolve_right_now_statuses(
    status_option: Option<&str>,
    has_issue_identifiers: bool,
) -> Result<Option<HashSet<String>>, KanbusError> {
    match status_option {
        None => {
            if has_issue_identifiers {
                Ok(None)
            } else {
                Ok(Some(HashSet::from([DEFAULT_RIGHT_NOW_STATUS.to_string()])))
            }
        }
        Some(raw) => {
            let tokens: Vec<String> = raw
                .split(',')
                .map(str::trim)
                .filter(|token| !token.is_empty())
                .map(str::to_string)
                .collect();
            if tokens.is_empty() {
                return Err(KanbusError::IssueOperation(EMPTY_STATUS_FILTER.to_string()));
            }
            if tokens.iter().any(|token| token == RIGHT_NOW_STATUS_ALL) {
                return Ok(None);
            }
            Ok(Some(tokens.into_iter().collect()))
        }
    }
}

/// Filter issues by the resolved Now status set.
///
/// # Errors
///
/// Returns `KanbusError` when the status filter is empty.
fn filter_right_now_issues_by_status(
    issues: Vec<IssueData>,
    options: &RightNowCommandOptions,
) -> Result<Vec<IssueData>, KanbusError> {
    let allowed =
        resolve_right_now_statuses(options.status.as_deref(), !options.issue_ids.is_empty())?;
    Ok(match allowed {
        None => issues,
        Some(statuses) => issues
            .into_iter()
            .filter(|issue| statuses.contains(&issue.status))
            .collect(),
    })
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
        return filter_right_now_issues_by_status(issues, options);
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
    filter_right_now_issues_by_status(
        issues_by_identifier
            .into_iter()
            .filter(|(identifier, _)| selected.contains(identifier))
            .map(|(_, issue)| issue)
            .collect(),
        options,
    )
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
    use serial_test::serial;
    use std::collections::{BTreeMap, HashMap, HashSet};
    use std::fs;
    use tempfile::TempDir;

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
            agent: None,
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
    fn resolve_right_now_statuses_defaults_to_in_progress_for_board() {
        let statuses = resolve_right_now_statuses(None, false).expect("ok");
        assert_eq!(
            statuses,
            Some(HashSet::from([DEFAULT_RIGHT_NOW_STATUS.to_string()]))
        );
        assert!(resolve_right_now_statuses(None, true)
            .expect("named")
            .is_none());
        assert!(resolve_right_now_statuses(Some("all"), false)
            .expect("all")
            .is_none());
        let selected = resolve_right_now_statuses(Some("in_progress,open"), false)
            .expect("csv")
            .expect("set");
        assert!(selected.contains("in_progress"));
        assert!(selected.contains("open"));
        let error = resolve_right_now_statuses(Some(" , "), false).expect_err("empty");
        assert_eq!(error.to_string(), EMPTY_STATUS_FILTER);
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

    #[test]
    #[serial]
    fn cli_now_recursively_backfills_every_rendered_tree_node() {
        let previous_mock = std::env::var("KANBUS_TEST_AI_MOCK").ok();
        let previous_no_daemon = std::env::var("KANBUS_NO_DAEMON").ok();
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        std::env::set_var("KANBUS_NO_DAEMON", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\nai:\n  provider: litellm\n  model: gpt-4o-mini\nright_now:\n  enabled: true\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues");

        let parent = make_issue("kanbus-parent", "Parent");
        let mut discovery_child = make_issue("kanbus-discovery", "Discovery child");
        discovery_child.status = "discovery".to_string();
        discovery_child.parent = Some(parent.identifier.clone());
        let mut active_child = make_issue("kanbus-active", "Active child");
        active_child.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active_child.parent = Some(parent.identifier.clone());
        for issue in [&parent, &discovery_child, &active_child] {
            fs::write(
                issues_dir.join(format!("{}.json", issue.identifier)),
                serde_json::to_vec(issue).expect("serialize issue"),
            )
            .expect("write issue");
        }

        let output = run_right_now_command(
            temp_dir.path(),
            &RightNowCommandOptions {
                issue_ids: vec![parent.identifier.clone()],
                expanded: true,
                ..RightNowCommandOptions::default()
            },
        )
        .expect("run now");

        for identifier in ["kanbus-parent", "kanbus-discovery", "kanbus-active"] {
            let expected = crate::right_now::mock_right_now_summary_text(identifier);
            assert!(output.contains(&expected));
            assert_eq!(
                load_issue_from_project(temp_dir.path(), identifier)
                    .expect("reload issue")
                    .issue
                    .right_now_summary
                    .as_deref(),
                Some(expected.as_str())
            );
        }

        match previous_mock {
            Some(value) => std::env::set_var("KANBUS_TEST_AI_MOCK", value),
            None => std::env::remove_var("KANBUS_TEST_AI_MOCK"),
        }
        match previous_no_daemon {
            Some(value) => std::env::set_var("KANBUS_NO_DAEMON", value),
            None => std::env::remove_var("KANBUS_NO_DAEMON"),
        }
    }

    #[test]
    #[serial]
    fn cli_now_default_board_uses_active_tree_expansion() {
        let previous_mock = std::env::var("KANBUS_TEST_AI_MOCK").ok();
        let previous_no_daemon = std::env::var("KANBUS_NO_DAEMON").ok();
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        std::env::set_var("KANBUS_NO_DAEMON", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\nai:\n  provider: litellm\n  model: gpt-4o-mini\nright_now:\n  enabled: true\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues");

        let parent = make_issue("kanbus-board-parent", "Board parent");
        let mut discovery_child = make_issue("kanbus-board-discovery", "Board discovery");
        discovery_child.status = "discovery".to_string();
        discovery_child.parent = Some(parent.identifier.clone());
        let mut active_child = make_issue("kanbus-board-active", "Board active");
        active_child.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active_child.parent = Some(parent.identifier.clone());
        for issue in [&parent, &discovery_child, &active_child] {
            fs::write(
                issues_dir.join(format!("{}.json", issue.identifier)),
                serde_json::to_vec(issue).expect("serialize issue"),
            )
            .expect("write issue");
        }

        let output = run_right_now_command(
            temp_dir.path(),
            &RightNowCommandOptions {
                expanded: true,
                ..RightNowCommandOptions::default()
            },
        )
        .expect("run now");

        for identifier in [
            "kanbus-board-parent",
            "kanbus-board-discovery",
            "kanbus-board-active",
        ] {
            assert!(output.contains(identifier));
        }

        match previous_mock {
            Some(value) => std::env::set_var("KANBUS_TEST_AI_MOCK", value),
            None => std::env::remove_var("KANBUS_TEST_AI_MOCK"),
        }
        match previous_no_daemon {
            Some(value) => std::env::set_var("KANBUS_NO_DAEMON", value),
            None => std::env::remove_var("KANBUS_NO_DAEMON"),
        }
    }

    #[test]
    fn run_right_now_command_returns_empty_output_when_board_has_no_matches() {
        let previous_no_daemon = std::env::var("KANBUS_NO_DAEMON").ok();
        std::env::set_var("KANBUS_NO_DAEMON", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\nright_now:\n  enabled: true\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues");
        let open_issue = make_issue("kanbus-open-only", "Open only");
        fs::write(
            issues_dir.join(format!("{}.json", open_issue.identifier)),
            serde_json::to_vec(&open_issue).expect("serialize issue"),
        )
        .expect("write issue");

        let tree_output = run_right_now_command(
            temp_dir.path(),
            &RightNowCommandOptions {
                raw: true,
                ..RightNowCommandOptions::default()
            },
        )
        .expect("tree output");
        assert!(tree_output.is_empty());

        let flat_output = run_right_now_command(
            temp_dir.path(),
            &RightNowCommandOptions {
                tree: false,
                raw: true,
                ..RightNowCommandOptions::default()
            },
        )
        .expect("flat output");
        assert!(flat_output.is_empty());

        match previous_no_daemon {
            Some(value) => std::env::set_var("KANBUS_NO_DAEMON", value),
            None => std::env::remove_var("KANBUS_NO_DAEMON"),
        }
    }

    #[test]
    #[serial]
    fn cli_now_filtered_listing_keeps_cached_issue_on_reload_failure() {
        let previous_mock = std::env::var("KANBUS_TEST_AI_MOCK").ok();
        let previous_no_daemon = std::env::var("KANBUS_NO_DAEMON").ok();
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        std::env::set_var("KANBUS_NO_DAEMON", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\nai:\n  provider: litellm\n  model: gpt-4o-mini\nright_now:\n  enabled: true\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues");
        let mut active = make_issue("kanbus-filtered-reload", "Filtered reload");
        active.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        fs::write(
            issues_dir.join(format!("{}.json", active.identifier)),
            serde_json::to_vec(&active).expect("serialize issue"),
        )
        .expect("write issue");

        let output = run_right_now_command(
            temp_dir.path(),
            &RightNowCommandOptions {
                tree: false,
                status: Some("all".to_string()),
                ..RightNowCommandOptions::default()
            },
        )
        .expect("run now");

        assert!(output.contains("kanbus-filtered-reload"));

        match previous_mock {
            Some(value) => std::env::set_var("KANBUS_TEST_AI_MOCK", value),
            None => std::env::remove_var("KANBUS_TEST_AI_MOCK"),
        }
        match previous_no_daemon {
            Some(value) => std::env::set_var("KANBUS_NO_DAEMON", value),
            None => std::env::remove_var("KANBUS_NO_DAEMON"),
        }
    }

    #[test]
    fn reload_right_now_issues_keeps_cached_issue_on_lookup_error() {
        let temp_dir = TempDir::new().expect("tempdir");
        fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        fs::create_dir_all(&issues_dir).expect("create issues");
        let issue = make_issue("kanbus-reload", "Reload fallback");
        fs::write(
            issues_dir.join(format!("{}.json", issue.identifier)),
            serde_json::to_vec(&issue).expect("serialize issue"),
        )
        .expect("write issue");
        fs::remove_file(issues_dir.join(format!("{}.json", issue.identifier))).expect("remove");

        let reloaded = reload_right_now_issues(temp_dir.path(), vec![issue.clone()]);
        assert_eq!(reloaded.len(), 1);
        assert_eq!(reloaded[0].identifier, issue.identifier);
    }

    #[test]
    fn expand_active_right_now_issues_uses_listing_cache_on_lookup_error() {
        let temp_dir = TempDir::new().expect("tempdir");
        let issue = make_issue("kanbus-cache-fallback", "Cache fallback");
        let mut selected = HashSet::new();
        selected.insert(issue.identifier.clone());
        let mut cache = HashMap::new();
        cache.insert(issue.identifier.clone(), issue.clone());

        let expanded = expand_active_right_now_issues(temp_dir.path(), &selected, &cache);

        assert_eq!(expanded.len(), 1);
        assert_eq!(expanded[0].identifier, issue.identifier);
    }
}
