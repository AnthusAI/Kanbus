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
