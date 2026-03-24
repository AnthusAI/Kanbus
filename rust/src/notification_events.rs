//! Real-time notification events for issue operations.

use crate::models::IssueData;
use serde::{Deserialize, Serialize};

/// Events that can be broadcast to connected clients for real-time updates.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum NotificationEvent {
    /// An issue was created.
    IssueCreated {
        issue_id: String,
        issue_data: IssueData,
    },
    /// An issue was updated.
    IssueUpdated {
        issue_id: String,
        #[serde(default, skip_serializing_if = "Vec::is_empty")]
        fields_changed: Vec<String>,
        issue_data: IssueData,
    },
    /// An issue was deleted.
    IssueDeleted { issue_id: String },
    /// An issue was focused (for UI highlighting).
    IssueFocused {
        issue_id: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        user: Option<String>,
        /// Optional comment ID to scroll to within the focused issue.
        #[serde(skip_serializing_if = "Option::is_none")]
        comment_id: Option<String>,
    },
    /// UI control command to manipulate console UI state.
    UiControl { action: UiControlAction },
}

/// UI control actions that can be sent to the console frontend.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "action", rename_all = "snake_case")]
pub enum UiControlAction {
    /// Clear the current focus filter.
    ClearFocus,
    /// Switch to a different view mode.
    SetViewMode { mode: String },
    /// Set the search query filter.
    SetSearch { query: String },
    /// Maximize the detail panel.
    MaximizeDetail,
    /// Restore the detail panel to normal size.
    RestoreDetail,
    /// Close the detail panel.
    CloseDetail,
    /// Toggle the settings panel.
    ToggleSettings,
    /// Update a specific setting value.
    SetSetting { key: String, value: String },
    /// Collapse a board column.
    CollapseColumn { column_name: String },
    /// Expand a board column.
    ExpandColumn { column_name: String },
    /// Select and navigate to an issue.
    SelectIssue { issue_id: String },
    /// Reload the entire page.
    ReloadPage,
}

impl NotificationEvent {
    /// Get the issue ID associated with this event, if applicable.
    pub fn issue_id(&self) -> Option<&str> {
        match self {
            NotificationEvent::IssueCreated { issue_id, .. } => Some(issue_id),
            NotificationEvent::IssueUpdated { issue_id, .. } => Some(issue_id),
            NotificationEvent::IssueDeleted { issue_id } => Some(issue_id),
            NotificationEvent::IssueFocused { issue_id, .. } => Some(issue_id),
            NotificationEvent::UiControl { .. } => None,
        }
    }

    /// Get a human-readable description of this event.
    pub fn description(&self) -> String {
        match self {
            NotificationEvent::IssueCreated { issue_id, .. } => {
                format!("Issue {} created", issue_id)
            }
            NotificationEvent::IssueUpdated {
                issue_id,
                fields_changed,
                ..
            } => {
                if fields_changed.is_empty() {
                    format!("Issue {} updated", issue_id)
                } else {
                    format!("Issue {} updated: {}", issue_id, fields_changed.join(", "))
                }
            }
            NotificationEvent::IssueDeleted { issue_id } => {
                format!("Issue {} deleted", issue_id)
            }
            NotificationEvent::IssueFocused { issue_id, user, .. } => {
                if let Some(u) = user {
                    format!("Issue {} focused by {}", issue_id, u)
                } else {
                    format!("Issue {} focused", issue_id)
                }
            }
            NotificationEvent::UiControl { action } => {
                format!("UI control: {:?}", action)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::collections::BTreeMap;

    fn sample_issue(id: &str) -> IssueData {
        let now = Utc::now();
        IssueData {
            identifier: id.to_string(),
            title: "Test issue".to_string(),
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
            created_at: now,
            updated_at: now,
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn issue_id_returns_expected_values_for_all_event_types() {
        let issue = sample_issue("kanbus-1");
        let created = NotificationEvent::IssueCreated {
            issue_id: "kanbus-1".to_string(),
            issue_data: issue.clone(),
        };
        let updated = NotificationEvent::IssueUpdated {
            issue_id: "kanbus-1".to_string(),
            fields_changed: vec!["status".to_string()],
            issue_data: issue,
        };
        let deleted = NotificationEvent::IssueDeleted {
            issue_id: "kanbus-1".to_string(),
        };
        let focused = NotificationEvent::IssueFocused {
            issue_id: "kanbus-1".to_string(),
            user: Some("agent".to_string()),
            comment_id: None,
        };
        let ui = NotificationEvent::UiControl {
            action: UiControlAction::ReloadPage,
        };

        assert_eq!(created.issue_id(), Some("kanbus-1"));
        assert_eq!(updated.issue_id(), Some("kanbus-1"));
        assert_eq!(deleted.issue_id(), Some("kanbus-1"));
        assert_eq!(focused.issue_id(), Some("kanbus-1"));
        assert_eq!(ui.issue_id(), None);
    }

    #[test]
    fn description_formats_event_variants() {
        let issue = sample_issue("kanbus-2");
        let updated_no_fields = NotificationEvent::IssueUpdated {
            issue_id: "kanbus-2".to_string(),
            fields_changed: Vec::new(),
            issue_data: issue.clone(),
        };
        let updated_with_fields = NotificationEvent::IssueUpdated {
            issue_id: "kanbus-2".to_string(),
            fields_changed: vec!["status".to_string(), "priority".to_string()],
            issue_data: issue,
        };
        let focused_no_user = NotificationEvent::IssueFocused {
            issue_id: "kanbus-2".to_string(),
            user: None,
            comment_id: None,
        };
        let ui = NotificationEvent::UiControl {
            action: UiControlAction::SetSearch {
                query: "hello".to_string(),
            },
        };

        assert_eq!(updated_no_fields.description(), "Issue kanbus-2 updated");
        assert_eq!(
            updated_with_fields.description(),
            "Issue kanbus-2 updated: status, priority"
        );
        assert_eq!(focused_no_user.description(), "Issue kanbus-2 focused");
        assert!(ui.description().starts_with("UI control: "));
    }

    #[test]
    fn description_covers_created_deleted_and_focused_with_user() {
        let issue = sample_issue("kanbus-3");
        let created = NotificationEvent::IssueCreated {
            issue_id: "kanbus-3".to_string(),
            issue_data: issue.clone(),
        };
        let deleted = NotificationEvent::IssueDeleted {
            issue_id: "kanbus-3".to_string(),
        };
        let focused = NotificationEvent::IssueFocused {
            issue_id: "kanbus-3".to_string(),
            user: Some("pair".to_string()),
            comment_id: Some("cmt-1".to_string()),
        };

        assert_eq!(created.description(), "Issue kanbus-3 created");
        assert_eq!(deleted.description(), "Issue kanbus-3 deleted");
        assert_eq!(focused.description(), "Issue kanbus-3 focused by pair");
    }

    #[test]
    fn ui_control_variants_serialize_with_expected_action_tags() {
        let cases = vec![
            (UiControlAction::ClearFocus, "clear_focus"),
            (
                UiControlAction::SetViewMode {
                    mode: "board".into(),
                },
                "set_view_mode",
            ),
            (
                UiControlAction::SetSearch {
                    query: "abc".into(),
                },
                "set_search",
            ),
            (UiControlAction::MaximizeDetail, "maximize_detail"),
            (UiControlAction::RestoreDetail, "restore_detail"),
            (UiControlAction::CloseDetail, "close_detail"),
            (UiControlAction::ToggleSettings, "toggle_settings"),
            (
                UiControlAction::SetSetting {
                    key: "theme".into(),
                    value: "light".into(),
                },
                "set_setting",
            ),
            (
                UiControlAction::CollapseColumn {
                    column_name: "todo".into(),
                },
                "collapse_column",
            ),
            (
                UiControlAction::ExpandColumn {
                    column_name: "doing".into(),
                },
                "expand_column",
            ),
            (
                UiControlAction::SelectIssue {
                    issue_id: "kanbus-1".into(),
                },
                "select_issue",
            ),
            (UiControlAction::ReloadPage, "reload_page"),
        ];

        for (action, expected_tag) in cases {
            let event = NotificationEvent::UiControl { action };
            let value = serde_json::to_value(&event).expect("serialize event");
            assert_eq!(value["type"], "ui_control");
            assert_eq!(value["action"]["action"], expected_tag);
            assert_eq!(event.issue_id(), None);
        }
    }
}
