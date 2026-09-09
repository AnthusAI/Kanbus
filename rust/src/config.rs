//! Default configuration for new Kanbus projects.

use std::collections::BTreeMap;
use std::path::Path;

use crate::error::KanbusError;
use crate::models::{
    AiConfiguration, CategoryDefinition, HooksConfiguration, OverlayConfig, PriorityDefinition,
    ProjectConfiguration, RealtimeConfig, RightNowConfiguration, StandupConfiguration,
    StatusDefinition,
};

/// Return the default project configuration.
pub fn default_project_configuration() -> ProjectConfiguration {
    let mut workflows = BTreeMap::new();
    workflows.insert(
        "default".to_string(),
        BTreeMap::from([
            (
                "backlog".to_string(),
                vec!["open".to_string(), "closed".to_string()],
            ),
            (
                "open".to_string(),
                vec![
                    "in_progress".to_string(),
                    "closed".to_string(),
                    "backlog".to_string(),
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

    let transition_labels: BTreeMap<String, BTreeMap<String, BTreeMap<String, String>>> =
        BTreeMap::from([
            (
                "default".to_string(),
                BTreeMap::from([
                    (
                        "backlog".to_string(),
                        BTreeMap::from([
                            ("open".to_string(), "Start discovery".to_string()),
                            ("closed".to_string(), "Drop".to_string()),
                        ]),
                    ),
                    (
                        "open".to_string(),
                        BTreeMap::from([
                            ("in_progress".to_string(), "Start work".to_string()),
                            ("closed".to_string(), "Drop".to_string()),
                            ("backlog".to_string(), "Back to backlog".to_string()),
                        ]),
                    ),
                    (
                        "in_progress".to_string(),
                        BTreeMap::from([
                            ("open".to_string(), "Pause".to_string()),
                            ("blocked".to_string(), "Block".to_string()),
                            ("closed".to_string(), "Complete".to_string()),
                        ]),
                    ),
                    (
                        "blocked".to_string(),
                        BTreeMap::from([
                            ("in_progress".to_string(), "Unblock".to_string()),
                            ("closed".to_string(), "Drop".to_string()),
                        ]),
                    ),
                    (
                        "closed".to_string(),
                        BTreeMap::from([("open".to_string(), "Reopen".to_string())]),
                    ),
                ]),
            ),
            (
                "epic".to_string(),
                BTreeMap::from([
                    (
                        "open".to_string(),
                        BTreeMap::from([
                            ("in_progress".to_string(), "Start".to_string()),
                            ("closed".to_string(), "Complete".to_string()),
                        ]),
                    ),
                    (
                        "in_progress".to_string(),
                        BTreeMap::from([
                            ("open".to_string(), "Pause".to_string()),
                            ("closed".to_string(), "Complete".to_string()),
                        ]),
                    ),
                    (
                        "closed".to_string(),
                        BTreeMap::from([("open".to_string(), "Reopen".to_string())]),
                    ),
                ]),
            ),
        ]);

    let categories = vec![
        CategoryDefinition {
            name: "To do".to_string(),
            color: Some("grey".to_string()),
        },
        CategoryDefinition {
            name: "In progress".to_string(),
            color: Some("blue".to_string()),
        },
        CategoryDefinition {
            name: "Done".to_string(),
            color: Some("green".to_string()),
        },
    ];

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
        virtual_projects: BTreeMap::new(),
        new_issue_project: None,
        ignore_paths: Vec::new(),
        console_port: None,
        realtime: RealtimeConfig::default(),
        overlay: OverlayConfig::default(),
        project_key: "kanbus".to_string(),
        name: None,
        project_management_template: None,
        hierarchy: vec![
            "initiative".to_string(),
            "epic".to_string(),
            "task".to_string(),
            "sub-task".to_string(),
        ],
        types: vec!["bug".to_string(), "story".to_string(), "chore".to_string()],
        workflows,
        transition_labels,
        initial_status: "open".to_string(),
        priorities,
        default_priority: 2,
        assignee: None,
        time_zone: None,
        statuses: vec![
            StatusDefinition {
                key: "backlog".to_string(),
                name: "Backlog".to_string(),
                category: "To do".to_string(),
                semantic_category: "todo".to_string(),
                color: None,
                collapsed: true,
            },
            StatusDefinition {
                key: "open".to_string(),
                name: "Discovery".to_string(),
                category: "To do".to_string(),
                semantic_category: "todo".to_string(),
                color: None,
                collapsed: false,
            },
            StatusDefinition {
                key: "in_progress".to_string(),
                name: "In Progress".to_string(),
                category: "In progress".to_string(),
                semantic_category: "in_progress".to_string(),
                color: None,
                collapsed: false,
            },
            StatusDefinition {
                key: "blocked".to_string(),
                name: "Blocked".to_string(),
                category: "In progress".to_string(),
                semantic_category: "in_progress".to_string(),
                color: None,
                collapsed: true,
            },
            StatusDefinition {
                key: "closed".to_string(),
                name: "Done".to_string(),
                category: "Done".to_string(),
                semantic_category: "done".to_string(),
                color: None,
                collapsed: true,
            },
        ],
        categories,
        sort_order: BTreeMap::new(),
        type_colors: BTreeMap::from([
            ("initiative".to_string(), "bright_blue".to_string()),
            ("epic".to_string(), "magenta".to_string()),
            ("task".to_string(), "blue".to_string()),
            ("sub-task".to_string(), "bright_cyan".to_string()),
            ("bug".to_string(), "red".to_string()),
            ("story".to_string(), "yellow".to_string()),
            ("chore".to_string(), "green".to_string()),
            ("event".to_string(), "bright_blue".to_string()),
        ]),
        beads_compatibility: false,
        jira: None,
        snyk: None,
        wiki_directory: None,
        ai: Some(AiConfiguration {
            provider: "litellm".to_string(),
            model: "gpt-5.6-luna".to_string(),
        }),
        right_now: RightNowConfiguration::default(),
        standup: StandupConfiguration::default(),
        hooks: HooksConfiguration::default(),
        github_security: None,
    }
}

/// Return the board title for console display.
///
/// # Arguments
/// * `configured_name` - Optional `name` from `.kanbus.yml`.
/// * `repository_root` - Repository root path.
/// * `project_key` - Issue ID project key used when the folder name is empty.
///
/// # Returns
/// Configured name, repository folder name, or project key.
pub fn resolve_board_name(
    configured_name: Option<&str>,
    repository_root: &Path,
    project_key: &str,
) -> String {
    if let Some(configured_name) = configured_name {
        let trimmed = configured_name.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }
    let folder_name = repository_root
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("")
        .trim();
    if folder_name.is_empty() || folder_name == "." {
        return project_key.to_string();
    }
    folder_name.to_string()
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

#[cfg(test)]
mod tests {
    use super::resolve_board_name;
    use std::path::Path;

    #[test]
    fn resolve_board_name_prefers_configured_name() {
        assert_eq!(
            resolve_board_name(Some("Chattic.us"), Path::new("/tmp/other"), "kbs"),
            "Chattic.us"
        );
    }

    #[test]
    fn resolve_board_name_trims_configured_name() {
        assert_eq!(
            resolve_board_name(Some("  Kanbus  "), Path::new("/tmp/other"), "kbs"),
            "Kanbus"
        );
    }

    #[test]
    fn resolve_board_name_uses_folder_when_name_blank() {
        assert_eq!(
            resolve_board_name(Some("  "), Path::new("/repos/Chattic.us"), "chatticus"),
            "Chattic.us"
        );
    }

    #[test]
    fn resolve_board_name_uses_project_key_when_folder_empty() {
        assert_eq!(resolve_board_name(None, Path::new("/"), "kanbus"), "kanbus");
    }
}
