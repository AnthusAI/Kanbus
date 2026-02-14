//! Configuration loading and validation.

use std::fs;
use std::path::Path;

use serde_yaml::{Mapping, Value};

use crate::config::default_project_configuration;
use crate::error::KanbusError;
use crate::models::ProjectConfiguration;

/// Load a project configuration from disk.
///
/// # Arguments
///
/// * `path` - Path to the configuration file.
///
/// # Errors
///
/// Returns `KanbusError::Configuration` if the configuration is invalid.
pub fn load_project_configuration(path: &Path) -> Result<ProjectConfiguration, KanbusError> {
    let contents = fs::read_to_string(path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            KanbusError::Configuration("configuration file not found".to_string())
        } else {
            KanbusError::Io(error.to_string())
        }
    })?;

    let raw_value = load_configuration_value(&contents)?;
    let mut merged_value = merge_with_defaults(raw_value)?;
    let overrides = load_override_configuration(path.parent().unwrap_or(Path::new(".")))?;
    merged_value = apply_overrides(merged_value, overrides);
    let configuration: ProjectConfiguration = serde_yaml::from_value(Value::Mapping(merged_value))
        .map_err(|error| KanbusError::Configuration(map_configuration_error(&error)))?;

    let errors = validate_project_configuration(&configuration);
    if !errors.is_empty() {
        return Err(KanbusError::Configuration(errors.join("; ")));
    }

    Ok(configuration)
}

/// Validate configuration rules beyond schema validation.
///
/// # Arguments
///
/// * `configuration` - Loaded configuration.
///
/// # Returns
///
/// A list of validation errors.
pub fn validate_project_configuration(configuration: &ProjectConfiguration) -> Vec<String> {
    let mut errors = Vec::new();

    if configuration.project_directory.trim().is_empty() {
        errors.push("project_directory must not be empty".to_string());
    }

    if configuration.hierarchy.is_empty() {
        errors.push("hierarchy must not be empty".to_string());
    }

    let mut seen = std::collections::HashSet::new();
    for item in configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
    {
        if seen.contains(item) {
            errors.push("duplicate type name".to_string());
            break;
        }
        seen.insert(item.to_string());
    }

    if !configuration.workflows.contains_key("default") {
        errors.push("default workflow is required".to_string());
    }

    if !configuration
        .priorities
        .contains_key(&configuration.default_priority)
    {
        errors.push("default priority must be in priorities map".to_string());
    }

    errors
}

fn map_configuration_error(error: &serde_yaml::Error) -> String {
    let message = error.to_string();
    if message.contains("unknown field") {
        return "unknown configuration fields".to_string();
    }
    message
}

fn merge_with_defaults(value: Value) -> Result<Mapping, KanbusError> {
    let defaults_value = serde_yaml::to_value(default_project_configuration())
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut defaults = defaults_value
        .as_mapping()
        .cloned()
        .expect("default configuration must be a mapping");
    let overrides = match value {
        Value::Null => Mapping::new(),
        Value::Mapping(mapping) => mapping,
        _ => {
            return Err(KanbusError::Configuration(
                "configuration must be a mapping".to_string(),
            ))
        }
    };

    for (key, value) in overrides {
        defaults.insert(key, value);
    }
    Ok(defaults)
}

fn load_configuration_value(contents: &str) -> Result<Value, KanbusError> {
    if contents.trim().is_empty() {
        return Ok(Value::Mapping(Mapping::new()));
    }
    let raw_value: Value = serde_yaml::from_str(contents)
        .map_err(|error| KanbusError::Configuration(map_configuration_error(&error)))?;
    Ok(raw_value)
}

fn load_override_configuration(root: &Path) -> Result<Mapping, KanbusError> {
    let override_path = root.join(".kanbus.override.yml");
    if !override_path.exists() {
        return Ok(Mapping::new());
    }
    let contents =
        fs::read_to_string(&override_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    if contents.trim().is_empty() {
        return Ok(Mapping::new());
    }
    let raw_value: Value = serde_yaml::from_str(&contents).map_err(|_error| {
        KanbusError::Configuration("override configuration is invalid".to_string())
    })?;
    match raw_value {
        Value::Mapping(mapping) => Ok(mapping),
        _ => Err(KanbusError::Configuration(
            "override configuration must be a mapping".to_string(),
        )),
    }
}

fn apply_overrides(mut value: Mapping, overrides: Mapping) -> Mapping {
    if overrides.is_empty() {
        return value;
    }
    for (key, value_override) in overrides {
        value.insert(key, value_override);
    }
    value
}
