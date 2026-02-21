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

    // Prevent drift between implementations: hierarchy must match an allowed canonical ordering.
    let default_hierarchy = crate::config::default_project_configuration().hierarchy;
    let python_hierarchy = vec![
        "initiative".to_string(),
        "epic".to_string(),
        "issue".to_string(),
        "subtask".to_string(),
    ];
    if configuration.hierarchy != default_hierarchy && configuration.hierarchy != python_hierarchy {
        errors.push("hierarchy is fixed".to_string());
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

    // Ensure every issue type has a workflow binding (or a default fallback).
    for issue_type in configuration
        .types
        .iter()
        .chain(configuration.hierarchy.iter())
    {
        if !configuration.workflows.contains_key(issue_type)
            && !configuration.workflows.contains_key("default")
        {
            errors.push(format!(
                "missing workflow binding for issue type '{}'",
                issue_type
            ));
            break;
        }
    }

    if configuration.transition_labels.is_empty() {
        errors.push("transition_labels must not be empty".to_string());
    }

    if !configuration
        .priorities
        .contains_key(&configuration.default_priority)
    {
        errors.push("default priority must be in priorities map".to_string());
    }

    if configuration.categories.is_empty() {
        errors.push("categories must not be empty".to_string());
    }
    let mut category_names = std::collections::HashSet::new();
    for category in &configuration.categories {
        if !category_names.insert(&category.name) {
            errors.push("duplicate category name".to_string());
            break;
        }
    }

    // Validate statuses
    if configuration.statuses.is_empty() {
        errors.push("statuses must not be empty".to_string());
    }

    // Check for duplicate status keys/names
    let mut status_keys = std::collections::HashSet::new();
    let mut status_names = std::collections::HashSet::new();
    for status in &configuration.statuses {
        if !status_keys.insert(&status.key) {
            errors.push("duplicate status key".to_string());
            break;
        }
        if !status_names.insert(&status.name) {
            errors.push("duplicate status name".to_string());
            break;
        }
        if !category_names.is_empty() && !category_names.contains(&status.category) {
            errors.push(format!(
                "status '{}' references undefined category '{}'",
                status.key, status.category
            ));
            break;
        }
    }

    // Build set of valid status keys
    let valid_statuses: std::collections::HashSet<&String> =
        configuration.statuses.iter().map(|s| &s.key).collect();

    // Validate that initial_status exists in statuses
    if !valid_statuses.contains(&configuration.initial_status) {
        errors.push(format!(
            "initial_status '{}' must exist in statuses",
            configuration.initial_status
        ));
    }

    // Validate that all workflow states exist in statuses
    for (workflow_name, workflow) in &configuration.workflows {
        for (from_status, transitions) in workflow {
            if !valid_statuses.contains(from_status) {
                errors.push(format!(
                    "workflow '{}' references undefined status '{}'",
                    workflow_name, from_status
                ));
            }
            for to_status in transitions {
                if !valid_statuses.contains(to_status) {
                    errors.push(format!(
                        "workflow '{}' references undefined status '{}'",
                        workflow_name, to_status
                    ));
                }
            }
        }
    }

    // Validate transition labels match workflows
    for (workflow_name, workflow) in &configuration.workflows {
        let Some(workflow_labels) = configuration.transition_labels.get(workflow_name) else {
            errors.push(format!(
                "transition_labels missing workflow '{}'",
                workflow_name
            ));
            continue;
        };
        for (from_status, transitions) in workflow {
            let Some(from_labels) = workflow_labels.get(from_status) else {
                errors.push(format!(
                    "transition_labels missing from-status '{}' in workflow '{}'",
                    from_status, workflow_name
                ));
                continue;
            };
            for to_status in transitions {
                if !from_labels.contains_key(to_status) {
                    errors.push(format!(
                        "transition_labels missing transition '{}' -> '{}' in workflow '{}'",
                        from_status, to_status, workflow_name
                    ));
                }
            }
            for labeled_target in from_labels.keys() {
                if !transitions.iter().any(|entry| entry == labeled_target) {
                    errors.push(format!(
                        "transition_labels references invalid transition '{}' -> '{}' in workflow '{}'",
                        from_status, labeled_target, workflow_name
                    ));
                }
            }
        }
        for labeled_from in workflow_labels.keys() {
            if !workflow.contains_key(labeled_from) {
                errors.push(format!(
                    "transition_labels references invalid from-status '{}' in workflow '{}'",
                    labeled_from, workflow_name
                ));
            }
        }
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
