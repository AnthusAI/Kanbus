//! Methodology bundles assembled into the generated CONTRIBUTING_AGENT.md.
//!
//! A methodology is a Markdown document with YAML frontmatter that carries one
//! set of process opinions (for example Behavior-Driven Design or Git Flow).
//! Kanbus core stays neutral; the configured methodologies supply the opinions.

use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::error::KanbusError;
use crate::models::{MethodologySelection, ProjectConfiguration};

const BUILT_IN_METHODOLOGY_SOURCES: [(&str, &str); 2] = [
    ("bdd", include_str!("methodologies/bdd/METHODOLOGY.md")),
    (
        "git-flow",
        include_str!("methodologies/git-flow/METHODOLOGY.md"),
    ),
];

/// Methodologies used when `.kanbus.yml` does not set `methodologies`.
pub const DEFAULT_METHODOLOGY_NAMES: [&str; 2] = ["bdd", "git-flow"];

/// File that defines a methodology inside its bundle directory.
pub const METHODOLOGY_DOCUMENT_FILENAME: &str = "METHODOLOGY.md";

/// Command that runs a methodology tool from the repository root.
pub const METHODOLOGY_TOOL_INVOCATION_PREFIX: &str = "kbs methodology run";

/// Environment variable that tells a running tool where its bundle lives.
pub const METHODOLOGY_DIRECTORY_ENVIRONMENT_VARIABLE: &str = "KANBUS_METHODOLOGY_DIRECTORY";

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct MethodologyFrontmatter {
    name: String,
    title: String,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    tools: Vec<MethodologyToolDeclaration>,
}

/// A tool a methodology bundle ships, declared in its frontmatter.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MethodologyToolDeclaration {
    pub name: String,
    pub command: String,
    pub purpose: String,
}

/// A methodology document split into its frontmatter and template body.
#[derive(Debug, Clone)]
pub struct MethodologyDocument {
    pub name: String,
    pub title: String,
    pub description: String,
    pub template_body: String,
    pub tools: Vec<MethodologyToolDeclaration>,
    pub bundle_directory: Option<PathBuf>,
}

/// A methodology tool as listed in the agents file.
#[derive(Debug, Clone, Serialize)]
pub struct RenderedMethodologyTool {
    pub name: String,
    pub purpose: String,
    pub invocation: String,
}

/// A methodology whose body has been rendered with the agents-file context.
#[derive(Debug, Clone, Serialize)]
pub struct RenderedMethodology {
    pub name: String,
    pub title: String,
    pub description: String,
    pub content: String,
    pub tools: Vec<RenderedMethodologyTool>,
}

/// Return the names of the built-in methodologies.
pub fn built_in_methodology_names() -> Vec<&'static str> {
    BUILT_IN_METHODOLOGY_SOURCES
        .iter()
        .map(|(name, _)| *name)
        .collect()
}

/// Return the methodologies selected by the configuration, applying the default.
pub fn selected_methodologies(configuration: &ProjectConfiguration) -> Vec<MethodologySelection> {
    match configuration.methodologies.as_ref() {
        Some(selections) => selections.clone(),
        None => DEFAULT_METHODOLOGY_NAMES
            .iter()
            .map(|name| MethodologySelection::BuiltInName(name.to_string()))
            .collect(),
    }
}

/// Parse a methodology document with `---` delimited YAML frontmatter.
///
/// # Errors
/// Returns `KanbusError::Configuration` when the frontmatter is missing or malformed.
pub fn parse_methodology_document(
    source_text: &str,
    source_description: &str,
) -> Result<MethodologyDocument, KanbusError> {
    let malformed_frontmatter_error = || {
        KanbusError::Configuration(format!(
            "methodology {source_description} must begin with YAML frontmatter between --- lines"
        ))
    };
    let normalized_text = source_text.replace("\r\n", "\n");
    let after_opening_delimiter = normalized_text
        .strip_prefix("---\n")
        .ok_or_else(malformed_frontmatter_error)?;
    let closing_delimiter_index = after_opening_delimiter
        .find("\n---\n")
        .ok_or_else(malformed_frontmatter_error)?;
    let frontmatter_text = &after_opening_delimiter[..closing_delimiter_index];
    let template_body = &after_opening_delimiter[closing_delimiter_index + "\n---\n".len()..];
    let frontmatter: MethodologyFrontmatter =
        serde_yaml::from_str(frontmatter_text).map_err(|error| {
            KanbusError::Configuration(format!(
                "methodology {source_description} has invalid frontmatter: {error}"
            ))
        })?;
    validate_methodology_tool_declarations(&frontmatter.tools, source_description)?;
    Ok(MethodologyDocument {
        name: frontmatter.name,
        title: frontmatter.title,
        description: frontmatter.description.unwrap_or_default(),
        template_body: template_body.to_string(),
        tools: frontmatter.tools,
        bundle_directory: None,
    })
}

fn validate_methodology_tool_declarations(
    tools: &[MethodologyToolDeclaration],
    source_description: &str,
) -> Result<(), KanbusError> {
    for (tool_index, tool) in tools.iter().enumerate() {
        if tools[..tool_index]
            .iter()
            .any(|earlier_tool| earlier_tool.name == tool.name)
        {
            return Err(KanbusError::Configuration(format!(
                "methodology {source_description} declares tool {} more than once",
                tool.name
            )));
        }
        let command_path = Path::new(&tool.command);
        let command_stays_inside_bundle = !tool.command.is_empty()
            && command_path
                .components()
                .all(|component| matches!(component, Component::Normal(_) | Component::CurDir));
        if !command_stays_inside_bundle {
            return Err(KanbusError::Configuration(format!(
                "methodology {source_description} tool {} command must be a path inside the bundle: {}",
                tool.name, tool.command
            )));
        }
    }
    Ok(())
}

/// Load a built-in methodology by name.
///
/// # Errors
/// Returns `KanbusError::Configuration` when no built-in methodology has that name.
pub fn load_built_in_methodology(name: &str) -> Result<MethodologyDocument, KanbusError> {
    let (_, source_text) = BUILT_IN_METHODOLOGY_SOURCES
        .iter()
        .find(|(built_in_name, _)| *built_in_name == name)
        .ok_or_else(|| {
            KanbusError::Configuration(format!(
                "unknown methodology: {name} (built-in methodologies: {})",
                built_in_methodology_names().join(", ")
            ))
        })?;
    parse_methodology_document(source_text, &format!("built-in {name}"))
}

/// Load a methodology bundle directory from the repository.
///
/// # Errors
/// Returns `KanbusError::Configuration` when the bundle or its document is missing or malformed.
pub fn load_project_methodology_bundle(
    repository_root: &Path,
    bundle_relative_path: &str,
) -> Result<MethodologyDocument, KanbusError> {
    let bundle_directory = repository_root.join(bundle_relative_path);
    if !bundle_directory.is_dir() {
        return Err(KanbusError::Configuration(format!(
            "methodology bundle not found: {bundle_relative_path}"
        )));
    }
    let document_path = bundle_directory.join(METHODOLOGY_DOCUMENT_FILENAME);
    let source_text = std::fs::read_to_string(&document_path).map_err(|_| {
        KanbusError::Configuration(format!(
            "methodology bundle {bundle_relative_path} has no {METHODOLOGY_DOCUMENT_FILENAME}"
        ))
    })?;
    let mut methodology =
        parse_methodology_document(&source_text, &format!("bundle {bundle_relative_path}"))?;
    methodology.bundle_directory = Some(bundle_directory);
    Ok(methodology)
}

/// Load every methodology selected by the configuration, in configured order.
///
/// # Errors
/// Returns `KanbusError::Configuration` for unknown, missing, malformed or duplicated methodologies.
pub fn load_selected_methodologies(
    repository_root: &Path,
    configuration: &ProjectConfiguration,
) -> Result<Vec<MethodologyDocument>, KanbusError> {
    let mut loaded_methodologies: Vec<MethodologyDocument> = Vec::new();
    for selection in selected_methodologies(configuration) {
        let methodology = match &selection {
            MethodologySelection::BuiltInName(name) => load_built_in_methodology(name)?,
            MethodologySelection::ProjectBundle(bundle_reference) => {
                load_project_methodology_bundle(repository_root, &bundle_reference.path)?
            }
        };
        if loaded_methodologies
            .iter()
            .any(|loaded_methodology| loaded_methodology.name == methodology.name)
        {
            return Err(KanbusError::Configuration(format!(
                "methodology listed more than once: {}",
                methodology.name
            )));
        }
        loaded_methodologies.push(methodology);
    }
    Ok(loaded_methodologies)
}

/// Render each selected methodology body with the agents-file template context.
///
/// # Errors
/// Returns `KanbusError` when loading or rendering a methodology fails.
pub fn render_selected_methodologies<TemplateContext: Serialize>(
    repository_root: &Path,
    configuration: &ProjectConfiguration,
    template_context: &TemplateContext,
) -> Result<Vec<RenderedMethodology>, KanbusError> {
    let template_environment = minijinja::Environment::new();
    load_selected_methodologies(repository_root, configuration)?
        .into_iter()
        .map(|methodology| {
            let content = template_environment
                .render_str(&methodology.template_body, template_context)
                .map_err(|error| {
                    KanbusError::IssueOperation(format!(
                        "methodology {} failed to render: {error}",
                        methodology.name
                    ))
                })?;
            let rendered_tools: Vec<RenderedMethodologyTool> = methodology
                .tools
                .iter()
                .map(|tool| RenderedMethodologyTool {
                    name: tool.name.clone(),
                    purpose: tool.purpose.clone(),
                    invocation: format!(
                        "{METHODOLOGY_TOOL_INVOCATION_PREFIX} {} {}",
                        methodology.name, tool.name
                    ),
                })
                .collect();
            let content_with_tool_listing = if rendered_tools.is_empty() {
                content
            } else {
                format!(
                    "{}\n\n{}",
                    content.trim_end(),
                    methodology_tool_listing_text(&methodology.title, &rendered_tools)
                )
            };
            Ok(RenderedMethodology {
                name: methodology.name,
                title: methodology.title,
                description: methodology.description,
                content: content_with_tool_listing,
                tools: rendered_tools,
            })
        })
        .collect()
}

fn methodology_tool_listing_text(
    methodology_title: &str,
    rendered_tools: &[RenderedMethodologyTool],
) -> String {
    let tool_lines: Vec<String> = rendered_tools
        .iter()
        .map(|tool| format!("- `{}`: {}", tool.invocation, tool.purpose))
        .collect();
    format!(
        "### {methodology_title} tools\n\nRun these from the repository root:\n\n{}\n",
        tool_lines.join("\n")
    )
}

/// Run a tool declared by one of the configured methodologies.
///
/// The tool runs from the repository root with the bundle directory exported in
/// `KANBUS_METHODOLOGY_DIRECTORY`. Its standard output is returned; its standard
/// error is passed through.
///
/// # Errors
/// Returns `KanbusError` when the methodology is not configured, the tool is not
/// declared, the command cannot start, or the tool exits unsuccessfully.
pub fn run_methodology_tool(
    repository_root: &Path,
    configuration: &ProjectConfiguration,
    methodology_name: &str,
    tool_name: &str,
    tool_arguments: &[String],
) -> Result<String, KanbusError> {
    let configured_methodologies = load_selected_methodologies(repository_root, configuration)?;
    let methodology = configured_methodologies
        .iter()
        .find(|configured_methodology| configured_methodology.name == methodology_name)
        .ok_or_else(|| {
            let configured_names: Vec<&str> = configured_methodologies
                .iter()
                .map(|configured_methodology| configured_methodology.name.as_str())
                .collect();
            KanbusError::IssueOperation(format!(
                "methodology not configured: {methodology_name} (configured methodologies: {})",
                configured_names.join(", ")
            ))
        })?;
    let tool = methodology
        .tools
        .iter()
        .find(|declared_tool| declared_tool.name == tool_name)
        .ok_or_else(|| {
            let declared_tool_names: Vec<&str> = methodology
                .tools
                .iter()
                .map(|declared_tool| declared_tool.name.as_str())
                .collect();
            let declared_tool_summary = if declared_tool_names.is_empty() {
                "it declares no tools".to_string()
            } else {
                format!("declared tools: {}", declared_tool_names.join(", "))
            };
            KanbusError::IssueOperation(format!(
                "methodology {methodology_name} has no tool named {tool_name} ({declared_tool_summary})"
            ))
        })?;
    let bundle_directory = methodology.bundle_directory.as_ref().ok_or_else(|| {
        KanbusError::IssueOperation(format!(
            "methodology {methodology_name} is built in and has no bundle directory"
        ))
    })?;
    let tool_program_path = bundle_directory.join(&tool.command);
    let tool_output = std::process::Command::new(&tool_program_path)
        .args(tool_arguments)
        .current_dir(repository_root)
        .env(METHODOLOGY_DIRECTORY_ENVIRONMENT_VARIABLE, bundle_directory)
        .output()
        .map_err(|error| {
            KanbusError::IssueOperation(format!(
                "methodology tool {methodology_name} {tool_name} could not start {}: {error}",
                tool.command
            ))
        })?;
    let tool_standard_output = String::from_utf8_lossy(&tool_output.stdout).to_string();
    let tool_standard_error = String::from_utf8_lossy(&tool_output.stderr).to_string();
    if tool_output.status.success() {
        eprint!("{tool_standard_error}");
        return Ok(tool_standard_output);
    }
    let exit_status_description = tool_output
        .status
        .code()
        .map(|exit_code| exit_code.to_string())
        .unwrap_or_else(|| "a signal".to_string());
    Err(KanbusError::IssueOperation(format!(
        "{tool_standard_output}{tool_standard_error}methodology tool {methodology_name} {tool_name} exited with status {exit_status_description}"
    )))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_built_in_methodology_parses_and_declares_its_own_name() {
        for name in built_in_methodology_names() {
            let methodology = load_built_in_methodology(name).expect("built-in parses");
            assert_eq!(methodology.name, name);
            assert!(!methodology.title.is_empty());
        }
    }

    #[test]
    fn parse_methodology_document_rejects_missing_frontmatter() {
        let error =
            parse_methodology_document("## Heading\n", "example").expect_err("missing frontmatter");
        assert!(error
            .to_string()
            .contains("must begin with YAML frontmatter"));
    }
}
