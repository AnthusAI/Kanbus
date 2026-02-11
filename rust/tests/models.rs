use chrono::{TimeZone, Utc};
use serde_json::json;

use taskulus::models::{DependencyLink, IssueComment, IssueData};

#[test]
fn issue_data_parses_from_aliases() {
    let payload = json!({
        "id": "tsk-aaaaaa",
        "title": "Title",
        "description": "",
        "type": "task",
        "status": "open",
        "priority": 2,
        "assignee": null,
        "creator": "user@example.com",
        "parent": null,
        "labels": ["label"],
        "dependencies": [{"target": "tsk-bbbbbb", "type": "blocked-by"}],
        "comments": [
            {
                "author": "user@example.com",
                "text": "Comment",
                "created_at": Utc.with_ymd_and_hms(2025, 2, 10, 0, 0, 0).unwrap(),
            }
        ],
        "created_at": Utc.with_ymd_and_hms(2025, 2, 10, 0, 0, 0).unwrap(),
        "updated_at": Utc.with_ymd_and_hms(2025, 2, 10, 0, 0, 0).unwrap(),
        "closed_at": null,
        "custom": {},
    });

    let issue: IssueData = serde_json::from_value(payload).expect("issue");
    assert_eq!(issue.identifier, "tsk-aaaaaa");
    assert_eq!(issue.issue_type, "task");
    assert!(matches!(issue.dependencies[0], DependencyLink { .. }));
    assert!(matches!(issue.comments[0], IssueComment { .. }));
}
