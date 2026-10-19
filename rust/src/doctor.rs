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
    Ok(DoctorResult {
        project_dir,
        ai_credential_source,
        methodology_names,
        project_management_file_is_current,
    })
}
