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

    ProjectConfiguration {
        project_directory: "project".to_string(),
        external_projects: Vec::new(),
        project_key: "tsk".to_string(),
        hierarchy: vec![
            "initiative".to_string(),
            "epic".to_string(),
            "task".to_string(),
            "sub-task".to_string(),
        ],
        types: vec!["bug".to_string(), "story".to_string(), "chore".to_string()],
        workflows,
        initial_status: "open".to_string(),
        priorities: BTreeMap::from([
            (
                0,
                crate::models::PriorityDefinition {
                    name: "critical".to_string(),
                    color: Some("red".to_string()),
                },
            ),
            (
                1,
                crate::models::PriorityDefinition {
                    name: "high".to_string(),
                    color: Some("bright_red".to_string()),
                },
            ),
            (
                2,
                crate::models::PriorityDefinition {
                    name: "medium".to_string(),
                    color: Some("yellow".to_string()),
                },
            ),
            (
                3,
                crate::models::PriorityDefinition {
                    name: "low".to_string(),
                    color: Some("blue".to_string()),
                },
            ),
            (
                4,
                crate::models::PriorityDefinition {
                    name: "trivial".to_string(),
                    color: Some("white".to_string()),
                },
            ),
        ]),
        default_priority: 2,
        status_colors: BTreeMap::from([
            ("open".to_string(), "cyan".to_string()),
            ("in_progress".to_string(), "blue".to_string()),
            ("blocked".to_string(), "red".to_string()),
            ("closed".to_string(), "green".to_string()),
            ("deferred".to_string(), "yellow".to_string()),
        ]),
        type_colors: BTreeMap::from([
            ("initiative".to_string(), "bright_blue".to_string()),
            ("epic".to_string(), "magenta".to_string()),
            ("task".to_string(), "cyan".to_string()),
            ("sub-task".to_string(), "bright_cyan".to_string()),
            ("bug".to_string(), "red".to_string()),
            ("story".to_string(), "yellow".to_string()),
            ("chore".to_string(), "green".to_string()),
            ("event".to_string(), "bright_blue".to_string()),
        ]),
    }
}

/// Write the default configuration to disk.
///
/// # Arguments
///
/// * `path` - Path to the .taskulus.yml file.
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
