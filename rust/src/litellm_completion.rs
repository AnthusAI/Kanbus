//! LiteLLM-compatible chat completion client for Kanbus AI features.

use std::env;

use reqwest::blocking::Client;
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE};
use serde::Deserialize;
use serde_json::json;

use crate::ai_credentials::OPENAI_API_KEY_MISSING_MESSAGE;
use crate::error::KanbusError;

const LITELLM_CALLED_ENV: &str = "KANBUS_RIGHT_NOW_LITELLM_CALLED";
const TEST_LITELLM_COMPLETION_ENV: &str = "KANBUS_TEST_LITELLM_COMPLETION";
const OPENAI_CHAT_COMPLETIONS_URL: &str = "https://api.openai.com/v1/chat/completions";

/// Token usage details returned by a chat completion request.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LitellmUsageRecord {
    /// Prompt token count.
    pub prompt_tokens: u64,
    /// Completion token count.
    pub completion_tokens: u64,
    /// Total token count.
    pub total_tokens: u64,
    /// Estimated cost in USD.
    pub cost: f64,
}

/// Run a single-user chat completion through LiteLLM or the OpenAI-compatible API.
///
/// # Arguments
///
/// * `model` - Model identifier configured in `.kanbus.yml`.
/// * `prompt` - User message content.
///
/// # Returns
///
/// Completion text and usage metadata.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when credentials, transport, or response
/// parsing fails.
pub fn litellm_chat_completion(
    model: &str,
    prompt: &str,
) -> Result<(String, LitellmUsageRecord), KanbusError> {
    if let Ok(stub_completion) = env::var(TEST_LITELLM_COMPLETION_ENV) {
        env::set_var(LITELLM_CALLED_ENV, "1");
        return Ok((
            stub_completion,
            LitellmUsageRecord {
                prompt_tokens: 1,
                completion_tokens: 2,
                total_tokens: 3,
                cost: 0.0,
            },
        ));
    }

    let (endpoint, api_key) = resolve_litellm_endpoint_and_api_key()?;
    env::set_var(LITELLM_CALLED_ENV, "1");

    let client = Client::new();
    let response = client
        .post(endpoint)
        .header(CONTENT_TYPE, "application/json")
        .header(AUTHORIZATION, format!("Bearer {api_key}"))
        .json(&json!({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }))
        .send()
        .map_err(|error| {
            KanbusError::IssueOperation(format!("litellm completion request failed: {error}"))
        })?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().unwrap_or_default();
        return Err(KanbusError::IssueOperation(format!(
            "litellm completion request failed with status {}: {}",
            status,
            body.trim()
        )));
    }

    let payload = response.json::<ChatCompletionResponse>().map_err(|error| {
        KanbusError::IssueOperation(format!("litellm completion response parse failed: {error}"))
    })?;

    let completion_text = payload
        .choices
        .first()
        .and_then(|choice| choice.message.content.clone())
        .filter(|content| !content.trim().is_empty())
        .ok_or_else(|| {
            KanbusError::IssueOperation(
                "right-now summary generation returned empty content".to_string(),
            )
        })?;

    let usage = payload.usage.unwrap_or_default();
    let prompt_tokens = usage.prompt_tokens.unwrap_or(0);
    let completion_tokens = usage.completion_tokens.unwrap_or(0);
    let total_tokens = usage
        .total_tokens
        .unwrap_or(prompt_tokens + completion_tokens);

    Ok((
        completion_text,
        LitellmUsageRecord {
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost: 0.0,
        },
    ))
}

fn resolve_litellm_endpoint_and_api_key() -> Result<(String, String), KanbusError> {
    if let Some(base_url) = read_litellm_base_url() {
        let api_key = read_non_empty_env("LITELLM_API_KEY")
            .or_else(|| read_non_empty_env("OPENAI_API_KEY"))
            .ok_or_else(|| {
                KanbusError::IssueOperation(format!(
                    "LITELLM_API_KEY or {OPENAI_API_KEY_MISSING_MESSAGE}"
                ))
            })?;
        let endpoint = join_chat_completions_url(&base_url);
        require_encrypted_transport(&endpoint)?;
        return Ok((endpoint, api_key));
    }

    let api_key = read_non_empty_env("OPENAI_API_KEY")
        .ok_or_else(|| KanbusError::IssueOperation(OPENAI_API_KEY_MISSING_MESSAGE.to_string()))?;

    let endpoint = read_non_empty_env("OPENAI_API_BASE")
        .map(|base| join_chat_completions_url(&base))
        .unwrap_or_else(|| OPENAI_CHAT_COMPLETIONS_URL.to_string());
    require_encrypted_transport(&endpoint)?;

    Ok((endpoint, api_key))
}

/// Refuse to send the API key over a plaintext connection.
///
/// `LITELLM_API_BASE` / `LITELLM_PROXY_URL` / `OPENAI_API_BASE` are
/// operator-configurable, so a misconfigured value could otherwise carry the
/// `Authorization: Bearer` header in cleartext. Loopback addresses are
/// exempt: a local LiteLLM proxy on `http://127.0.0.1:...` or
/// `http://localhost:...` never leaves the machine, which is a common,
/// intentional local-development setup.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when the endpoint is neither
/// `https://` nor a loopback `http://` address.
fn require_encrypted_transport(endpoint: &str) -> Result<(), KanbusError> {
    if endpoint.starts_with("https://") {
        return Ok(());
    }
    if let Some(rest) = endpoint.strip_prefix("http://") {
        let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
        let host = authority.rsplit('@').next().unwrap_or(authority);
        let hostname = if let Some(bracketed) = host.strip_prefix('[') {
            bracketed.split(']').next().unwrap_or("")
        } else {
            host.split(':').next().unwrap_or(host)
        };
        if hostname == "localhost" || hostname == "127.0.0.1" || hostname == "::1" {
            return Ok(());
        }
    }
    Err(KanbusError::IssueOperation(format!(
        "litellm endpoint must use https (or a loopback http:// address for local development): {endpoint}"
    )))
}

fn read_litellm_base_url() -> Option<String> {
    read_non_empty_env("LITELLM_API_BASE").or_else(|| read_non_empty_env("LITELLM_PROXY_URL"))
}

fn read_non_empty_env(name: &str) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn join_chat_completions_url(base_url: &str) -> String {
    let trimmed = base_url.trim_end_matches('/');
    if trimmed.ends_with("/chat/completions") {
        trimmed.to_string()
    } else {
        format!("{trimmed}/chat/completions")
    }
}

#[derive(Debug, Deserialize)]
struct ChatCompletionResponse {
    choices: Vec<ChatCompletionChoice>,
    usage: Option<ChatCompletionUsage>,
}

#[derive(Debug, Deserialize)]
struct ChatCompletionChoice {
    message: ChatCompletionMessage,
}

#[derive(Debug, Deserialize)]
struct ChatCompletionMessage {
    content: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct ChatCompletionUsage {
    prompt_tokens: Option<u64>,
    completion_tokens: Option<u64>,
    total_tokens: Option<u64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn join_chat_completions_url_appends_path() {
        assert_eq!(
            join_chat_completions_url("https://proxy.example.com"),
            "https://proxy.example.com/chat/completions"
        );
        assert_eq!(
            join_chat_completions_url("https://proxy.example.com/v1"),
            "https://proxy.example.com/v1/chat/completions"
        );
        assert_eq!(
            join_chat_completions_url("https://proxy.example.com/chat/completions"),
            "https://proxy.example.com/chat/completions"
        );
    }

    #[test]
    fn require_encrypted_transport_allows_https_and_loopback_http() {
        assert!(require_encrypted_transport("https://api.openai.com/v1/chat/completions").is_ok());
        assert!(require_encrypted_transport("http://127.0.0.1:4000/chat/completions").is_ok());
        assert!(require_encrypted_transport("http://localhost:4000/chat/completions").is_ok());
        assert!(require_encrypted_transport("http://[::1]:4000/chat/completions").is_ok());
    }

    #[test]
    fn require_encrypted_transport_rejects_plaintext_remote_endpoints() {
        let error = require_encrypted_transport("http://proxy.example.com/chat/completions")
            .expect_err("plaintext remote endpoint must be rejected");
        assert!(error.to_string().contains("https"));
    }

    #[test]
    fn litellm_chat_completion_uses_test_stub_without_http() {
        std::env::set_var(TEST_LITELLM_COMPLETION_ENV, "Stubbed native completion.");
        std::env::remove_var(LITELLM_CALLED_ENV);
        let (text, usage) =
            litellm_chat_completion("gpt-4o-mini", "prompt").expect("stub completion");
        assert_eq!(text, "Stubbed native completion.");
        assert_eq!(usage.total_tokens, 3);
        assert_eq!(
            std::env::var(LITELLM_CALLED_ENV).ok(),
            Some("1".to_string())
        );
        std::env::remove_var(TEST_LITELLM_COMPLETION_ENV);
        std::env::remove_var(LITELLM_CALLED_ENV);
    }

    #[test]
    #[serial_test::serial]
    fn resolve_endpoint_error_points_to_setup_ai_when_no_key_is_present() {
        let saved_openai = std::env::var_os("OPENAI_API_KEY");
        let saved_openai_base = std::env::var_os("OPENAI_API_BASE");
        let saved_litellm_key = std::env::var_os("LITELLM_API_KEY");
        let saved_litellm_base = std::env::var_os("LITELLM_API_BASE");
        let saved_litellm_proxy = std::env::var_os("LITELLM_PROXY_URL");
        std::env::remove_var("OPENAI_API_KEY");
        std::env::remove_var("OPENAI_API_BASE");
        std::env::remove_var("LITELLM_API_KEY");
        std::env::remove_var("LITELLM_API_BASE");
        std::env::remove_var("LITELLM_PROXY_URL");

        let error = resolve_litellm_endpoint_and_api_key().expect_err("missing key error");
        assert!(error.to_string().contains("setup ai"));

        match saved_openai {
            Some(value) => std::env::set_var("OPENAI_API_KEY", value),
            None => std::env::remove_var("OPENAI_API_KEY"),
        }
        match saved_openai_base {
            Some(value) => std::env::set_var("OPENAI_API_BASE", value),
            None => std::env::remove_var("OPENAI_API_BASE"),
        }
        match saved_litellm_key {
            Some(value) => std::env::set_var("LITELLM_API_KEY", value),
            None => std::env::remove_var("LITELLM_API_KEY"),
        }
        match saved_litellm_base {
            Some(value) => std::env::set_var("LITELLM_API_BASE", value),
            None => std::env::remove_var("LITELLM_API_BASE"),
        }
        match saved_litellm_proxy {
            Some(value) => std::env::set_var("LITELLM_PROXY_URL", value),
            None => std::env::remove_var("LITELLM_PROXY_URL"),
        }
    }
}
