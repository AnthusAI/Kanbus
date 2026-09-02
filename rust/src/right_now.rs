//! Right-now summary helpers.

use crate::models::IssueData;

/// Return the right-now summary for an issue.
///
/// # Arguments
///
/// * `issue` - Issue data to read.
///
/// # Returns
///
/// The right-now summary text, or `None` when absent.
pub fn get_right_now_summary(issue: &IssueData) -> Option<&str> {
    issue.right_now_summary.as_deref()
}
