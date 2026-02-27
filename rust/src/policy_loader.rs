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
