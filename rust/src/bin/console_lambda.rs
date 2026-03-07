//! Lambda handler for the console backend.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::Path;

use base64::Engine as _;
use chrono::Utc;
use lambda_http::{http::StatusCode, run, service_fn, Body, Error, Request, Response};

use kanbus::console_backend::{find_issue_matches, FileStore};

const EFS_ROOT: &str = "/mnt/data";
const DEFAULT_ASSETS_ROOT: &str = "/opt/apps/console/dist";
const REALTIME_MODE: &str = "mqtt_iot";
const AUTH_MODE_NONE: &str = "none";
const AUTH_MODE_COGNITO_PKCE: &str = "cognito_pkce";

type ResponseType = Response<Body>;

#[tokio::main]
async fn main() -> Result<(), Error> {
    run(service_fn(handler)).await
}

async fn handler(request: Request) -> Result<ResponseType, Error> {
    let path = request.uri().path();
    let query = request.uri().query().unwrap_or_default().to_string();
    let raw_segments: Vec<&str> = path
        .trim_start_matches('/')
        .split('/')
        .filter(|segment| !segment.is_empty())
        .collect();
    let segments = normalize_segments(raw_segments);
    if segments.is_empty() {
        return Ok(asset_response("index.html"));
    }
    if segments == vec!["api", "auth", "bootstrap"] {
        return handle_auth_bootstrap(None, None);
    }
    if segments == vec!["auth", "callback"] || segments == vec!["auth", "logout"] {
        return Ok(asset_response("index.html"));
    }
    if segments[0] == "assets" {
        let asset_path = segments[1..].join("/");
        return Ok(asset_response(&format!("assets/{asset_path}")));
    }
    if segments.len() < 2 {
        return Ok(asset_response("index.html"));
    }
    let account = segments[0];
    let project = segments[1];
    let store_root = resolve_store_root(Path::new(EFS_ROOT), account, project);
    let store = FileStore::new(store_root);
    if segments.len() < 3 {
        return Ok(asset_response("index.html"));
    }
    if segments[2] != "api" {
        let tail = segments[2..].join("/");
        if is_console_route(&tail) {
            return Ok(asset_response("index.html"));
        }
        return Ok(asset_response(&tail));
    }
    if segments.len() < 4 {
        return Ok(not_found());
    }
    let token_from_query = query_param(&query, "access_token");
    match segments[3] {
        "telemetry" => match segments.get(4) {
            Some(&"console") => Ok(no_content()),
            _ => Ok(not_found()),
        },
        "config" => {
            if let Err(response) = enforce_tenant_claims(&request, account, project, None) {
                return Ok(response);
            }
            handle_config(&store)
        }
        "issues" => match segments.get(4) {
            Some(identifier) => {
                if let Err(response) = enforce_tenant_claims(&request, account, project, None) {
                    return Ok(response);
                }
                handle_issue(&store, identifier)
            }
            None => {
                if let Err(response) = enforce_tenant_claims(&request, account, project, None) {
                    return Ok(response);
                }
                handle_issues(&store)
            }
        },
        "events" => match segments.get(4) {
            Some(&"realtime") => {
                if let Err(response) =
                    enforce_tenant_claims(&request, account, project, token_from_query.as_deref())
                {
                    return Ok(response);
                }
                handle_realtime_events(&store)
            }
            Some(_) => Ok(not_found()),
            None => {
                if let Err(response) =
                    enforce_tenant_claims(&request, account, project, token_from_query.as_deref())
                {
                    return Ok(response);
                }
                handle_events(&store)
            }
        },
        "realtime" => match segments.get(4) {
            Some(&"bootstrap") => {
                if let Err(response) = enforce_tenant_claims(&request, account, project, None) {
                    return Ok(response);
                }
                handle_realtime_bootstrap(account, project)
            }
            _ => Ok(not_found()),
        },
        "auth" => match segments.get(4) {
            Some(&"bootstrap") => handle_auth_bootstrap(Some(account), Some(project)),
            _ => Ok(not_found()),
        },
        _ => Ok(not_found()),
    }
}

fn normalize_segments(segments: Vec<&str>) -> Vec<&str> {
    if let Ok(stage) = std::env::var("KANBUS_API_STAGE") {
        if segments.first().copied() == Some(stage.as_str()) {
            return segments[1..].to_vec();
        }
    }
    if segments.len() >= 4 && segments[2] != "api" && segments[3] == "api" {
        return segments[1..].to_vec();
    }
    segments
}

fn resolve_store_root(base: &Path, account: &str, project: &str) -> std::path::PathBuf {
    let tenant_root = FileStore::resolve_tenant_root(base, account, project);
    if tenant_root.join(".kanbus.yml").is_file() {
        return tenant_root;
    }
    let repo_root = tenant_root.join("repo");
    if repo_root.join(".kanbus.yml").is_file() {
        return repo_root;
    }
    tenant_root
}

#[derive(Debug, serde::Serialize)]
struct AuthBootstrapResponse {
    mode: String,
    cognito_domain_url: Option<String>,
    cognito_client_id: Option<String>,
    cognito_redirect_uri: Option<String>,
    cognito_logout_uri: Option<String>,
    cognito_issuer: Option<String>,
    identity_pool_id: Option<String>,
    tenant_account_claim_key: String,
    tenant_project_claim_key: String,
    account: Option<String>,
    project: Option<String>,
}

fn handle_auth_bootstrap(
    account: Option<&str>,
    project: Option<&str>,
) -> Result<ResponseType, Error> {
    let auth_mode =
        std::env::var("KANBUS_AUTH_MODE").unwrap_or_else(|_| AUTH_MODE_NONE.to_string());
    if auth_mode == AUTH_MODE_NONE {
        return json_response(&AuthBootstrapResponse {
            mode: AUTH_MODE_NONE.to_string(),
            cognito_domain_url: None,
            cognito_client_id: None,
            cognito_redirect_uri: None,
            cognito_logout_uri: None,
            cognito_issuer: None,
            identity_pool_id: None,
            tenant_account_claim_key: tenant_account_claim_key(),
            tenant_project_claim_key: tenant_project_claim_key(),
            account: account.map(std::string::ToString::to_string),
            project: project.map(std::string::ToString::to_string),
        });
    }
    json_response(&AuthBootstrapResponse {
        mode: AUTH_MODE_COGNITO_PKCE.to_string(),
        cognito_domain_url: std::env::var("KANBUS_COGNITO_DOMAIN_URL").ok(),
        cognito_client_id: std::env::var("KANBUS_COGNITO_CLIENT_ID").ok(),
        cognito_redirect_uri: std::env::var("KANBUS_COGNITO_REDIRECT_URI").ok(),
        cognito_logout_uri: std::env::var("KANBUS_COGNITO_LOGOUT_URI").ok(),
        cognito_issuer: std::env::var("KANBUS_COGNITO_ISSUER").ok(),
        identity_pool_id: std::env::var("KANBUS_IDENTITY_POOL_ID").ok(),
        tenant_account_claim_key: tenant_account_claim_key(),
        tenant_project_claim_key: tenant_project_claim_key(),
        account: account.map(std::string::ToString::to_string),
        project: project.map(std::string::ToString::to_string),
    })
}

fn tenant_account_claim_key() -> String {
    std::env::var("KANBUS_TENANT_ACCOUNT_CLAIM_KEY")
        .unwrap_or_else(|_| "custom:account".to_string())
}

fn tenant_project_claim_key() -> String {
    std::env::var("KANBUS_TENANT_PROJECT_CLAIM_KEY")
        .unwrap_or_else(|_| "custom:project".to_string())
}

fn query_param(query: &str, key: &str) -> Option<String> {
    query
        .split('&')
        .filter_map(|pair| pair.split_once('='))
        .find_map(|(k, v)| if k == key { Some(v.to_string()) } else { None })
}

fn bearer_token(request: &Request) -> Option<String> {
    request.headers().get("Authorization").and_then(|raw| {
        let value = raw.to_str().ok()?;
        let trimmed = value.trim();
        trimmed
            .strip_prefix("Bearer ")
            .or_else(|| trimmed.strip_prefix("bearer "))
            .map(std::string::ToString::to_string)
    })
}

fn decode_jwt_claims(token: &str) -> Option<serde_json::Value> {
    let payload = token.split('.').nth(1)?;
    let bytes = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(payload)
        .ok()?;
    serde_json::from_slice(&bytes).ok()
}

#[allow(clippy::result_large_err)]
fn enforce_tenant_claims(
    request: &Request,
    account: &str,
    project: &str,
    token_from_query: Option<&str>,
) -> Result<(), ResponseType> {
    let auth_mode =
        std::env::var("KANBUS_AUTH_MODE").unwrap_or_else(|_| AUTH_MODE_NONE.to_string());
    if auth_mode == AUTH_MODE_NONE {
        return Ok(());
    }
    let token = bearer_token(request)
        .or_else(|| token_from_query.map(std::string::ToString::to_string))
        .ok_or_else(unauthorized)?;
    let claims = decode_jwt_claims(&token).ok_or_else(unauthorized)?;
    let account_key = tenant_account_claim_key();
    let project_key = tenant_project_claim_key();
    let claim_account = claims
        .get(&account_key)
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    let claim_project = claims
        .get(&project_key)
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    if claim_account != account || claim_project != project {
        return Err(forbidden());
    }
    Ok(())
}

fn unauthorized() -> ResponseType {
    error_response("unauthorized", StatusCode::UNAUTHORIZED)
        .unwrap_or_else(|_| Response::new(body_from_text("{\"error\":\"unauthorized\"}")))
}

fn forbidden() -> ResponseType {
    error_response("forbidden", StatusCode::FORBIDDEN)
        .unwrap_or_else(|_| Response::new(body_from_text("{\"error\":\"forbidden\"}")))
}

fn handle_config(store: &FileStore) -> Result<ResponseType, Error> {
    match store.build_snapshot() {
        Ok(snapshot) => json_response(&snapshot.config),
        Err(error) => error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR),
    }
}

fn handle_issues(store: &FileStore) -> Result<ResponseType, Error> {
    match store.build_snapshot() {
        Ok(snapshot) => json_response(&snapshot.issues),
        Err(error) => error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR),
    }
}

fn handle_issue(store: &FileStore, identifier: &str) -> Result<ResponseType, Error> {
    let snapshot = match store.build_snapshot() {
        Ok(snapshot) => snapshot,
        Err(error) => {
            return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let matches = find_issue_matches(&snapshot.issues, identifier, &snapshot.config.project_key);
    if matches.is_empty() {
        return error_response("issue not found", StatusCode::NOT_FOUND);
    }
    if matches.len() > 1 {
        return error_response("issue id is ambiguous", StatusCode::BAD_REQUEST);
    }
    json_response(matches[0])
}

fn handle_events(store: &FileStore) -> Result<ResponseType, Error> {
    let (payload, _) = snapshot_payload(store);
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", "text/event-stream")
        .header("Cache-Control", "no-cache")
        .header("Connection", "keep-alive")
        .body(Body::Text(format!("data: {payload}\n\n")))
        .map_err(Error::from)
}

fn handle_realtime_events(store: &FileStore) -> Result<ResponseType, Error> {
    // Cloud compatibility endpoint for the existing frontend notification stream.
    // In Lambda mode this currently reuses snapshot-based SSE fallback behavior.
    handle_events(store)
}

#[derive(Debug, serde::Serialize)]
struct RealtimeBootstrapResponse {
    mode: &'static str,
    region: String,
    iot_endpoint: String,
    iot_wss_url: String,
    topic: String,
    account: String,
    project: String,
    mqtt_custom_authorizer_name: Option<String>,
}

fn handle_realtime_bootstrap(account: &str, project: &str) -> Result<ResponseType, Error> {
    let payload = match build_realtime_bootstrap(account, project) {
        Ok(payload) => payload,
        Err(message) => {
            return error_response(message, StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    json_response(&payload)
}

fn build_realtime_bootstrap(
    account: &str,
    project: &str,
) -> Result<RealtimeBootstrapResponse, String> {
    let iot_endpoint = std::env::var("KANBUS_IOT_DATA_ENDPOINT")
        .map_err(|_| "KANBUS_IOT_DATA_ENDPOINT is not configured".to_string())?;
    let region = std::env::var("AWS_REGION")
        .or_else(|_| std::env::var("AWS_DEFAULT_REGION"))
        .map_err(|_| "AWS_REGION is not configured".to_string())?;
    let topic = format!("projects/{account}/{project}/events");
    let iot_wss_url = format!("wss://{iot_endpoint}/mqtt");
    Ok(RealtimeBootstrapResponse {
        mode: REALTIME_MODE,
        region,
        iot_endpoint,
        iot_wss_url,
        topic,
        account: account.to_string(),
        project: project.to_string(),
        mqtt_custom_authorizer_name: std::env::var("KANBUS_MQTT_CUSTOM_AUTHORIZER_NAME").ok(),
    })
}

fn json_response<T: serde::Serialize>(value: &T) -> Result<ResponseType, Error> {
    let body = serde_json::to_string(value).map_err(Error::from)?;
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", "application/json")
        .body(body_from_text(body))
        .map_err(Error::from)
}

fn error_response(message: impl Into<String>, status: StatusCode) -> Result<ResponseType, Error> {
    let payload = serde_json::json!({ "error": message.into() });
    let body = serde_json::to_string(&payload).map_err(Error::from)?;
    Response::builder()
        .status(status)
        .header("Content-Type", "application/json")
        .body(body_from_text(body))
        .map_err(Error::from)
}

fn no_content() -> ResponseType {
    Response::builder()
        .status(StatusCode::NO_CONTENT)
        .body(Body::Empty)
        .unwrap_or_else(|_| Response::new(Body::Empty))
}

fn not_found() -> ResponseType {
    let payload = serde_json::json!({ "error": "not found" });
    let body =
        serde_json::to_string(&payload).unwrap_or_else(|_| "{\"error\":\"not found\"}".into());
    Response::builder()
        .status(StatusCode::NOT_FOUND)
        .header("Content-Type", "application/json")
        .body(body_from_text(body))
        .unwrap_or_else(|_| Response::new(body_from_text("{\"error\":\"not found\"}")))
}

fn is_console_route(path: &str) -> bool {
    if path.is_empty() {
        return true;
    }
    if matches!(path, "initiatives" | "epics" | "issues") {
        return true;
    }
    if let Some(rest) = path.strip_prefix("issues/") {
        let segments: Vec<&str> = rest.split('/').collect();
        if segments.len() == 2 && segments[1] == "all" {
            return true;
        }
        return matches!(segments.len(), 1 | 2);
    }
    false
}

fn asset_response(path: &str) -> ResponseType {
    let root = std::env::var("CONSOLE_ASSETS_ROOT").unwrap_or_else(|_| DEFAULT_ASSETS_ROOT.into());
    let root_path = Path::new(&root);
    let Ok(root_canon) = root_path.canonicalize() else {
        return Response::builder()
            .status(StatusCode::INTERNAL_SERVER_ERROR)
            .header("Content-Type", "application/json")
            .body(body_from_text("{\"error\":\"asset root not found\"}"))
            .unwrap_or_else(|_| {
                Response::new(body_from_text("{\"error\":\"asset root not found\"}"))
            });
    };
    let requested = root_canon.join(path);
    let Ok(asset_path) = requested.canonicalize() else {
        return not_found();
    };
    if !asset_path.starts_with(&root_canon) || asset_path.is_dir() {
        return not_found();
    }
    let bytes = match std::fs::read(&asset_path) {
        Ok(bytes) => bytes,
        Err(_) => return not_found(),
    };
    let content_type = mime_guess::from_path(&asset_path)
        .first_or_octet_stream()
        .to_string();
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", content_type)
        .body(body_from_bytes(bytes))
        .unwrap_or_else(|_| Response::new(body_from_text("{\"error\":\"asset response failed\"}")))
}

fn snapshot_payload(store: &FileStore) -> (String, u64) {
    let (payload, fingerprint) = match store.build_snapshot() {
        Ok(snapshot) => {
            let fingerprint = snapshot_fingerprint(&snapshot);
            let payload = serde_json::to_string(&snapshot).unwrap_or_else(|error| {
                serde_json::json!({ "error": error.to_string(), "updated_at": Utc::now().to_rfc3339() })
                    .to_string()
            });
            (payload, fingerprint)
        }
        Err(error) => {
            let payload = serde_json::json!({
                "error": error.to_string(),
                "updated_at": Utc::now().to_rfc3339(),
            })
            .to_string();
            (payload.clone(), hash_payload(&payload))
        }
    };
    (payload, fingerprint)
}

fn snapshot_fingerprint(snapshot: &kanbus::console_backend::ConsoleSnapshot) -> u64 {
    let payload = serde_json::to_vec(&(&snapshot.config, &snapshot.issues)).unwrap_or_default();
    hash_bytes(&payload)
}

fn hash_payload(payload: &str) -> u64 {
    hash_bytes(payload.as_bytes())
}

fn hash_bytes(bytes: &[u8]) -> u64 {
    let mut hasher = DefaultHasher::new();
    bytes.hash(&mut hasher);
    hasher.finish()
}

fn body_from_text(text: impl Into<String>) -> Body {
    Body::Text(text.into())
}

fn body_from_bytes(bytes: Vec<u8>) -> Body {
    Body::Binary(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::sync::{Mutex, OnceLock};

    fn realtime_env_guard() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .expect("env lock")
    }

    fn clear_realtime_env() {
        // SAFETY: guarded by module-level mutex in realtime tests.
        unsafe {
            env::remove_var("KANBUS_AUTH_MODE");
            env::remove_var("KANBUS_COGNITO_DOMAIN_URL");
            env::remove_var("KANBUS_COGNITO_CLIENT_ID");
            env::remove_var("KANBUS_COGNITO_REDIRECT_URI");
            env::remove_var("KANBUS_COGNITO_LOGOUT_URI");
            env::remove_var("KANBUS_COGNITO_ISSUER");
            env::remove_var("KANBUS_IDENTITY_POOL_ID");
            env::remove_var("KANBUS_TENANT_ACCOUNT_CLAIM_KEY");
            env::remove_var("KANBUS_TENANT_PROJECT_CLAIM_KEY");
            env::remove_var("KANBUS_IOT_DATA_ENDPOINT");
            env::remove_var("KANBUS_MQTT_CUSTOM_AUTHORIZER_NAME");
            env::remove_var("KANBUS_API_STAGE");
            env::remove_var("AWS_REGION");
            env::remove_var("AWS_DEFAULT_REGION");
        }
    }

    #[test]
    fn is_console_route_detects_supported_paths() {
        assert!(is_console_route(""));
        assert!(is_console_route("issues"));
        assert!(is_console_route("issues/kanbus-1"));
        assert!(is_console_route("issues/kanbus-parent/all"));
        assert!(!is_console_route("assets/app.js"));
    }

    #[test]
    fn hash_helpers_are_stable_for_same_payload() {
        let one = hash_payload("payload");
        let two = hash_payload("payload");
        let bytes_hash = hash_bytes(b"payload");
        assert_eq!(one, two);
        assert_eq!(one, bytes_hash);
    }

    #[test]
    fn normalize_segments_strips_configured_stage_prefix() {
        let _guard = realtime_env_guard();
        clear_realtime_env();
        // SAFETY: guarded by module-level mutex in realtime tests.
        unsafe {
            env::set_var("KANBUS_API_STAGE", "dev");
        }
        let normalized = normalize_segments(vec!["dev", "anthus", "kanbus", "api", "config"]);
        assert_eq!(normalized, vec!["anthus", "kanbus", "api", "config"]);
    }

    #[test]
    fn normalize_segments_falls_back_to_api_shape_detection() {
        let _guard = realtime_env_guard();
        clear_realtime_env();
        let normalized = normalize_segments(vec!["prod", "anthus", "kanbus", "api", "issues"]);
        assert_eq!(normalized, vec!["anthus", "kanbus", "api", "issues"]);
    }

    #[test]
    fn resolve_store_root_prefers_repo_checkout_when_present() {
        let temp = tempfile::tempdir().expect("tempdir");
        let base = temp.path();
        let tenant_repo = base.join("anthus").join("kanbus").join("repo");
        std::fs::create_dir_all(&tenant_repo).expect("create repo root");
        std::fs::write(tenant_repo.join(".kanbus.yml"), "project_key: kbs").expect("write config");

        let resolved = resolve_store_root(base, "anthus", "kanbus");
        assert_eq!(resolved, tenant_repo);
    }

    #[test]
    fn realtime_bootstrap_builds_tenant_scoped_topic() {
        let _guard = realtime_env_guard();
        clear_realtime_env();
        // SAFETY: guarded by module-level mutex in realtime tests.
        unsafe {
            env::set_var(
                "KANBUS_IOT_DATA_ENDPOINT",
                "a1b2c3-ats.iot.us-east-1.amazonaws.com",
            );
            env::set_var("AWS_REGION", "us-east-1");
        }
        let payload = build_realtime_bootstrap("acct", "proj").expect("bootstrap payload");
        assert_eq!(payload.mode, REALTIME_MODE);
        assert_eq!(payload.region, "us-east-1");
        assert_eq!(
            payload.iot_wss_url,
            "wss://a1b2c3-ats.iot.us-east-1.amazonaws.com/mqtt"
        );
        assert_eq!(payload.topic, "projects/acct/proj/events");
        assert_eq!(payload.account, "acct");
        assert_eq!(payload.project, "proj");
        assert_eq!(payload.mqtt_custom_authorizer_name, None);

        // SAFETY: guarded by module-level mutex in realtime tests.
        unsafe {
            env::set_var("KANBUS_MQTT_CUSTOM_AUTHORIZER_NAME", "kanbus-mqtt-token-dev");
        }
        let payload_with_authorizer =
            build_realtime_bootstrap("acct", "proj").expect("bootstrap payload");
        assert_eq!(
            payload_with_authorizer.mqtt_custom_authorizer_name.as_deref(),
            Some("kanbus-mqtt-token-dev")
        );
    }

    #[test]
    fn realtime_bootstrap_requires_endpoint_and_region() {
        let _guard = realtime_env_guard();
        clear_realtime_env();
        let missing_endpoint = build_realtime_bootstrap("acct", "proj")
            .expect_err("missing endpoint should return error");
        assert!(missing_endpoint.contains("KANBUS_IOT_DATA_ENDPOINT"));

        // SAFETY: guarded by module-level mutex in realtime tests.
        unsafe {
            env::set_var(
                "KANBUS_IOT_DATA_ENDPOINT",
                "a1b2c3-ats.iot.us-east-1.amazonaws.com",
            );
        }
        let missing_region = build_realtime_bootstrap("acct", "proj")
            .expect_err("missing region should return error");
        assert!(missing_region.contains("AWS_REGION"));
    }

    #[test]
    fn auth_bootstrap_defaults_to_none_mode() {
        let _guard = realtime_env_guard();
        clear_realtime_env();
        let response = handle_auth_bootstrap(Some("anthus"), Some("kanbus")).expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[test]
    fn query_param_extracts_expected_value() {
        let value = query_param("access_token=abc&foo=bar", "access_token");
        assert_eq!(value.as_deref(), Some("abc"));
        assert_eq!(query_param("foo=bar", "access_token"), None);
    }

    #[test]
    fn decode_jwt_claims_parses_payload() {
        let payload = base64::engine::general_purpose::URL_SAFE_NO_PAD
            .encode(r#"{"custom:account":"anthus","custom:project":"kanbus"}"#);
        let token = format!("aaa.{payload}.bbb");
        let claims = decode_jwt_claims(&token).expect("claims");
        assert_eq!(claims["custom:account"], "anthus");
        assert_eq!(claims["custom:project"], "kanbus");
    }
}
