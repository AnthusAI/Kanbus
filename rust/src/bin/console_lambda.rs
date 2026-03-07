//! Lambda handler for the console backend.

use std::collections::hash_map::DefaultHasher;
use std::convert::Infallible;
use std::hash::{Hash, Hasher};
use std::path::Path;
use std::pin::Pin;
use std::sync::Arc;
use std::time::Duration;

use bytes::Bytes;
use chrono::Utc;
use futures_util::stream::{self, Stream, StreamExt};
use http_body::Frame;
use http_body_util::StreamBody;
use lambda_http::{
    http::StatusCode, run_with_streaming_response, service_fn, Error, Request, Response,
};
use tokio::sync::Mutex;
use tokio_stream::wrappers::IntervalStream;

use kanbus::console_backend::{find_issue_matches, FileStore};

const EFS_ROOT: &str = "/mnt/data";
const DEFAULT_ASSETS_ROOT: &str = "/opt/apps/console/dist";
const REALTIME_MODE: &str = "mqtt_iot";

type BoxedStream = Pin<Box<dyn Stream<Item = Result<Frame<Bytes>, Infallible>> + Send>>;
type StreamBodyType = StreamBody<BoxedStream>;
type ResponseType = Response<StreamBodyType>;

#[tokio::main]
async fn main() -> Result<(), Error> {
    run_with_streaming_response(service_fn(handler)).await
}

async fn handler(request: Request) -> Result<ResponseType, Error> {
    let path = request.uri().path();
    let segments: Vec<&str> = path.trim_start_matches('/').split('/').collect();
    if segments.is_empty() {
        return Ok(not_found());
    }
    if segments[0] == "assets" {
        let asset_path = segments[1..].join("/");
        return Ok(asset_response(&format!("assets/{asset_path}")));
    }
    if segments.len() < 2 {
        return Ok(not_found());
    }
    let account = segments[0];
    let project = segments[1];
    let store_root = FileStore::resolve_tenant_root(Path::new(EFS_ROOT), account, project);
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
    match segments[3] {
        "config" => handle_config(&store),
        "issues" => match segments.get(4) {
            Some(identifier) => handle_issue(&store, identifier),
            None => handle_issues(&store),
        },
        "events" => match segments.get(4) {
            Some(&"realtime") => handle_realtime_events(&store),
            Some(_) => Ok(not_found()),
            None => handle_events(&store),
        },
        "realtime" => match segments.get(4) {
            Some(&"bootstrap") => handle_realtime_bootstrap(account, project),
            _ => Ok(not_found()),
        },
        _ => Ok(not_found()),
    }
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
    let stream = sse_stream(store.clone());
    Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", "text/event-stream")
        .header("Cache-Control", "no-cache")
        .header("Connection", "keep-alive")
        .body(StreamBody::new(stream))
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
    topic: String,
    account: String,
    project: String,
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
    Ok(RealtimeBootstrapResponse {
        mode: REALTIME_MODE,
        region,
        iot_endpoint,
        topic,
        account: account.to_string(),
        project: project.to_string(),
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

fn sse_stream(store: FileStore) -> BoxedStream {
    let (initial_payload, initial_fingerprint) = snapshot_payload(&store);
    let last_fingerprint = Arc::new(Mutex::new(initial_fingerprint));
    let initial = stream::once(async move { Ok(Frame::data(Bytes::from(initial_payload))) });
    let updates_store = store.clone();
    let interval = IntervalStream::new(tokio::time::interval(Duration::from_secs(15)));
    let updates_last = Arc::clone(&last_fingerprint);
    let updates = interval.filter_map(move |_| {
        let store = updates_store.clone();
        let last_fingerprint = Arc::clone(&updates_last);
        async move {
            let (payload, fingerprint) = snapshot_payload(&store);
            let mut guard = last_fingerprint.lock().await;
            if *guard == fingerprint {
                None
            } else {
                *guard = fingerprint;
                Some(Ok(Frame::data(Bytes::from(payload))))
            }
        }
    });
    Box::pin(initial.chain(updates))
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
    (format!("data: {payload}\n\n"), fingerprint)
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

fn body_from_text(text: impl Into<String>) -> StreamBodyType {
    let bytes = Bytes::from(text.into());
    let stream = stream::once(async move { Ok(Frame::data(bytes)) });
    StreamBody::new(Box::pin(stream))
}

fn body_from_bytes(bytes: Vec<u8>) -> StreamBodyType {
    let stream = stream::once(async move { Ok(Frame::data(Bytes::from(bytes))) });
    StreamBody::new(Box::pin(stream))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

    fn clear_realtime_env() {
        // SAFETY: tests in this module are single-threaded and control env usage locally.
        unsafe {
            env::remove_var("KANBUS_IOT_DATA_ENDPOINT");
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
    fn realtime_bootstrap_builds_tenant_scoped_topic() {
        clear_realtime_env();
        // SAFETY: tests in this module are single-threaded and control env usage locally.
        unsafe {
            env::set_var("KANBUS_IOT_DATA_ENDPOINT", "a1b2c3-ats.iot.us-east-1.amazonaws.com");
            env::set_var("AWS_REGION", "us-east-1");
        }
        let payload = build_realtime_bootstrap("acct", "proj").expect("bootstrap payload");
        assert_eq!(payload.mode, REALTIME_MODE);
        assert_eq!(payload.region, "us-east-1");
        assert_eq!(payload.topic, "projects/acct/proj/events");
        assert_eq!(payload.account, "acct");
        assert_eq!(payload.project, "proj");
    }

    #[test]
    fn realtime_bootstrap_requires_endpoint_and_region() {
        clear_realtime_env();
        let missing_endpoint = build_realtime_bootstrap("acct", "proj")
            .expect_err("missing endpoint should return error");
        assert!(missing_endpoint.contains("KANBUS_IOT_DATA_ENDPOINT"));

        // SAFETY: tests in this module are single-threaded and control env usage locally.
        unsafe {
            env::set_var("KANBUS_IOT_DATA_ENDPOINT", "a1b2c3-ats.iot.us-east-1.amazonaws.com");
        }
        let missing_region = build_realtime_bootstrap("acct", "proj")
            .expect_err("missing region should return error");
        assert!(missing_region.contains("AWS_REGION"));
    }
}
