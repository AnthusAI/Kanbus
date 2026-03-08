//! Configuration loading and validation.

use std::env;
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
    let dotenv_path = path.parent().unwrap_or(Path::new(".")).join(".env");
    load_dotenv(&dotenv_path);
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
    handle_legacy_fields(&mut merged_value);
    normalize_virtual_projects(&mut merged_value);
    apply_environment_overrides(&mut merged_value);
    let configuration: ProjectConfiguration = serde_yaml::from_value(Value::Mapping(merged_value))
        .map_err(|error| KanbusError::Configuration(map_configuration_error(&error)))?;

    let errors = validate_project_configuration(&configuration);
    if !errors.is_empty() {
        return Err(KanbusError::Configuration(errors.join("; ")));
    }

    Ok(configuration)
}

fn load_dotenv(path: &Path) {
    let Ok(contents) = fs::read_to_string(path) else {
        return;
    };

    for line in contents.lines() {
        let mut stripped = line.trim();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        if let Some(rest) = stripped.strip_prefix("export ") {
            stripped = rest.trim_start();
        }
        let Some((key, value)) = stripped.split_once('=') else {
            continue;
        };
        let key = key.trim();
        if key.is_empty() || env::var_os(key).is_some() {
            continue;
        }
        let mut value = value.trim().to_string();
        if value.len() >= 2 {
            let bytes = value.as_bytes();
            let first = bytes[0];
            let last = bytes[bytes.len() - 1];
            if (first == b'"' && last == b'"') || (first == b'\'' && last == b'\'') {
                value = value[1..value.len() - 1].to_string();
            }
        }
        env::set_var(key, value);
    }
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

    if let Some(ref wd) = configuration.wiki_directory {
        if wd.starts_with('/') || (wd.len() >= 2 && wd.chars().nth(1) == Some(':')) {
            errors.push("wiki_directory must not escape project root".to_string());
        } else if wd.contains("..") {
            let normalized = wd.replace('\\', "/");
            if wd.matches("..").count() > 1 || !normalized.starts_with("../") {
                errors.push("wiki_directory must not escape project root".to_string());
            }
        }
    }

    for label in configuration.virtual_projects.keys() {
        if label == &configuration.project_key {
            errors.push("virtual project label conflicts with project key".to_string());
            break;
        }
    }

    if let Some(ref target) = configuration.new_issue_project {
        if target != "ask"
            && target != &configuration.project_key
            && !configuration.virtual_projects.contains_key(target)
        {
            errors.push("new_issue_project references unknown project".to_string());
        }
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

    validate_sort_order(configuration, &mut errors);

    errors
}

const SORT_PRESETS: &[&str] = &["fifo", "priority-first", "recently-updated"];
const SORT_FIELDS: &[&str] = &["priority", "created_at", "updated_at", "id"];
const SORT_DIRECTIONS: &[&str] = &["asc", "desc"];

fn validate_sort_order(configuration: &ProjectConfiguration, errors: &mut Vec<String>) {
    if configuration.sort_order.is_empty() {
        return;
    }

    if let Some(categories_value) = configuration.sort_order.get("categories") {
        let Some(categories) = categories_value.as_mapping() else {
            errors.push("sort_order.categories must be a mapping".to_string());
            return;
        };
        for (category, rule) in categories {
            let Some(category_name) = category.as_str() else {
                errors.push("sort_order.categories keys must be strings".to_string());
                continue;
            };
            validate_sort_rule(
                &format!("sort_order.categories.{category_name}"),
                rule,
                errors,
            );
        }
    }

    for (status, rule) in &configuration.sort_order {
        if status == "categories" {
            continue;
        }
        validate_sort_rule(&format!("sort_order.{status}"), rule, errors);
    }
}

fn validate_sort_rule(path: &str, value: &Value, errors: &mut Vec<String>) {
    if let Some(preset) = value.as_str() {
        if !SORT_PRESETS.contains(&preset) {
            errors.push(format!(
                "{path} has invalid preset '{preset}' (valid presets: {})",
                SORT_PRESETS.join(", ")
            ));
        }
        return;
    }

    let Some(rules) = value.as_sequence() else {
        errors.push(format!(
            "{path} must be a preset string or a list of field rules"
        ));
        return;
    };

    if rules.is_empty() {
        errors.push(format!("{path} must not be an empty list"));
        return;
    }

    for (index, rule) in rules.iter().enumerate() {
        let Some(mapping) = rule.as_mapping() else {
            errors.push(format!(
                "{path}[{index}] must be an object with field/direction"
            ));
            continue;
        };

        for key in mapping.keys() {
            let Some(key_text) = key.as_str() else {
                errors.push(format!("{path}[{index}] contains a non-string key"));
                continue;
            };
            if key_text != "field" && key_text != "direction" {
                errors.push(format!("{path}[{index}] has unsupported key '{key_text}'"));
            }
        }

        let field = mapping
            .get(Value::String("field".to_string()))
            .and_then(Value::as_str);
        let direction = mapping
            .get(Value::String("direction".to_string()))
            .and_then(Value::as_str);

        match field {
            Some(value) if SORT_FIELDS.contains(&value) => {}
            Some(value) => errors.push(format!(
                "{path}[{index}] has invalid field '{value}' (valid fields: {})",
                SORT_FIELDS.join(", ")
            )),
            None => errors.push(format!("{path}[{index}] is missing 'field'")),
        }

        match direction {
            Some(value) if SORT_DIRECTIONS.contains(&value) => {}
            Some(value) => errors.push(format!(
                "{path}[{index}] has invalid direction '{value}' (valid directions: {})",
                SORT_DIRECTIONS.join(", ")
            )),
            None => errors.push(format!("{path}[{index}] is missing 'direction'")),
        }
    }
}

/// Convert `virtual_projects` from a YAML sequence (e.g. `[]`) to an empty
/// mapping so that it deserializes into `BTreeMap<String, VirtualProjectConfig>`.
/// Older configs (and the old `external_projects` field) used a list format.
fn normalize_virtual_projects(mapping: &mut Mapping) {
    let key = Value::String("virtual_projects".to_string());
    if let Some(Value::Sequence(_)) = mapping.get(&key) {
        mapping.insert(key, Value::Mapping(Mapping::new()));
    }
}

fn handle_legacy_fields(mapping: &mut Mapping) {
    let legacy_key = Value::String("external_projects".to_string());
    if let Some(legacy_value) = mapping.remove(&legacy_key) {
        let virtual_key = Value::String("virtual_projects".to_string());
        if !mapping.contains_key(&virtual_key) {
            mapping.insert(virtual_key, legacy_value);
        }
        eprintln!(
            "Warning: external_projects has been replaced by virtual_projects. Please update your configuration."
        );
    }
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
    let vp_key = Value::String("virtual_projects".to_string());
    for (key, value_override) in overrides {
        if key == vp_key {
            // Merge virtual_projects additively so the override adds entries
            // rather than replacing the entire map.
            if let Value::Mapping(additions) = value_override {
                if let Some(Value::Mapping(existing)) = value.get(&vp_key).cloned() {
                    let mut merged = existing;
                    for (k, v) in additions {
                        merged.insert(k, v);
                    }
                    value.insert(vp_key.clone(), Value::Mapping(merged));
                } else {
                    value.insert(vp_key.clone(), Value::Mapping(additions));
                }
                continue;
            }
        }
        value.insert(key, value_override);
    }
    value
}

fn apply_environment_overrides(mapping: &mut Mapping) {
    if let Ok(value) = env::var("KANBUS_REALTIME_TRANSPORT") {
        if !value.trim().is_empty() {
            set_nested_value(mapping, &["realtime", "transport"], Value::String(value));
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_BROKER") {
        if !value.trim().is_empty() {
            set_nested_value(mapping, &["realtime", "broker"], Value::String(value));
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_AUTOSTART") {
        if let Some(parsed) = parse_env_bool(&value) {
            set_nested_value(mapping, &["realtime", "autostart"], Value::Bool(parsed));
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_KEEPALIVE") {
        if let Some(parsed) = parse_env_bool(&value) {
            set_nested_value(mapping, &["realtime", "keepalive"], Value::Bool(parsed));
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_UDS_SOCKET_PATH") {
        if !value.trim().is_empty() {
            set_nested_value(
                mapping,
                &["realtime", "uds_socket_path"],
                Value::String(value),
            );
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME") {
        if !value.trim().is_empty() {
            set_nested_value(
                mapping,
                &["realtime", "mqtt_custom_authorizer_name"],
                Value::String(value),
            );
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_MQTT_API_TOKEN") {
        if !value.trim().is_empty() {
            set_nested_value(
                mapping,
                &["realtime", "mqtt_api_token"],
                Value::String(value),
            );
        }
    }
    if let Ok(value) = env::var("KANBUS_REALTIME_TOPICS_PROJECT_EVENTS") {
        if !value.trim().is_empty() {
            set_nested_value(
                mapping,
                &["realtime", "topics", "project_events"],
                Value::String(value),
            );
        }
    }
    if let Ok(value) = env::var("KANBUS_OVERLAY_ENABLED") {
        if let Some(parsed) = parse_env_bool(&value) {
            set_nested_value(mapping, &["overlay", "enabled"], Value::Bool(parsed));
        }
    }
    if let Ok(value) = env::var("KANBUS_OVERLAY_TTL_S") {
        if let Ok(parsed) = value.trim().parse::<u64>() {
            set_nested_value(
                mapping,
                &["overlay", "ttl_s"],
                Value::Number(serde_yaml::Number::from(parsed)),
            );
        }
    }
}

fn parse_env_bool(value: &str) -> Option<bool> {
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" => Some(true),
        "0" | "false" | "no" | "off" => Some(false),
        _ => None,
    }
}

fn set_nested_value(mapping: &mut Mapping, path: &[&str], value: Value) {
    if path.is_empty() {
        return;
    }
    if path.len() == 1 {
        mapping.insert(Value::String(path[0].to_string()), value);
        return;
    }
    let key = Value::String(path[0].to_string());
    if !matches!(mapping.get(&key), Some(Value::Mapping(_))) {
        mapping.insert(key.clone(), Value::Mapping(Mapping::new()));
    }
    if let Some(Value::Mapping(child)) = mapping.get_mut(&key) {
        set_nested_value(child, &path[1..], value);
    }
}
