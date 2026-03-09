//! Policy file loading and parsing.

use gherkin::{Feature, GherkinEnv};
use std::fs;
use std::path::Path;

use crate::error::KanbusError;

/// Load and parse all .policy files from the policies directory.
///
/// # Arguments
/// * `policies_dir` - Path to the policies directory.
///
/// # Returns
/// Vector of parsed Gherkin features with their source file paths.
///
/// # Errors
/// Returns `KanbusError::Configuration` if parsing fails.
pub fn load_policies(policies_dir: &Path) -> Result<Vec<(String, Feature)>, KanbusError> {
    if !policies_dir.exists() || !policies_dir.is_dir() {
        return Ok(Vec::new());
    }

    let mut features = Vec::new();

    let entries = fs::read_dir(policies_dir).map_err(|error| {
        KanbusError::Configuration(format!("failed to read policies directory: {error}"))
    })?;

    for entry in entries {
        let entry = entry.map_err(|error| {
            KanbusError::Configuration(format!("failed to read directory entry: {error}"))
        })?;
        let path = entry.path();

        if path.extension().and_then(|ext| ext.to_str()) != Some("policy") {
            continue;
        }

        let feature = Feature::parse_path(&path, GherkinEnv::default()).map_err(|error| {
            KanbusError::Configuration(format!("failed to parse {}: {error}", path.display()))
        })?;

        let file_name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("unknown")
            .to_string();

        features.push((file_name, feature));
    }

    Ok(features)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn returns_empty_for_missing_or_non_directory_path() {
        let temp = tempfile::tempdir().expect("tempdir");
        let missing = temp.path().join("missing");
        let as_file = temp.path().join("file.policy");
        fs::write(&as_file, "Feature: file\n  Scenario: ignored\n    Given x\n").expect("write");

        let missing_result = load_policies(&missing).expect("missing path should be treated empty");
        assert!(missing_result.is_empty());

        let file_result = load_policies(&as_file).expect("file path should be treated empty");
        assert!(file_result.is_empty());
    }

    #[test]
    fn loads_policy_files_and_ignores_other_extensions() {
        let temp = tempfile::tempdir().expect("tempdir");
        fs::write(
            temp.path().join("valid.policy"),
            "Feature: Valid policy\n  Scenario: pass\n    Given issue type is \"task\"\n",
        )
        .expect("write policy");
        fs::write(temp.path().join("notes.txt"), "not a policy").expect("write txt");

        let mut loaded = load_policies(temp.path()).expect("load policies");
        loaded.sort_by(|a, b| a.0.cmp(&b.0));
        assert_eq!(loaded.len(), 1);
        assert_eq!(loaded[0].0, "valid.policy");
    }

    #[test]
    fn returns_configuration_error_for_invalid_policy_syntax() {
        let temp = tempfile::tempdir().expect("tempdir");
        let bad = temp.path().join("broken.policy");
        fs::write(&bad, "Feature:\n  Scenario missing colon\n").expect("write invalid policy");

        let error = load_policies(temp.path()).expect_err("invalid syntax should fail");
        match error {
            KanbusError::Configuration(message) => {
                assert!(message.contains("failed to parse"));
                assert!(message.contains("broken.policy"));
            }
            other => panic!("expected configuration error, got {other}"),
        }
    }
}
