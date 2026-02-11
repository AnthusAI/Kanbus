use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

use serde_json::Value;

use taskulus::models::{IssueData, ProjectConfiguration};

fn fixtures_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("specs")
        .join("fixtures")
}

fn canonicalize(value: Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut ordered = BTreeMap::new();
            for (key, val) in map {
                ordered.insert(key, canonicalize(val));
            }
            let mut ordered_map = serde_json::Map::new();
            for (key, val) in ordered {
                ordered_map.insert(key, val);
            }
            Value::Object(ordered_map)
        }
        Value::Array(items) => Value::Array(items.into_iter().map(canonicalize).collect()),
        other => other,
    }
}

#[test]
fn issue_serialization_matches_expected() {
    let fixtures = fixtures_dir();
    let issue_path = fixtures.join("sample_issues").join("open_task.json");
    let expected_path = fixtures.join("expected_issue.json");

    let issue_contents = fs::read_to_string(issue_path).expect("issue");
    let issue: IssueData = serde_json::from_str(&issue_contents).expect("issue");

    let value = serde_json::to_value(issue).expect("value");
    let canonical = canonicalize(value);
    let serialized = serde_json::to_string_pretty(&canonical).expect("json");

    let expected = fs::read_to_string(expected_path).expect("expected");
    assert_eq!(serialized.trim(), expected.trim());
}

#[test]
fn configuration_serialization_matches_expected() {
    let fixtures = fixtures_dir();
    let config_path = fixtures.join("default_config.yaml");
    let expected_path = fixtures.join("expected_config.json");

    let config_contents = fs::read_to_string(config_path).expect("config");
    let configuration: ProjectConfiguration =
        serde_yaml::from_str(&config_contents).expect("config");

    let value = serde_json::to_value(configuration).expect("value");
    let canonical = canonicalize(value);
    let serialized = serde_json::to_string_pretty(&canonical).expect("json");

    let expected = fs::read_to_string(expected_path).expect("expected");
    assert_eq!(serialized.trim(), expected.trim());
}
