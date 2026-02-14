//! Hierarchy validation for parent-child relationships.

use crate::error::KanbusError;
use crate::models::ProjectConfiguration;

/// Return the allowed child types for a parent issue type.
///
/// # Arguments
/// * `configuration` - Project configuration containing hierarchy rules.
/// * `parent_type` - Parent issue type to validate.
///
/// # Returns
/// Allowed child types.
pub fn get_allowed_child_types(
    configuration: &ProjectConfiguration,
    parent_type: &str,
) -> Vec<String> {
    let parent_index = configuration
        .hierarchy
        .iter()
        .position(|entry| entry == parent_type);
    let Some(parent_index) = parent_index else {
        return Vec::new();
    };
    if parent_index >= configuration.hierarchy.len() - 1 {
        return Vec::new();
    }

    let mut allowed = Vec::new();
    allowed.push(configuration.hierarchy[parent_index + 1].clone());
    allowed.extend(configuration.types.iter().cloned());
    allowed
}

/// Validate that a parent-child relationship is permitted.
///
/// # Arguments
/// * `configuration` - Project configuration containing hierarchy rules.
/// * `parent_type` - Parent issue type.
/// * `child_type` - Child issue type.
///
/// # Errors
/// Returns `KanbusError::InvalidHierarchy` if the relationship is not permitted.
pub fn validate_parent_child_relationship(
    configuration: &ProjectConfiguration,
    parent_type: &str,
    child_type: &str,
) -> Result<(), KanbusError> {
    let allowed_child_types = get_allowed_child_types(configuration, parent_type);
    if !allowed_child_types.iter().any(|entry| entry == child_type) {
        return Err(KanbusError::InvalidHierarchy(format!(
            "invalid parent-child relationship: '{parent_type}' cannot have child '{child_type}'"
        )));
    }
    Ok(())
}
