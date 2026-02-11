//! Configuration loading and validation.

use std::fs;
use std::path::Path;

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
    let contents =
        fs::read_to_string(path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let configuration: ProjectConfiguration = serde_yaml::from_str(&contents)
        .map_err(|error| TaskulusError::Configuration(error.to_string()))?;

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
