//! Upward LLM summarization for standup rollup.

use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::litellm_completion::litellm_chat_completion;
use crate::models::ProjectConfiguration;
use crate::right_now::ensure_litellm_provider;
use crate::standup::truncate_bullet;
use crate::standup_rollup::dedupe_summary_list;

const TEST_STANDUP_ROLLUP_COMPLETION_ENV: &str = "KANBUS_TEST_STANDUP_ROLLUP_COMPLETION";
const STANDUP_ROLLUP_MAX_LENGTH: usize = 120;

fn build_standup_rollup_reduce_prompt(summaries: &[String], max_length: usize) -> String {
    let lines = summaries
        .iter()
        .map(|summary| format!("- {summary}"))
        .collect::<Vec<_>>()
        .join("\n");
    format!(
        "Write exactly one short sentence a director can act on that summarizes \
the active work below. State what is in flight and any obvious close-out \
signal when present. Do not use semicolons, bullet lists, or issue IDs.\n\
Maximum {max_length} characters.\n\n\
Facts:\n{lines}\n"
    )
}

fn truncate_rollup_text(text: &str) -> String {
    truncate_bullet(text)
}

fn resolve_rollup_model(configuration: &ProjectConfiguration) -> Result<String, KanbusError> {
    if let Some(model) = configuration.right_now.model.as_ref() {
        let trimmed = model.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    let ai = configuration
        .ai
        .as_ref()
        .ok_or_else(|| KanbusError::IssueOperation("AI provider not configured".to_string()))?;
    Ok(ai.model.clone())
}

fn load_rollup_configuration(root: &Path) -> Result<ProjectConfiguration, KanbusError> {
    let path = get_configuration_path(root)?;
    load_project_configuration(&path)
}

fn mock_standup_rollup_reduce(summaries: &[String]) -> String {
    if let Ok(stub) = std::env::var(TEST_STANDUP_ROLLUP_COMPLETION_ENV) {
        let trimmed = stub.trim();
        if !trimmed.is_empty() {
            return truncate_rollup_text(trimmed);
        }
    }
    let first = summaries
        .first()
        .map(|value| value.trim_end_matches('.'))
        .unwrap_or_default();
    truncate_bullet(&format!(
        "{first} and related delivery tracks remain in flight."
    ))
}

/// Synthesize one upward standup summary from child fact lines.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when AI is required and reduction fails.
pub fn reduce_summaries_for_standup_rollup(
    root: &Path,
    summaries: &[String],
) -> Result<String, KanbusError> {
    let deduped = dedupe_summary_list(
        &summaries
            .iter()
            .map(|summary| summary.trim())
            .filter(|summary| !summary.is_empty())
            .map(|summary| summary.to_string())
            .collect::<Vec<_>>(),
    );
    if deduped.is_empty() {
        return Err(KanbusError::IssueOperation(
            "standup rollup reduce requires at least one summary".to_string(),
        ));
    }
    if deduped.len() == 1 {
        return Ok(truncate_rollup_text(&deduped[0]));
    }

    if let Ok(stub) = std::env::var(TEST_STANDUP_ROLLUP_COMPLETION_ENV) {
        let trimmed = stub.trim();
        if !trimmed.is_empty() {
            return Ok(truncate_rollup_text(trimmed));
        }
    }

    if std::env::var("KANBUS_TEST_AI_MOCK").as_deref() == Ok("1") {
        return Ok(mock_standup_rollup_reduce(&deduped));
    }

    let configuration = load_rollup_configuration(root)?;
    ensure_litellm_provider(&configuration)?;
    let model = resolve_rollup_model(&configuration)?;
    let prompt = build_standup_rollup_reduce_prompt(&deduped, STANDUP_ROLLUP_MAX_LENGTH);
    let (completion_text, _usage) = litellm_chat_completion(&model, &prompt)?;
    let trimmed = completion_text.trim();
    if trimmed.is_empty() {
        return Err(KanbusError::IssueOperation(
            "standup rollup reduce returned empty content".to_string(),
        ));
    }
    Ok(truncate_rollup_text(trimmed))
}
