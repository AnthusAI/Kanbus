//! Helpers for managing AGENTS.md Taskulus instructions.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{self, Write};
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::file_io::get_configuration_path;
use crate::models::ProjectConfiguration;
use crate::project_management_template::{
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE, DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME,
};
use serde::Serialize;

const TASKULUS_SECTION_HEADER: &str = "## Project management with Taskulus";
const TASKULUS_SECTION_LINES: [&str; 8] = [
    TASKULUS_SECTION_HEADER,
    "",
    "Use Taskulus for task management.",
    "Why: Taskulus task management is MANDATORY here; every task must live in Taskulus.",
    "When: Create/update the Taskulus task before coding; close it only after the change lands.",
    "How: See CONTRIBUTING_AGENT.md for the Taskulus workflow, hierarchy, status rules, priorities, command examples, and the sins to avoid.",
    "Performance: Prefer tskr (Rust) when available; tsk (Python) is equivalent but slower.",
    "Warning: Editing project/ directly is a sin against The Way. Do not read or write anything in project/; work only through Taskulus.",
];
const AGENTS_HEADER_LINES: [&str; 2] = ["# Agent Instructions", ""];
const PROJECT_MANAGEMENT_FILENAME: &str = "CONTRIBUTING_AGENT.md";

#[derive(Debug, Clone)]
struct SectionMatch {
    start: usize,
    end: usize,
}

/// Ensure AGENTS.md exists and contains the Taskulus section.
///
/// # Arguments
/// * `root` - Repository root path
/// * `force` - Overwrite existing Taskulus section without prompting
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if overwrite is required but not confirmed.
pub fn ensure_agents_file(root: &Path, force: bool) -> Result<(), TaskulusError> {
    let instructions_text = build_project_management_text(root)?;
    let agents_path = root.join("AGENTS.md");
    if !agents_path.exists() {
        let content = build_new_agents_file();
        fs::write(&agents_path, content).map_err(|error| TaskulusError::Io(error.to_string()))?;
        ensure_project_management_file(root, force, &instructions_text)?;
        ensure_project_guard_files(root)?;
        return Ok(());
    }

    let contents =
        fs::read_to_string(&agents_path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let lines: Vec<String> = contents.lines().map(|line| line.to_string()).collect();
    if let Some(section) = find_taskulus_section(&lines) {
        if !force {
            if !confirm_overwrite()? {
                ensure_project_management_file(root, force, &instructions_text)?;
                ensure_project_guard_files(root)?;
                return Ok(());
            }
        }
        let updated = replace_section(&lines, &section, &TASKULUS_SECTION_LINES);
        fs::write(&agents_path, updated).map_err(|error| TaskulusError::Io(error.to_string()))?;
        ensure_project_management_file(root, force, &instructions_text)?;
        ensure_project_guard_files(root)?;
        return Ok(());
    }

    let updated = insert_taskulus_section(&lines, &TASKULUS_SECTION_LINES);
    fs::write(&agents_path, updated).map_err(|error| TaskulusError::Io(error.to_string()))?;
    ensure_project_management_file(root, force, &instructions_text)?;
    ensure_project_guard_files(root)?;
    Ok(())
}

/// Return the canonical Taskulus section text.
pub fn taskulus_section_text() -> String {
    let lines = TASKULUS_SECTION_LINES
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>();
    join_lines(&lines)
}

/// Return the Taskulus project management text derived from configuration.
///
/// # Arguments
/// * `root` - Repository root path
///
/// # Errors
/// Returns `TaskulusError` if configuration lookup fails.
pub fn project_management_text(root: &Path) -> Result<String, TaskulusError> {
    build_project_management_text(root)
}

fn build_project_management_text(root: &Path) -> Result<String, TaskulusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&configuration_path)?;
    let template_path = resolve_project_management_template_path(root, &configuration)?;
    let template_text = match template_path {
        Some(path) => std::fs::read_to_string(&path)
            .map_err(|error| TaskulusError::Io(error.to_string()))?,
        None => DEFAULT_PROJECT_MANAGEMENT_TEMPLATE.to_string(),
    };
    let context = build_project_management_context(&configuration);
    let env = minijinja::Environment::new();
    env.render_str(&template_text, context)
        .map_err(|error| TaskulusError::IssueOperation(error.to_string()))
}

fn build_new_agents_file() -> String {
    let mut lines: Vec<&str> = Vec::new();
    lines.extend(AGENTS_HEADER_LINES);
    lines.extend(TASKULUS_SECTION_LINES);
    join_lines(&lines.iter().map(|value| value.to_string()).collect::<Vec<_>>())
}

#[derive(Debug, Serialize)]
struct WorkflowContext {
    name: String,
    statuses: Vec<WorkflowStatusContext>,
}

#[derive(Debug, Serialize)]
struct WorkflowStatusContext {
    name: String,
    transitions: Vec<String>,
}

#[derive(Debug, Serialize)]
struct PriorityContext {
    value: u8,
    name: String,
}

#[derive(Debug, Serialize)]
struct SemanticReleaseMapping {
    r#type: String,
    category: String,
}

#[derive(Debug, Serialize)]
struct ProjectManagementContext {
    project_key: String,
    hierarchy_order: String,
    non_hierarchical_types: Vec<String>,
    parent_child_rules: Vec<String>,
    initial_status: String,
    workflows: Vec<WorkflowContext>,
    priorities: Vec<PriorityContext>,
    default_priority_value: u8,
    default_priority_name: String,
    command_examples: Vec<String>,
    semantic_release_mapping: Vec<SemanticReleaseMapping>,
    has_story: bool,
    gherkin_example: Vec<String>,
}

fn resolve_project_management_template_path(
    root: &Path,
    configuration: &ProjectConfiguration,
) -> Result<Option<std::path::PathBuf>, TaskulusError> {
    if let Some(path) = configuration.project_management_template.as_ref() {
        let resolved = if std::path::Path::new(path).is_absolute() {
            std::path::PathBuf::from(path)
        } else {
            root.join(path)
        };
        if !resolved.exists() {
            return Err(TaskulusError::IssueOperation(format!(
                "project management template not found: {}",
                resolved.display()
            )));
        }
        return Ok(Some(resolved));
    }
    let conventional = root.join(DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME);
    if conventional.exists() {
        return Ok(Some(conventional));
    }
    Ok(None)
}

fn build_project_management_context(
    configuration: &ProjectConfiguration,
) -> ProjectManagementContext {
    let hierarchy = &configuration.hierarchy;
    let types = &configuration.types;
    let workflows = build_workflow_context(&configuration.workflows);
    let priorities = build_priority_context(&configuration.priorities);
    let default_priority_name = configuration
        .priorities
        .get(&configuration.default_priority)
        .map(|definition| definition.name.clone())
        .unwrap_or_else(|| configuration.default_priority.to_string());
    ProjectManagementContext {
        project_key: configuration.project_key.clone(),
        hierarchy_order: if hierarchy.is_empty() {
            "none".to_string()
        } else {
            hierarchy.join(" -> ")
        },
        non_hierarchical_types: types.clone(),
        parent_child_rules: build_parent_child_rules(hierarchy, types),
        initial_status: configuration.initial_status.clone(),
        workflows,
        priorities,
        default_priority_value: configuration.default_priority,
        default_priority_name,
        command_examples: build_command_examples(configuration),
        semantic_release_mapping: build_semantic_release_mapping(types),
        has_story: types.iter().any(|value| value.to_lowercase() == "story"),
        gherkin_example: vec![
            "Feature:".to_string(),
            "Scenario:".to_string(),
            "Given".to_string(),
            "When".to_string(),
            "Then".to_string(),
        ],
    }
}

fn build_parent_child_rules(hierarchy: &[String], types: &[String]) -> Vec<String> {
    let mut rules = Vec::new();
    if hierarchy.len() > 1 {
        for index in 1..hierarchy.len() {
            let child = &hierarchy[index];
            let parent = &hierarchy[index - 1];
            rules.push(format!("{child} can have parent {parent}."));
        }
    }
    if !types.is_empty() {
        let parents = if hierarchy.len() > 1 {
            hierarchy[..hierarchy.len() - 1].join(", ")
        } else {
            String::new()
        };
        if parents.is_empty() {
            rules.push(format!("{} cannot have parents.", types.join(", ")));
        } else {
            rules.push(format!(
                "{} can have parent {}.",
                types.join(", "),
                parents
            ));
        }
    }
    if hierarchy.len() <= 1 && types.is_empty() {
        rules.push("No parent-child relationships are defined.".to_string());
    }
    rules
}

fn build_workflow_context(
    workflows: &BTreeMap<String, BTreeMap<String, Vec<String>>>,
) -> Vec<WorkflowContext> {
    let mut context = Vec::new();
    for (workflow_name, workflow) in workflows {
        let mut statuses = Vec::new();
        for (status, transitions) in workflow {
            statuses.push(WorkflowStatusContext {
                name: status.clone(),
                transitions: transitions.clone(),
            });
        }
        context.push(WorkflowContext {
            name: workflow_name.clone(),
            statuses,
        });
    }
    context
}

fn build_priority_context(
    priorities: &BTreeMap<u8, crate::models::PriorityDefinition>,
) -> Vec<PriorityContext> {
    let mut context = Vec::new();
    for (value, definition) in priorities {
        context.push(PriorityContext {
            value: *value,
            name: definition.name.clone(),
        });
    }
    context
}

fn build_command_examples(configuration: &ProjectConfiguration) -> Vec<String> {
    let hierarchy = &configuration.hierarchy;
    let types = &configuration.types;
    let priority_example = configuration
        .priorities
        .keys()
        .next()
        .copied()
        .unwrap_or(configuration.default_priority);
    let workflow_name = if configuration.workflows.contains_key("default") {
        "default".to_string()
    } else {
        configuration
            .workflows
            .keys()
            .next()
            .cloned()
            .unwrap_or_else(|| "default".to_string())
    };
    let empty_workflow = BTreeMap::new();
    let workflow = configuration
        .workflows
        .get(&workflow_name)
        .unwrap_or(&empty_workflow);
    let status_example = select_status_example(&configuration.initial_status, workflow);
    let status_set = collect_statuses(workflow);
    let mut lines = Vec::new();
    if let Some(top) = hierarchy.first() {
        lines.push(format!("tsk create \"Plan the roadmap\" --type {top}"));
    }
    if hierarchy.len() > 1 {
        lines.push(format!(
            "tsk create \"Release v1\" --type {} --parent <{}-id>",
            hierarchy[1], hierarchy[0]
        ));
    }
    if hierarchy.len() > 2 {
        lines.push(format!(
            "tsk create \"Implement feature\" --type {} --parent <{}-id>",
            hierarchy[2], hierarchy[1]
        ));
    }
    if let Some(issue_type) = types.first() {
        let parent = if hierarchy.len() > 1 {
            Some(&hierarchy[1])
        } else {
            None
        };
        let parent_fragment = parent
            .map(|value| format!(" --parent <{value}-id>"))
            .unwrap_or_default();
        lines.push(format!(
            "tsk create \"Fix crash on launch\" --type {issue_type} --priority {priority_example}{parent_fragment}"
        ));
    }
    lines.push(format!(
        "tsk update <id> --status {status_example} --assignee \"you@example.com\""
    ));
    if status_set.contains("blocked") && status_example != "blocked" {
        lines.push("tsk update <id> --status blocked".to_string());
    }
    lines.push("tsk comment <id> \"Progress note\"".to_string());
    lines.push(format!(
        "tsk list --status {}",
        configuration.initial_status
    ));
    lines.push("tsk close <id> --comment \"Summary of the change\"".to_string());
    lines
}

fn build_semantic_release_mapping(types: &[String]) -> Vec<SemanticReleaseMapping> {
    let mut mapping = Vec::new();
    for issue_type in types {
        let lowered = issue_type.to_lowercase();
        let category = if lowered.contains("bug") || lowered.contains("fix") {
            "fix"
        } else if lowered.contains("story") || lowered.contains("feature") {
            "feat"
        } else if lowered.contains("chore") || lowered.contains("maintenance") {
            "chore"
        } else {
            "chore"
        };
        mapping.push(SemanticReleaseMapping {
            r#type: issue_type.clone(),
            category: category.to_string(),
        });
    }
    mapping
}

fn collect_statuses(workflow: &BTreeMap<String, Vec<String>>) -> BTreeSet<String> {
    let mut statuses = BTreeSet::new();
    for (status, transitions) in workflow {
        statuses.insert(status.clone());
        for transition in transitions {
            statuses.insert(transition.clone());
        }
    }
    statuses
}

fn select_status_example(initial_status: &str, workflow: &BTreeMap<String, Vec<String>>) -> String {
    if let Some(transitions) = workflow.get(initial_status) {
        if let Some(value) = transitions.first() {
            return value.clone();
        }
    }
    for transitions in workflow.values() {
        if let Some(value) = transitions.first() {
            return value.clone();
        }
    }
    initial_status.to_string()
}

fn ensure_project_management_file(
    root: &Path,
    force: bool,
    content: &str,
) -> Result<(), TaskulusError> {
    let instructions_path = root.join(PROJECT_MANAGEMENT_FILENAME);
    if instructions_path.exists() && !force {
        return Ok(());
    }
    fs::write(&instructions_path, content).map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(())
}

fn ensure_project_guard_files(root: &Path) -> Result<(), TaskulusError> {
    let project_dir = root.join("project");
    if !project_dir.exists() {
        return Ok(());
    }
    let project_agents = project_dir.join("AGENTS.md");
    let project_agents_content = [
        "# DO NOT EDIT HERE",
        "",
        "Editing anything under project/ directly is hacking the data and is a sin against The Way.",
        "Do not read or write in this folder. Use Taskulus commands instead.",
        "",
        "See ../AGENTS.md and ../CONTRIBUTING_AGENT.md for required process.",
    ]
    .join("\n")
        + "\n";
    fs::write(&project_agents, project_agents_content)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;

    let do_not_edit = project_dir.join("DO_NOT_EDIT");
    let do_not_edit_content = [
        "DO NOT EDIT ANYTHING IN project/",
        "This folder is guarded by The Way.",
        "All changes must go through Taskulus (see ../AGENTS.md and ../CONTRIBUTING_AGENT.md).",
    ]
    .join("\n")
        + "\n";
    fs::write(&do_not_edit, do_not_edit_content)
        .map_err(|error| TaskulusError::Io(error.to_string()))
}

fn confirm_overwrite() -> Result<bool, TaskulusError> {
    print!("Taskulus section already exists in AGENTS.md. Overwrite it? [y/N] ");
    io::stdout()
        .flush()
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    let mut input = String::new();
    let bytes = io::stdin()
        .read_line(&mut input)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    if bytes == 0 {
        return Err(TaskulusError::IssueOperation(
            "Taskulus section already exists in AGENTS.md. Re-run with --force to overwrite."
                .to_string(),
        ));
    }
    let response = input.trim().to_lowercase();
    Ok(response == "y" || response == "yes")
}

fn find_taskulus_section(lines: &[String]) -> Option<SectionMatch> {
    for (index, line) in lines.iter().enumerate() {
        if let Some((level, text)) = parse_header(line) {
            if text.to_lowercase().contains("taskulus") {
                let end = find_section_end(lines, index + 1, level);
                return Some(SectionMatch { start: index, end });
            }
        }
    }
    None
}

fn find_section_end(lines: &[String], start: usize, level: usize) -> usize {
    for index in start..lines.len() {
        if let Some((next_level, _)) = parse_header(&lines[index]) {
            if next_level <= level {
                return index;
            }
        }
    }
    lines.len()
}

fn parse_header(line: &str) -> Option<(usize, String)> {
    let trimmed = line.trim_end();
    if !trimmed.starts_with('#') {
        return None;
    }
    let mut count = 0;
    for ch in trimmed.chars() {
        if ch == '#' {
            count += 1;
        } else {
            break;
        }
    }
    if count == 0 || count > 6 {
        return None;
    }
    let rest = trimmed[count..].trim_start();
    if !rest.starts_with(' ') && !rest.starts_with('\t') {
        return None;
    }
    let text = rest.trim();
    if text.is_empty() {
        return None;
    }
    Some((count, text.to_string()))
}

fn replace_section(lines: &[String], section: &SectionMatch, section_lines: &[&str]) -> String {
    let mut updated = Vec::new();
    updated.extend_from_slice(&lines[..section.start]);
    updated.extend(section_lines.iter().map(|value| value.to_string()));
    updated.extend_from_slice(&lines[section.end..]);
    join_lines(&updated)
}

fn insert_taskulus_section(lines: &[String], section_lines: &[&str]) -> String {
    let mut updated: Vec<String> = lines.to_vec();
    let mut insert_index = find_insert_index(lines);
    if insert_index > 0 && insert_index < updated.len() && !updated[insert_index].trim().is_empty() {
        updated.insert(insert_index, String::new());
        insert_index += 1;
    }
    let section_strings = section_lines.iter().map(|value| value.to_string());
    updated.splice(insert_index..insert_index, section_strings);
    join_lines(&updated)
}

fn find_insert_index(lines: &[String]) -> usize {
    for (index, line) in lines.iter().enumerate() {
        if let Some((level, _)) = parse_header(line) {
            if level == 1 {
                let mut insert_index = index + 1;
                while insert_index < lines.len() && lines[insert_index].trim().is_empty() {
                    insert_index += 1;
                }
                return insert_index;
            }
        }
    }
    0
}

fn join_lines(lines: &[String]) -> String {
    let mut output = lines.join("\n");
    output.push('\n');
    output
}
