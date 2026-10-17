use std::fs;
use std::path::PathBuf;

use kanbus::router::redact_router_log;
use serde_json::Value;

#[test]
fn redaction_matches_the_cases_shared_with_the_python_runtime() {
    let cases_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("tools")
        .join("parity")
        .join("redaction_cases.json");
    let cases: Vec<Value> =
        serde_json::from_str(&fs::read_to_string(&cases_path).expect("read shared cases"))
            .expect("parse shared cases");
    assert!(!cases.is_empty());
    for case in cases {
        let name = case["name"].as_str().expect("case name");
        let input = case["input"].as_str().expect("case input");
        let expected = case["expected"].as_str().expect("case expected");
        assert_eq!(redact_router_log(input), expected, "case: {name}");
    }
}
