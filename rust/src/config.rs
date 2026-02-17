//! Default configuration for new Kanbus projects.

use std::collections::BTreeMap;
use std::path::Path;

use crate::error::KanbusError;
use crate::models::{PriorityDefinition, ProjectConfiguration};

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
        (
            0u8,
            PriorityDefinition {
                name: "critical".to_string(),
                color: Some("red".to_string()),
            },
        ),
        (
            1u8,
            PriorityDefinition {
                name: "high".to_string(),
                color: Some("bright_red".to_string()),
            },
        ),
        (
            2u8,
            PriorityDefinition {
                name: "medium".to_string(),
                color: Some("yellow".to_string()),
            },
        ),
        (
            3u8,
            PriorityDefinition {
                name: "low".to_string(),
                color: Some("blue".to_string()),
            },
        ),
        (
            4u8,
            PriorityDefinition {
                name: "trivial".to_string(),
                color: Some("white".to_string()),
            },
        ),
    ]);

    ProjectConfiguration {
        project_directory: "project".to_string(),
        external_projects: Vec::new(),
        ignore_paths: Vec::new(),
        console_port: None,
        project_key: "kanbus".to_string(),
        project_management_template: None,
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
        assignee: None,
        time_zone: None,
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
        beads_compatibility: false,
    }
}

/// Write the default configuration to disk.
///
/// # Arguments
///
/// * `path` - Path to the kanbus.yml file.
///
/// # Errors
///
/// Returns `KanbusError::Io` if writing fails.
pub fn write_default_configuration(path: &Path) -> Result<(), KanbusError> {
    let configuration = default_project_configuration();
    let contents = serde_yaml::to_string(&configuration)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    std::fs::write(path, contents).map_err(|error| KanbusError::Io(error.to_string()))
}
