//! Policy evaluation context.

use crate::models::{IssueData, ProjectConfiguration};

/// Type of operation triggering policy evaluation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyOperation {
    /// Issue is being created.
    Create,
    /// Issue is being updated.
    Update,
    /// Issue is being closed.
    Close,
    /// Issue is being deleted.
    Delete,
    /// Issue is being viewed.
    View,
    /// Issues are being listed.
    List,
    /// Ready issues are being listed.
    Ready,
}

/// Status transition details.
#[derive(Debug, Clone)]
pub struct StatusTransition {
    /// Status before the transition.
    pub from: String,
    /// Status after the transition.
    pub to: String,
}

/// Context provided to policy evaluation steps.
///
/// Contains all information needed to evaluate policies against
/// a proposed issue state change.
#[derive(Debug, Clone)]
pub struct PolicyContext {
    /// Current issue state on disk.
    pub current_issue: Option<IssueData>,
    /// Proposed issue state after applying updates.
    pub proposed_issue: IssueData,
    /// Status transition details if status is changing.
    pub transition: Option<StatusTransition>,
    /// Type of operation triggering evaluation.
    pub operation: PolicyOperation,
    /// Project configuration.
    pub project_configuration: ProjectConfiguration,
    /// All issues in the project for aggregate checks.
    pub all_issues: Vec<IssueData>,
}

impl PolicyContext {
    /// Get the issue being evaluated (proposed state).
    pub fn issue(&self) -> &IssueData {
        &self.proposed_issue
    }

    /// Check if this is a status transition.
    pub fn is_transition(&self) -> bool {
        self.transition.is_some()
    }

    /// Check if transitioning to a specific status.
    pub fn is_transitioning_to(&self, status: &str) -> bool {
        self.transition
            .as_ref()
            .map(|t| t.to == status)
            .unwrap_or(false)
    }

    /// Check if transitioning from a specific status.
    pub fn is_transitioning_from(&self, status: &str) -> bool {
        self.transition
            .as_ref()
            .map(|t| t.from == status)
            .unwrap_or(false)
    }

    /// Get child issues of the proposed issue.
    pub fn child_issues(&self) -> Vec<&IssueData> {
        let parent_id = &self.proposed_issue.identifier;
        self.all_issues
            .iter()
            .filter(|issue| issue.parent.as_ref() == Some(parent_id))
            .collect()
    }

    /// Get parent issue of the proposed issue.
    pub fn parent_issue(&self) -> Option<&IssueData> {
        let parent_id = self.proposed_issue.parent.as_ref()?;
        self.all_issues
            .iter()
            .find(|issue| &issue.identifier == parent_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{PriorityDefinition, StatusDefinition};
    use chrono::Utc;
    use std::collections::BTreeMap;

    fn sample_issue(identifier: &str, parent: Option<&str>) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: format!("Issue {identifier}"),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
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

    fn sample_project_configuration() -> ProjectConfiguration {
        let mut workflows = BTreeMap::new();
        workflows.insert("default".to_string(), BTreeMap::new());

        let mut priorities = BTreeMap::new();
        priorities.insert(
            2u8,
            PriorityDefinition {
                name: "medium".to_string(),
                color: None,
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
                color: None,
                collapsed: false,
            }],
            categories: Vec::new(),
            sort_order: BTreeMap::new(),
            type_colors: BTreeMap::new(),
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

    fn sample_context(transition: Option<StatusTransition>, parent: Option<&str>) -> PolicyContext {
        let proposed = sample_issue("kanbus-parent", parent);
        let child = sample_issue("kanbus-child", Some("kanbus-parent"));
        let other = sample_issue("kanbus-other", None);
        PolicyContext {
            current_issue: None,
            proposed_issue: proposed,
            transition,
            operation: PolicyOperation::Update,
            project_configuration: sample_project_configuration(),
            all_issues: vec![child, other],
        }
    }

    #[test]
    fn transition_helpers_cover_true_and_false_paths() {
        let with_transition = sample_context(
            Some(StatusTransition {
                from: "open".to_string(),
                to: "in_progress".to_string(),
            }),
            None,
        );
        assert!(with_transition.is_transition());
        assert!(with_transition.is_transitioning_to("in_progress"));
        assert!(with_transition.is_transitioning_from("open"));
        assert!(!with_transition.is_transitioning_to("closed"));
        assert!(!with_transition.is_transitioning_from("blocked"));

        let no_transition = sample_context(None, None);
        assert!(!no_transition.is_transition());
        assert!(!no_transition.is_transitioning_to("open"));
        assert!(!no_transition.is_transitioning_from("open"));
    }

    #[test]
    fn issue_parent_and_child_helpers_return_expected_records() {
        let no_parent = sample_context(None, None);
        let children = no_parent.child_issues();
        assert_eq!(children.len(), 1);
        assert_eq!(children[0].identifier, "kanbus-child");
        assert!(no_parent.parent_issue().is_none());
        assert_eq!(no_parent.issue().identifier, "kanbus-parent");

        let with_parent = sample_context(None, Some("kanbus-other"));
        let parent = with_parent.parent_issue().expect("parent should resolve");
        assert_eq!(parent.identifier, "kanbus-other");
    }
}
