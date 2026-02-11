use std::collections::HashSet;

use chrono::{TimeZone, Utc};
use regex::Regex;

use taskulus::ids::{generate_issue_identifier, generate_many_identifiers, IssueIdentifierRequest};

#[test]
fn generated_ids_follow_prefix_hex_format() {
    let request = IssueIdentifierRequest {
        title: "Test".to_string(),
        existing_ids: HashSet::new(),
        prefix: "tsk".to_string(),
        created_at: Utc::now(),
    };

    let result = generate_issue_identifier(&request).expect("identifier");
    let pattern = Regex::new(r"^tsk-[0-9a-f]{6}$").expect("regex");
    assert!(pattern.is_match(&result.identifier));
}

#[test]
fn generated_ids_are_unique() {
    let ids = generate_many_identifiers("Test", "tsk", 100).expect("ids");
    assert_eq!(ids.len(), 100);
}

#[test]
fn collision_is_avoided() {
    let mut existing = HashSet::new();
    existing.insert("tsk-aaaaaa".to_string());

    let request = IssueIdentifierRequest {
        title: "Test".to_string(),
        existing_ids: existing,
        prefix: "tsk".to_string(),
        created_at: Utc.with_ymd_and_hms(2025, 2, 10, 0, 0, 0).unwrap(),
    };

    let result = generate_issue_identifier(&request).expect("identifier");
    assert_ne!(result.identifier, "tsk-aaaaaa");
}
