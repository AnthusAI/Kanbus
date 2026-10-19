//! Environment diagnostics for Kanbus.

use std::path::{Path, PathBuf};

use crate::agents_management::project_management_text;
use crate::ai_credentials::{resolve_api_key_source, DEFAULT_API_KEY_VARIABLE};
use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{ensure_git_repository, get_configuration_path, load_project_directory};
use crate::maintenance::validate_project;
use crate::methodology_bundles::load_selected_methodologies;

/// Result of running doctor checks.
#[derive(Debug, Clone)]
pub struct DoctorResult {
    pub project_dir: PathBuf,
    /// Description of where the default AI credential currently resolves from.
    pub ai_credential_source: &'static str,
    /// Names of the configured methodologies, in configured order.
    pub methodology_names: Vec<String>,
    /// Whether CONTRIBUTING_AGENT.md matches what the configuration generates; `None` when the file is absent.
    pub project_management_file_is_current: Option<bool>,
    /// Warning text naming the gitignore rule that hides project events while events are enabled.
    pub events_gitignore_warning: Option<String>,
}

fn describe_gitignore_rule_hiding_events(
    root: &Path,
    project_dir: &Path,
) -> Result<Option<String>, KanbusError> {
    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let canonical_events_dir = project_dir
        .join("events")
        .canonicalize()
        .unwrap_or_else(|_| project_dir.join("events"));
    let events_relative_path = canonical_events_dir
        .strip_prefix(&canonical_root)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .to_string_lossy()
        .replace('\\', "/");
    let check_output = std::process::Command::new("git")
        .args(["check-ignore", "-v", "--"])
        .arg(format!("{events_relative_path}/probe.json"))
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !check_output.status.success() {
        return Ok(None);
    }
    let stdout = String::from_utf8_lossy(&check_output.stdout).to_string();
    let rule_source = stdout.split('\t').next().unwrap_or_default().trim();
    let mut rule_parts = rule_source.splitn(3, ':');
    let source_file = rule_parts.next().unwrap_or_default();
    let line_number = rule_parts.next().unwrap_or_default();
    let pattern = rule_parts.next().unwrap_or_default();
    Ok(Some(format!(
        "events are enabled but {events_relative_path} is gitignored by the rule {pattern} ({source_file}:{line_number}); remove the rule so kbs commit includes events"
    )))
}

/// Run diagnostic checks for Kanbus.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if any check fails.
pub fn run_doctor(root: &Path) -> Result<DoctorResult, KanbusError> {
    ensure_git_repository(root)?;
    let project_dir = load_project_directory(root)?;
    let configuration_path = get_configuration_path(project_dir.as_path())?;
    let configuration = load_project_configuration(&configuration_path)?;
    validate_project(root)?;
    let methodology_names = load_selected_methodologies(root, &configuration)?
        .into_iter()
        .map(|methodology| methodology.name)
        .collect();
    let expected_project_management_text = project_management_text(root)?;
    let project_management_file_is_current =
        std::fs::read_to_string(root.join("CONTRIBUTING_AGENT.md"))
            .ok()
            .map(|existing_text| existing_text == expected_project_management_text);
    let ai_credential_source =
        resolve_api_key_source(Some(root), DEFAULT_API_KEY_VARIABLE).describe();
    let events_gitignore_warning = if configuration.events {
        describe_gitignore_rule_hiding_events(root, &project_dir)?
    } else {
        None
    };
    Ok(DoctorResult {
        project_dir,
        ai_credential_source,
        methodology_names,
        project_management_file_is_current,
        events_gitignore_warning,
    })
}
