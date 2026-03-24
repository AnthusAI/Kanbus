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

fn tokens_url(base_url: &str) -> String {
    format!("{}/api/tokens", trim_base(base_url))
}

fn revoke_url(base_url: &str, token_id: &str) -> String {
    format!(
        "{}/api/tokens/{}/revoke",
        trim_base(base_url),
        token_id.trim_start_matches("kbt_")
    )
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
        .post(tokens_url(base_url))
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
    serde_json::to_string_pretty(&parsed)
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

pub fn list_cloud_tokens(
    base_url: &str,
    id_token: &str,
    account: Option<&str>,
    project: Option<&str>,
) -> Result<String, KanbusError> {
    let client = build_client(id_token)?;
    let mut request = client.get(tokens_url(base_url));
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
    serde_json::to_string_pretty(&parsed)
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

pub fn revoke_cloud_token(
    base_url: &str,
    id_token: &str,
    token_id: &str,
) -> Result<String, KanbusError> {
    let client = build_client(id_token)?;
    let response = client
        .post(revoke_url(base_url, token_id))
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
    serde_json::to_string_pretty(&parsed)
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::mpsc::{self, Receiver};
    use std::thread;
    use std::time::Duration;

    fn spawn_http_server(status: &str, body: &str) -> (String, Receiver<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind test listener");
        let addr = listener.local_addr().expect("read local addr");
        let (tx, rx) = mpsc::channel::<String>();
        let response_body = body.to_string();
        let status_line = status.to_string();
        thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept connection");
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .expect("set read timeout");
            let mut buffer = [0_u8; 8192];
            let bytes_read = stream.read(&mut buffer).expect("read request");
            let request = String::from_utf8_lossy(&buffer[..bytes_read]).to_string();
            let _ = tx.send(request);
            let response = format!(
                "HTTP/1.1 {status_line}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response_body}",
                response_body.len()
            );
            let _ = stream.write_all(response.as_bytes());
        });
        (format!("http://{addr}"), rx)
    }

    #[test]
    fn trim_base_removes_trailing_slashes() {
        assert_eq!(
            trim_base("https://api.example.com/"),
            "https://api.example.com"
        );
        assert_eq!(
            trim_base("https://api.example.com///"),
            "https://api.example.com"
        );
        assert_eq!(
            trim_base("https://api.example.com"),
            "https://api.example.com"
        );
    }

    #[test]
    fn build_client_rejects_invalid_bearer_header_value() {
        let error = build_client("bad\ntoken").expect_err("expected invalid header error");
        assert!(error.to_string().contains("header"));
    }

    #[test]
    fn tokens_and_revoke_urls_are_normalized() {
        assert_eq!(
            tokens_url("https://api.example.com///"),
            "https://api.example.com/api/tokens"
        );
        assert_eq!(
            revoke_url("https://api.example.com/", "kbt_abc123"),
            "https://api.example.com/api/tokens/abc123/revoke"
        );
        assert_eq!(
            revoke_url("https://api.example.com", "raw-id"),
            "https://api.example.com/api/tokens/raw-id/revoke"
        );
    }

    #[test]
    fn create_cloud_token_posts_payload_and_returns_pretty_json() {
        let (base_url, request_rx) = spawn_http_server(
            "200 OK",
            r#"{"token_id":"kbt_1","token":"secret","account":"acct","project":"proj","scopes":["read"],"created_at":"2026-03-09T00:00:00Z","expires_at":"2026-04-08T00:00:00Z","revoked":false}"#,
        );
        let response = create_cloud_token(
            &base_url,
            "id-token",
            "acct",
            "proj",
            vec!["read".to_string()],
            30,
        )
        .expect("create token response");
        let request = request_rx.recv().expect("captured request");
        assert!(request.starts_with("POST /api/tokens HTTP/1.1"));
        assert!(request.contains("\"account\":\"acct\""));
        assert!(response.contains("\"token_id\": \"kbt_1\""));
    }

    #[test]
    fn list_cloud_tokens_includes_optional_query_parameters() {
        let (base_url, request_rx) = spawn_http_server(
            "200 OK",
            r#"{"tokens":[{"id":"kbt_1"}],"count":1,"at":"2026-03-09T00:00:00Z"}"#,
        );
        let response = list_cloud_tokens(&base_url, "id-token", Some("acct"), Some("proj"))
            .expect("list token response");
        let request = request_rx.recv().expect("captured request");
        assert!(request.starts_with("GET /api/tokens?account=acct&project=proj HTTP/1.1"));
        assert!(response.contains("\"count\": 1"));
    }

    #[test]
    fn revoke_cloud_token_strips_kbt_prefix_from_token_id() {
        let (base_url, request_rx) =
            spawn_http_server("200 OK", r#"{"token_id":"abc123","revoked":true}"#);
        let response =
            revoke_cloud_token(&base_url, "id-token", "kbt_abc123").expect("revoke token response");
        let request = request_rx.recv().expect("captured request");
        assert!(request.starts_with("POST /api/tokens/abc123/revoke HTTP/1.1"));
        assert!(response.contains("\"revoked\": true"));
    }

    #[test]
    fn cloud_token_requests_return_error_on_non_success_status() {
        let (create_base, _) = spawn_http_server("500 Internal Server Error", "{}");
        let create_error = create_cloud_token(
            &create_base,
            "id-token",
            "acct",
            "proj",
            vec!["read".to_string()],
            7,
        )
        .expect_err("expected create failure");
        assert!(create_error
            .to_string()
            .contains("token create request failed:"));

        let (list_base, _) = spawn_http_server("403 Forbidden", "{}");
        let list_error = list_cloud_tokens(&list_base, "id-token", None, None)
            .expect_err("expected list failure");
        assert!(list_error
            .to_string()
            .contains("token list request failed:"));

        let (revoke_base, _) = spawn_http_server("404 Not Found", "{}");
        let revoke_error = revoke_cloud_token(&revoke_base, "id-token", "kbt_missing")
            .expect_err("expected revoke failure");
        assert!(revoke_error
            .to_string()
            .contains("token revoke request failed:"));
    }

    #[test]
    fn cloud_token_requests_return_error_on_invalid_json_body() {
        let (create_base, _) = spawn_http_server("200 OK", "{");
        let create_error = create_cloud_token(
            &create_base,
            "id-token",
            "acct",
            "proj",
            vec!["read".to_string()],
            7,
        )
        .expect_err("expected create parse failure");
        assert!(!create_error.to_string().is_empty());

        let (list_base, _) = spawn_http_server("200 OK", "{");
        let list_error = list_cloud_tokens(&list_base, "id-token", None, None)
            .expect_err("expected list parse failure");
        assert!(!list_error.to_string().is_empty());

        let (revoke_base, _) = spawn_http_server("200 OK", "{");
        let revoke_error = revoke_cloud_token(&revoke_base, "id-token", "kbt_123")
            .expect_err("expected revoke parse failure");
        assert!(!revoke_error.to_string().is_empty());
    }
}
