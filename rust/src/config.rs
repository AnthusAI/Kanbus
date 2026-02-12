//! Default configuration for new Taskulus projects.

use std::collections::BTreeMap;
use std::path::Path;

use crate::error::TaskulusError;
use crate::models::ProjectConfiguration;

/// Return the default project configuration.
pub fn default_project_configuration() -> ProjectConfiguration {
    let mut workflows = BTreeMap::new();
    workflows.insert(
        "default".to_string(),
        BTreeMap::from([
            (
                "open".to_string(),
                vec![
                    "in_progress".to_string(),
                    "closed".to_string(),
                    "deferred".to_string(),
                ],
            ),
            (
                "in_progress".to_string(),
                vec![
                    "open".to_string(),
                    "blocked".to_string(),
                    "closed".to_string(),
                ],
            ),
            (
                "blocked".to_string(),
                vec!["in_progress".to_string(), "closed".to_string()],
            ),
            ("closed".to_string(), vec!["open".to_string()]),
            (
                "deferred".to_string(),
                vec!["open".to_string(), "closed".to_string()],
            ),
        ]),
    );
    workflows.insert(
        "epic".to_string(),
        BTreeMap::from([
            (
                "open".to_string(),
                vec!["in_progress".to_string(), "closed".to_string()],
            ),
            (
                "in_progress".to_string(),
                vec!["open".to_string(), "closed".to_string()],
            ),
            ("closed".to_string(), vec!["open".to_string()]),
        ]),
    );

    let priorities = BTreeMap::from([
        (0, "critical".to_string()),
        (1, "high".to_string()),
        (2, "medium".to_string()),
        (3, "low".to_string()),
        (4, "trivial".to_string()),
    ]);

    ProjectConfiguration {
        prefix: "tsk".to_string(),
        hierarchy: vec![
            "initiative".to_string(),
            "epic".to_string(),
            "task".to_string(),
            "sub-task".to_string(),
        ],
        types: vec!["bug".to_string(), "story".to_string(), "chore".to_string()],
        workflows,
        initial_status: "open".to_string(),
        priorities,
        default_priority: 2,
    }
}

/// Write the default configuration to disk.
///
/// # Arguments
///
/// * `path` - Path to the config.yaml file.
///
/// # Errors
///
/// Returns `TaskulusError::Io` if writing fails.
pub fn write_default_configuration(path: &Path) -> Result<(), TaskulusError> {
    let configuration = default_project_configuration();
    let contents = serde_yaml::to_string(&configuration)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    std::fs::write(path, contents).map_err(|error| TaskulusError::Io(error.to_string()))
}
