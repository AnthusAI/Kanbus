//! Agent provenance metadata resolution and validation.

use regex::Regex;
use serde_json::Value;
use std::collections::BTreeMap;
use std::sync::LazyLock;

use crate::error::KanbusError;
use crate::models::AgentMetadata;

static PLATFORM_PATTERN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[a-z0-9_-]{1,64}$").expect("platform regex"));
static SECRET_KEY_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(api[_-]?key|token|secret|password|credential)").expect("secret key regex")
});

const MAX_AGENT_METADATA_BYTES: usize = 2048;
const MAX_AGENT_NAME_LENGTH: usize = 128;

/// Optional agent metadata inputs from CLI flags and environment.
#[derive(Debug, Clone, Default)]
pub struct AgentMetadataRequest {
    pub platform: Option<String>,
    pub model: Option<String>,
    pub name: Option<String>,
    pub settings_json: Option<String>,
}

fn normalize_optional_text(value: Option<&str>) -> Option<String> {
    value.and_then(|text| {
        let trimmed = text.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn normalize_platform(platform: &str) -> Result<String, KanbusError> {
    let normalized = platform.trim().to_ascii_lowercase();
    if !PLATFORM_PATTERN.is_match(&normalized) {
        return Err(KanbusError::IssueOperation(
            "invalid agent platform".to_string(),
        ));
    }
    Ok(normalized)
}

fn normalize_agent_name(name: Option<&str>) -> Result<Option<String>, KanbusError> {
    let Some(normalized) = normalize_optional_text(name) else {
        return Ok(None);
    };
    if normalized.len() > MAX_AGENT_NAME_LENGTH {
        return Err(KanbusError::IssueOperation(
            "invalid agent name".to_string(),
        ));
    }
    Ok(Some(normalized))
}

fn validate_settings_keys(settings: &BTreeMap<String, Value>) -> Result<(), KanbusError> {
    for key in settings.keys() {
        if SECRET_KEY_PATTERN.is_match(key) {
            return Err(KanbusError::IssueOperation(
                "agent settings must not contain secret-like keys".to_string(),
            ));
        }
    }
    Ok(())
}

fn parse_settings_json(
    settings_json: Option<&str>,
) -> Result<BTreeMap<String, Value>, KanbusError> {
    let Some(normalized) = normalize_optional_text(settings_json) else {
        return Ok(BTreeMap::new());
    };
    let parsed: Value = serde_json::from_str(&normalized).map_err(|error| {
        KanbusError::IssueOperation(format!("invalid agent settings JSON: {error}"))
    })?;
    let Value::Object(object) = parsed else {
        return Err(KanbusError::IssueOperation(
            "invalid agent settings JSON: expected object".to_string(),
        ));
    };
    Ok(object.into_iter().collect())
}

/// Build validated agent metadata or return None when all inputs are absent.
pub fn build_agent_metadata(
    platform: Option<&str>,
    model: Option<&str>,
    settings: &BTreeMap<String, Value>,
    name: Option<&str>,
) -> Result<Option<AgentMetadata>, KanbusError> {
    let normalized_platform = normalize_optional_text(platform);
    let normalized_model = normalize_optional_text(model);
    let normalized_name = normalize_agent_name(name)?;
    if normalized_platform.is_none()
        && normalized_model.is_none()
        && settings.is_empty()
        && normalized_name.is_none()
    {
        return Ok(None);
    }
    let platform_value = normalized_platform.ok_or_else(|| {
        KanbusError::IssueOperation("agent metadata requires both platform and model".to_string())
    })?;
    let model_value = normalized_model.ok_or_else(|| {
        KanbusError::IssueOperation("agent metadata requires both platform and model".to_string())
    })?;
    validate_settings_keys(settings)?;
    let agent = AgentMetadata {
        platform: normalize_platform(&platform_value)?,
        model: model_value,
        name: normalized_name,
        settings: settings.clone(),
    };
    let serialized = serde_json::to_string(&agent)
        .map_err(|error| KanbusError::IssueOperation(format!("invalid agent metadata: {error}")))?;
    if serialized.len() > MAX_AGENT_METADATA_BYTES {
        return Err(KanbusError::IssueOperation(
            "agent metadata exceeds maximum size".to_string(),
        ));
    }
    Ok(Some(agent))
}

/// Resolve agent metadata from CLI flags with environment defaults.
pub fn resolve_agent_metadata(
    request: &AgentMetadataRequest,
) -> Result<Option<AgentMetadata>, KanbusError> {
    let mut platform = normalize_optional_text(request.platform.as_deref());
    let mut model = normalize_optional_text(request.model.as_deref());
    let mut name = normalize_agent_name(request.name.as_deref())?;
    let mut settings_json = normalize_optional_text(request.settings_json.as_deref());
    if platform.is_none() {
        platform = normalize_optional_text(std::env::var("KANBUS_AGENT_PLATFORM").ok().as_deref());
    }
    if model.is_none() {
        model = normalize_optional_text(std::env::var("KANBUS_AGENT_MODEL").ok().as_deref());
    }
    if name.is_none() {
        name = normalize_agent_name(std::env::var("KANBUS_AGENT_NAME").ok().as_deref())?;
    }
    if settings_json.is_none() {
        settings_json =
            normalize_optional_text(std::env::var("KANBUS_AGENT_SETTINGS").ok().as_deref());
    }
    let settings = parse_settings_json(settings_json.as_deref())?;
    build_agent_metadata(
        platform.as_deref(),
        model.as_deref(),
        &settings,
        name.as_deref(),
    )
}

fn format_setting_value(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Bool(flag) => flag.to_string(),
        Value::Null => "null".to_string(),
        other => other.to_string(),
    }
}

/// Format agent metadata for compact CLI display.
pub fn format_agent_display_line(agent: &AgentMetadata) -> String {
    let platform_model = format!("{} / {}", agent.platform, agent.model);
    if let Some(name) = agent.name.as_deref() {
        format!("{name} / {platform_model}")
    } else {
        platform_model
    }
}

/// Format agent settings for CLI display.
pub fn format_agent_settings_display(agent: &AgentMetadata) -> Option<String> {
    if agent.settings.is_empty() {
        return None;
    }
    let parts = agent
        .settings
        .iter()
        .map(|(key, value)| format!("{key}={}", format_setting_value(value)))
        .collect::<Vec<_>>();
    Some(parts.join(", "))
}

/// Serialize agent metadata for event payloads.
pub fn agent_metadata_to_event_value(agent: &AgentMetadata) -> Value {
    serde_json::to_value(agent).unwrap_or(Value::Null)
}

/// Reject agent metadata mutations in Beads compatibility mode.
pub fn reject_agent_metadata_in_beads_mode(agent_present: bool) -> Result<(), KanbusError> {
    if agent_present {
        return Err(KanbusError::IssueOperation(
            "agent metadata requires native Kanbus issue storage".to_string(),
        ));
    }
    Ok(())
}

/// Format comment author label with optional agent suffix.
pub fn format_comment_author_label(author: &str, agent: Option<&AgentMetadata>) -> String {
    match agent {
        Some(metadata) => format!("{author} ({}):", format_agent_display_line(metadata)),
        None => format!("{author}:"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_agent_metadata_requires_platform_and_model_together() {
        let error = build_agent_metadata(Some("cursor"), None, &BTreeMap::new(), None)
            .expect_err("expected error");
        assert_eq!(
            error.to_string(),
            "agent metadata requires both platform and model"
        );
    }

    #[test]
    fn reject_secret_like_settings_keys() {
        let mut settings = BTreeMap::new();
        settings.insert(
            "openai_api_key".to_string(),
            Value::String("secret".to_string()),
        );
        let error = build_agent_metadata(Some("cursor"), Some("model"), &settings, None)
            .expect_err("expected error");
        assert_eq!(
            error.to_string(),
            "agent settings must not contain secret-like keys"
        );
    }

    #[test]
    fn accept_unknown_settings_keys_and_values() {
        let mut settings = BTreeMap::new();
        settings.insert(
            "reasoning_effort".to_string(),
            Value::String("turbo".to_string()),
        );
        let agent = build_agent_metadata(Some("cursor"), Some("model"), &settings, None)
            .expect("expected metadata");
        assert_eq!(
            agent
                .expect("metadata present")
                .settings
                .get("reasoning_effort")
                .and_then(|value| value.as_str()),
            Some("turbo")
        );
    }
}
