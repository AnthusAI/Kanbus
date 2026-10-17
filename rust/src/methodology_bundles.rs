//! Methodology bundles assembled into the generated CONTRIBUTING_AGENT.md.
//!
//! A methodology is a Markdown document with YAML frontmatter that carries one
//! set of process opinions (for example Behavior-Driven Design or Git Flow).
//! Kanbus core stays neutral; the configured methodologies supply the opinions.

use serde::{Deserialize, Serialize};

use crate::error::KanbusError;
use crate::models::ProjectConfiguration;

const BUILT_IN_METHODOLOGY_SOURCES: [(&str, &str); 2] = [
    ("bdd", include_str!("methodologies/bdd/METHODOLOGY.md")),
    (
        "git-flow",
        include_str!("methodologies/git-flow/METHODOLOGY.md"),
    ),
];

/// Methodologies used when `.kanbus.yml` does not set `methodologies`.
pub const DEFAULT_METHODOLOGY_NAMES: [&str; 2] = ["bdd", "git-flow"];

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct MethodologyFrontmatter {
    name: String,
    title: String,
    #[serde(default)]
    description: Option<String>,
}

/// A methodology document split into its frontmatter and template body.
#[derive(Debug, Clone)]
pub struct MethodologyDocument {
    pub name: String,
    pub title: String,
    pub description: String,
    pub template_body: String,
}

/// A methodology whose body has been rendered with the agents-file context.
#[derive(Debug, Clone, Serialize)]
pub struct RenderedMethodology {
    pub name: String,
    pub title: String,
    pub description: String,
    pub content: String,
}

/// Return the names of the built-in methodologies.
pub fn built_in_methodology_names() -> Vec<&'static str> {
    BUILT_IN_METHODOLOGY_SOURCES
        .iter()
        .map(|(name, _)| *name)
        .collect()
}

/// Return the methodology names selected by the configuration, applying the default.
pub fn selected_methodology_names(configuration: &ProjectConfiguration) -> Vec<String> {
    match configuration.methodologies.as_ref() {
        Some(names) => names.clone(),
        None => DEFAULT_METHODOLOGY_NAMES
            .iter()
            .map(|name| name.to_string())
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
    Ok(MethodologyDocument {
        name: frontmatter.name,
        title: frontmatter.title,
        description: frontmatter.description.unwrap_or_default(),
        template_body: template_body.to_string(),
    })
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

/// Load every methodology selected by the configuration, in configured order.
///
/// # Errors
/// Returns `KanbusError::Configuration` for unknown or duplicated names.
pub fn load_selected_methodologies(
    configuration: &ProjectConfiguration,
) -> Result<Vec<MethodologyDocument>, KanbusError> {
    let mut loaded_methodologies: Vec<MethodologyDocument> = Vec::new();
    for name in selected_methodology_names(configuration) {
        if loaded_methodologies
            .iter()
            .any(|methodology| methodology.name == name)
        {
            return Err(KanbusError::Configuration(format!(
                "methodology listed more than once: {name}"
            )));
        }
        loaded_methodologies.push(load_built_in_methodology(&name)?);
    }
    Ok(loaded_methodologies)
}

/// Render each selected methodology body with the agents-file template context.
///
/// # Errors
/// Returns `KanbusError` when loading or rendering a methodology fails.
pub fn render_selected_methodologies<TemplateContext: Serialize>(
    configuration: &ProjectConfiguration,
    template_context: &TemplateContext,
) -> Result<Vec<RenderedMethodology>, KanbusError> {
    let template_environment = minijinja::Environment::new();
    load_selected_methodologies(configuration)?
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
            Ok(RenderedMethodology {
                name: methodology.name,
                title: methodology.title,
                description: methodology.description,
                content,
            })
        })
        .collect()
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
