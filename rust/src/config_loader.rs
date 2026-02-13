//! Configuration loading and validation.

use std::fs;
use std::path::Path;

use serde_yaml::{Mapping, Value};

use crate::config::default_project_configuration;
use crate::error::TaskulusError;
use crate::models::ProjectConfiguration;

/// Load a project configuration from disk.
///
/// # Arguments
///
/// * `path` - Path to the configuration file.
///
/// # Errors
///
/// Returns `TaskulusError::Configuration` if the configuration is invalid.
pub fn load_project_configuration(path: &Path) -> Result<ProjectConfiguration, TaskulusError> {
    let contents = fs::read_to_string(path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            TaskulusError::Configuration("configuration file not found".to_string())
        } else {
            TaskulusError::Io(error.to_string())
        }
    })?;

    let raw_value: Value = if contents.trim().is_empty() {
        Value::Mapping(Mapping::new())
    } else {
        serde_yaml::from_str(&contents)
            .map_err(|error| TaskulusError::Configuration(map_configuration_error(&error)))?
    };
    let merged_value = merge_with_defaults(raw_value)?;
    let configuration: ProjectConfiguration = serde_yaml::from_value(merged_value)
        .map_err(|error| TaskulusError::Configuration(map_configuration_error(&error)))?;

    let errors = validate_project_configuration(&configuration);
    if !errors.is_empty() {
        return Err(TaskulusError::Configuration(errors.join("; ")));
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

fn merge_with_defaults(value: Value) -> Result<Value, TaskulusError> {
    let mut defaults = serde_yaml::to_value(default_project_configuration())
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    let overrides = match value {
        Value::Null => Mapping::new(),
        Value::Mapping(mapping) => mapping,
        _ => {
            return Err(TaskulusError::Configuration(
                "configuration must be a mapping".to_string(),
            ))
        }
    };

    if let Value::Mapping(ref mut default_map) = defaults {
        for (key, value) in overrides {
            default_map.insert(key, value);
        }
    }
    Ok(defaults)
}
