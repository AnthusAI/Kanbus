//! Cloud token management client helpers.

use crate::error::KanbusError;
use reqwest::blocking::Client;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
struct CreateTokenRequest {
    account: String,
    project: String,
    scopes: Vec<String>,
    expires_in_days: u16,
}

#[derive(Debug, Deserialize, Serialize)]
struct TokenCreateResponse {
    token_id: String,
    token: String,
    account: String,
    project: String,
    scopes: Vec<String>,
    created_at: String,
    expires_at: String,
    revoked: bool,
}

#[derive(Debug, Deserialize, Serialize)]
struct TokenListResponse {
    tokens: Vec<serde_json::Value>,
    count: usize,
    at: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct TokenRevokeResponse {
    token_id: String,
    revoked: bool,
}

fn build_client(id_token: &str) -> Result<Client, KanbusError> {
    let mut headers = HeaderMap::new();
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {id_token}"))
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))?,
    );
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    Client::builder()
        .default_headers(headers)
        .build()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

fn trim_base(base_url: &str) -> String {
    base_url.trim_end_matches('/').to_string()
}

pub fn create_cloud_token(
    base_url: &str,
    id_token: &str,
    account: &str,
    project: &str,
    scopes: Vec<String>,
    expires_in_days: u16,
) -> Result<String, KanbusError> {
    let client = build_client(id_token)?;
    let payload = CreateTokenRequest {
        account: account.to_string(),
        project: project.to_string(),
        scopes,
        expires_in_days,
    };
    let response = client
        .post(format!("{}/api/tokens", trim_base(base_url)))
        .json(&payload)
        .send()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    if !response.status().is_success() {
        return Err(KanbusError::IssueOperation(format!(
            "token create request failed: {}",
            response.status()
        )));
    }
    let parsed: TokenCreateResponse = response
        .json()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    serde_json::to_string_pretty(&parsed).map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

pub fn list_cloud_tokens(
    base_url: &str,
    id_token: &str,
    account: Option<&str>,
    project: Option<&str>,
) -> Result<String, KanbusError> {
    let client = build_client(id_token)?;
    let mut request = client.get(format!("{}/api/tokens", trim_base(base_url)));
    if let Some(account) = account {
        request = request.query(&[("account", account)]);
    }
    if let Some(project) = project {
        request = request.query(&[("project", project)]);
    }
    let response = request
        .send()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    if !response.status().is_success() {
        return Err(KanbusError::IssueOperation(format!(
            "token list request failed: {}",
            response.status()
        )));
    }
    let parsed: TokenListResponse = response
        .json()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    serde_json::to_string_pretty(&parsed).map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

pub fn revoke_cloud_token(
    base_url: &str,
    id_token: &str,
    token_id: &str,
) -> Result<String, KanbusError> {
    let client = build_client(id_token)?;
    let response = client
        .post(format!(
            "{}/api/tokens/{}/revoke",
            trim_base(base_url),
            token_id.trim_start_matches("kbt_")
        ))
        .send()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    if !response.status().is_success() {
        return Err(KanbusError::IssueOperation(format!(
            "token revoke request failed: {}",
            response.status()
        )));
    }
    let parsed: TokenRevokeResponse = response
        .json()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    serde_json::to_string_pretty(&parsed).map_err(|error| KanbusError::IssueOperation(error.to_string()))
}
