//! Local HTTP server for the console backend.

use std::collections::hash_map::DefaultHasher;
use std::convert::Infallible;
use std::hash::{Hash, Hasher};
use std::io::{self, IsTerminal, Write};
use std::net::SocketAddr;
use std::path::Path as StdPath;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use axum::body::Body;
use axum::extract::{Path as AxumPath, State};
use axum::http::header::CONTENT_TYPE;
use axum::http::StatusCode;
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use axum::response::Response;
use axum::routing::{get, post};
use axum::Json;
use axum::Router;
use futures_util::stream;
use futures_util::stream::BoxStream;
use futures_util::Stream;
use futures_util::StreamExt;
use serde_json::Value as JsonValue;
use tokio::sync::broadcast;
use tokio::sync::Mutex;
use tokio_stream::wrappers::BroadcastStream;
use tokio_stream::wrappers::IntervalStream;

use kanbus::console_backend::{find_issue_matches, FileStore};

#[cfg(feature = "embed-assets")]
use rust_embed::RustEmbed;

#[cfg(feature = "embed-assets")]
#[derive(RustEmbed)]
#[folder = "../apps/console/dist"]
struct EmbeddedAssets;

#[derive(Clone)]
struct AppState {
    base_root: PathBuf,
    assets_root: PathBuf,
    multi_tenant: bool,
    assets_root_explicit: bool,
    telemetry_tx: broadcast::Sender<String>,
}

#[tokio::main]
async fn main() {
    let repo_root = resolve_repo_root();
    let root_override = std::env::var("CONSOLE_ROOT").ok().map(PathBuf::from);
    let data_root = std::env::var("CONSOLE_DATA_ROOT")
        .ok()
        .map(PathBuf::from)
        .or_else(|| root_override.clone())
        .unwrap_or_else(|| repo_root.clone());

    // Try to load console_port from project config
    let config_port = FileStore::new(&data_root)
        .load_config()
        .ok()
        .and_then(|cfg| cfg.console_port);

    let desired_port = std::env::var("CONSOLE_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .or(config_port)
        .unwrap_or(5174);

    let assets_root_explicit = std::env::var("CONSOLE_ASSETS_ROOT").is_ok();
    let assets_root = std::env::var("CONSOLE_ASSETS_ROOT")
        .ok()
        .map(PathBuf::from)
        .or_else(|| {
            root_override
                .clone()
                .map(|root| root.join("apps/console/dist"))
        })
        .unwrap_or_else(|| repo_root.join("apps/console/dist"));

    let multi_tenant = std::env::var("CONSOLE_TENANT_MODE")
        .map(|value| value == "multi")
        .unwrap_or(false);

    let (telemetry_tx, _) = broadcast::channel(256);
    let state = AppState {
        base_root: data_root,
        assets_root,
        multi_tenant,
        assets_root_explicit,
        telemetry_tx,
    };

    let app = Router::new()
        .route("/assets/*path", get(get_public_asset))
        .route("/api/config", get(get_config_root))
        .route("/api/issues", get(get_issues_root))
        .route("/api/issues/:id", get(get_issue_root))
        .route("/api/events", get(get_events_root))
        .route("/api/telemetry/console", post(post_console_telemetry_root))
        .route(
            "/api/telemetry/console/events",
            get(get_console_telemetry_events_root),
        )
        .route("/", get(get_index_root))
        .route("/initiatives/", get(get_index_root))
        .route("/epics/", get(get_index_root))
        .route("/issues/", get(get_index_root))
        .route("/issues/:parent/all", get(get_index_root))
        .route("/issues/:id", get(get_index_root))
        .route("/issues/:parent/:id", get(get_index_root))
        .route("/:account/:project/api/config", get(get_config))
        .route("/:account/:project/api/issues", get(get_issues))
        .route("/:account/:project/api/issues/:id", get(get_issue))
        .route("/:account/:project/api/events", get(get_events))
        .route(
            "/:account/:project/api/telemetry/console",
            post(post_console_telemetry),
        )
        .route(
            "/:account/:project/api/telemetry/console/events",
            get(get_console_telemetry_events),
        )
        .route("/:account/:project/", get(get_index))
        .route("/:account/:project/initiatives/", get(get_index))
        .route("/:account/:project/epics/", get(get_index))
        .route("/:account/:project/issues/", get(get_index))
        .route("/:account/:project/issues/:parent/all", get(get_index))
        .route("/:account/:project/issues/:id", get(get_index))
        .route("/:account/:project/issues/:parent/:id", get(get_index))
        .route("/:account/:project/*path", get(get_asset))
        .fallback(get(get_asset_root))
        .with_state(state);

    let (listener, port) = acquire_listener(desired_port).await;

    #[cfg(feature = "embed-assets")]
    println!("Console backend listening on http://127.0.0.1:{port} (embedded assets)");
    #[cfg(not(feature = "embed-assets"))]
    {
        // Verify assets directory exists before starting server
        if !state.assets_root.exists() {
            eprintln!(
                "\nWARNING: Console assets directory not found at {:?}",
                state.assets_root
            );
            eprintln!("The console UI will not work until you:");
            eprintln!("1. Build the UI: cd apps/console && npm install && npm run build");
            eprintln!("2. Set CONSOLE_ASSETS_ROOT to the correct dist directory");
            eprintln!(
                "3. Or reinstall with: cargo install kanbus --bin kbsc --features embed-assets\n"
            );
        }
        println!(
            "Console backend listening on http://127.0.0.1:{port} (filesystem assets at {:?})",
            state.assets_root
        );
    }

    axum::serve(listener, app.into_make_service())
        .await
        .expect("server failure");
}

async fn acquire_listener(desired_port: u16) -> (tokio::net::TcpListener, u16) {
    let initial_addr = SocketAddr::from(([127, 0, 0, 1], desired_port));
    match tokio::net::TcpListener::bind(initial_addr).await {
        Ok(listener) => (listener, desired_port),
        Err(error) if error.kind() == std::io::ErrorKind::AddrInUse => {
            let fallback_port = desired_port.saturating_add(1);
            if fallback_port > u16::MAX - 1 {
                exit_with_port_error(desired_port, "No valid fallback port is available.");
            }
            let consented = if io::stdin().is_terminal() && io::stdout().is_terminal() {
                prompt_for_port_switch(desired_port, fallback_port)
            } else {
                eprintln!(
                    "Console port {desired_port} is in use. Switching automatically to {fallback_port}."
                );
                true
            };
            if !consented {
                exit_with_port_error(
                    desired_port,
                    "Port is in use. Set CONSOLE_PORT to a free port and retry.",
                );
            }
            let fallback_addr = SocketAddr::from(([127, 0, 0, 1], fallback_port));
            match tokio::net::TcpListener::bind(fallback_addr).await {
                Ok(listener) => (listener, fallback_port),
                Err(fallback_error) => exit_with_port_error(
                    desired_port,
                    &format!(
                        "Port {desired_port} is in use and fallback port {fallback_port} failed: {fallback_error}"
                    ),
                ),
            }
        }
        Err(error) => exit_with_port_error(desired_port, &format!("Failed to bind: {error}")),
    }
}

fn prompt_for_port_switch(current: u16, fallback: u16) -> bool {
    print!("Console port {current} is already in use. Bump to {fallback}? [y/N] ");
    let _ = io::stdout().flush();
    let mut buffer = String::new();
    if io::stdin().read_line(&mut buffer).is_err() {
        return false;
    }
    buffer.trim().to_lowercase().starts_with('y')
}

fn exit_with_port_error(port: u16, message: &str) -> ! {
    eprintln!("{message} (requested port: {port})");
    std::process::exit(1);
}

async fn get_config(
    State(state): State<AppState>,
    AxumPath((account, project)): AxumPath<(String, String)>,
) -> Response {
    let store = store_for(&state, &account, &project);
    match store.build_snapshot() {
        Ok(snapshot) => Json(snapshot.config).into_response(),
        Err(error) => error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn get_config_root(State(state): State<AppState>) -> Response {
    let store = match store_for_root(&state) {
        Some(store) => store,
        None => {
            return error_response(
                "multi-tenant mode requires /:account/:project",
                StatusCode::BAD_REQUEST,
            )
        }
    };
    match store.build_snapshot() {
        Ok(snapshot) => Json(snapshot.config).into_response(),
        Err(error) => error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn get_issues(
    State(state): State<AppState>,
    AxumPath((account, project)): AxumPath<(String, String)>,
) -> Response {
    let store = store_for(&state, &account, &project);
    match store.build_snapshot() {
        Ok(snapshot) => Json(snapshot.issues).into_response(),
        Err(error) => error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn get_issues_root(State(state): State<AppState>) -> Response {
    let store = match store_for_root(&state) {
        Some(store) => store,
        None => {
            return error_response(
                "multi-tenant mode requires /:account/:project",
                StatusCode::BAD_REQUEST,
            )
        }
    };
    match store.build_snapshot() {
        Ok(snapshot) => Json(snapshot.issues).into_response(),
        Err(error) => error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR),
    }
}

async fn get_issue(
    State(state): State<AppState>,
    AxumPath((account, project, id)): AxumPath<(String, String, String)>,
) -> Response {
    let store = store_for(&state, &account, &project);
    let snapshot = match store.build_snapshot() {
        Ok(snapshot) => snapshot,
        Err(error) => {
            return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let matches = find_issue_matches(&snapshot.issues, &id, &snapshot.config.project_key);
    if matches.is_empty() {
        return error_response("issue not found", StatusCode::NOT_FOUND);
    }
    if matches.len() > 1 {
        return error_response("issue id is ambiguous", StatusCode::BAD_REQUEST);
    }
    Json(matches[0]).into_response()
}

async fn get_issue_root(State(state): State<AppState>, AxumPath(id): AxumPath<String>) -> Response {
    let store = match store_for_root(&state) {
        Some(store) => store,
        None => {
            return error_response(
                "multi-tenant mode requires /:account/:project",
                StatusCode::BAD_REQUEST,
            )
        }
    };
    let snapshot = match store.build_snapshot() {
        Ok(snapshot) => snapshot,
        Err(error) => {
            return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let matches = find_issue_matches(&snapshot.issues, &id, &snapshot.config.project_key);
    if matches.is_empty() {
        return error_response("issue not found", StatusCode::NOT_FOUND);
    }
    if matches.len() > 1 {
        return error_response("issue id is ambiguous", StatusCode::BAD_REQUEST);
    }
    Json(matches[0]).into_response()
}

async fn get_events(
    State(state): State<AppState>,
    AxumPath((account, project)): AxumPath<(String, String)>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let store = store_for(&state, &account, &project);
    let (initial_payload, initial_fingerprint) = snapshot_payload(&store);
    let last_fingerprint = Arc::new(Mutex::new(initial_fingerprint));
    let initial = stream::once(async move { Ok(Event::default().data(initial_payload)) });
    let interval = IntervalStream::new(tokio::time::interval(Duration::from_secs(15)));
    let updates_store = store.clone();
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
                Some(Ok(Event::default().data(payload)))
            }
        }
    });
    let stream = initial.chain(updates);

    Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text(": keep-alive"),
    )
}

async fn get_events_root(
    State(state): State<AppState>,
) -> Sse<BoxStream<'static, Result<Event, Infallible>>> {
    let store = match store_for_root(&state) {
        Some(store) => store,
        None => {
            let payload = serde_json::json!({
                "error": "multi-tenant mode requires /:account/:project",
                "updated_at": chrono::Utc::now().to_rfc3339(),
            })
            .to_string();
            let stream = stream::once(async move { Ok(Event::default().data(payload)) }).boxed();
            return Sse::new(stream).keep_alive(
                KeepAlive::new()
                    .interval(Duration::from_secs(15))
                    .text(": keep-alive"),
            );
        }
    };
    let (initial_payload, initial_fingerprint) = snapshot_payload(&store);
    let last_fingerprint = Arc::new(Mutex::new(initial_fingerprint));
    let initial = stream::once(async move { Ok(Event::default().data(initial_payload)) });
    let interval = IntervalStream::new(tokio::time::interval(Duration::from_secs(15)));
    let updates_store = store.clone();
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
                Some(Ok(Event::default().data(payload)))
            }
        }
    });
    let stream = initial.chain(updates).boxed();

    Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text(": keep-alive"),
    )
}

async fn post_console_telemetry_root(
    State(state): State<AppState>,
    Json(payload): Json<JsonValue>,
) -> StatusCode {
    let message = build_telemetry_payload(payload, None);
    let _ = state.telemetry_tx.send(message);
    StatusCode::NO_CONTENT
}

async fn post_console_telemetry(
    State(state): State<AppState>,
    AxumPath((account, project)): AxumPath<(String, String)>,
    Json(payload): Json<JsonValue>,
) -> StatusCode {
    let message = build_telemetry_payload(payload, Some((account, project)));
    let _ = state.telemetry_tx.send(message);
    StatusCode::NO_CONTENT
}

async fn get_console_telemetry_events_root(
    State(state): State<AppState>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let receiver = state.telemetry_tx.subscribe();
    let stream = BroadcastStream::new(receiver).filter_map(|payload| async move {
        match payload {
            Ok(data) => Some(Ok(Event::default().data(data))),
            Err(_) => None,
        }
    });
    Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text(": keep-alive"),
    )
}

async fn get_console_telemetry_events(
    State(state): State<AppState>,
    AxumPath((_account, _project)): AxumPath<(String, String)>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    get_console_telemetry_events_root(State(state)).await
}

fn build_telemetry_payload(payload: JsonValue, tenant: Option<(String, String)>) -> String {
    let mut map = serde_json::Map::new();
    map.insert(
        "received_at".to_string(),
        JsonValue::String(chrono::Utc::now().to_rfc3339()),
    );
    if let Some((account, project)) = tenant {
        map.insert("account".to_string(), JsonValue::String(account));
        map.insert("project".to_string(), JsonValue::String(project));
    }
    if let JsonValue::Object(object) = payload {
        for (key, value) in object {
            map.insert(key, value);
        }
    } else {
        map.insert("payload".to_string(), payload);
    }
    JsonValue::Object(map).to_string()
}

fn store_for(state: &AppState, account: &str, project: &str) -> FileStore {
    let root = if state.multi_tenant {
        FileStore::resolve_tenant_root(&state.base_root, account, project)
    } else {
        state.base_root.clone()
    };
    FileStore::new(root)
}

fn store_for_root(state: &AppState) -> Option<FileStore> {
    if state.multi_tenant {
        return None;
    }
    Some(FileStore::new(state.base_root.clone()))
}

fn error_response(message: impl Into<String>, status: StatusCode) -> Response {
    let payload = serde_json::json!({ "error": message.into() });
    (status, Json(payload)).into_response()
}

fn snapshot_payload(store: &FileStore) -> (String, u64) {
    match store.build_snapshot() {
        Ok(snapshot) => {
            let fingerprint = snapshot_fingerprint(&snapshot);
            let payload = serde_json::to_string(&snapshot).unwrap_or_else(|error| {
                serde_json::json!({
                    "error": error.to_string(),
                    "updated_at": chrono::Utc::now().to_rfc3339(),
                })
                .to_string()
            });
            (payload, fingerprint)
        }
        Err(error) => {
            let payload = serde_json::json!({
                "error": error.to_string(),
                "updated_at": chrono::Utc::now().to_rfc3339(),
            })
            .to_string();
            (payload.clone(), hash_payload(&payload))
        }
    }
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

fn resolve_repo_root() -> PathBuf {
    // Always anchor to the workspace root (one level above the `rust/` crate).
    // `CARGO_MANIFEST_DIR` points at `.../Kanbus/rust`, so walk up a parent to
    // find the repo root regardless of where the binary is launched from.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")))
}

async fn get_index(
    State(state): State<AppState>,
    AxumPath((_account, _project)): AxumPath<(String, String)>,
) -> Response {
    serve_asset(&state, "index.html")
}

async fn get_index_root(State(state): State<AppState>) -> Response {
    serve_asset(&state, "index.html")
}

async fn get_asset(
    State(state): State<AppState>,
    AxumPath((_account, _project, path)): AxumPath<(String, String, String)>,
) -> Response {
    serve_asset(&state, &path)
}

async fn get_asset_root(
    State(state): State<AppState>,
    AxumPath(path): AxumPath<String>,
) -> Response {
    serve_asset(&state, &path)
}

async fn get_public_asset(
    State(state): State<AppState>,
    AxumPath(path): AxumPath<String>,
) -> Response {
    serve_asset(&state, &format!("assets/{path}"))
}

fn serve_asset(state: &AppState, asset_path: &str) -> Response {
    // If CONSOLE_ASSETS_ROOT was explicitly set, use filesystem only
    if state.assets_root_explicit {
        return serve_asset_from_filesystem(state, asset_path);
    }

    // Try embedded assets first (if feature enabled and no explicit override)
    #[cfg(feature = "embed-assets")]
    {
        if let Some(embedded_file) = EmbeddedAssets::get(asset_path) {
            let content_type = mime_guess::from_path(asset_path)
                .first_or_octet_stream()
                .to_string();
            return Response::builder()
                .status(StatusCode::OK)
                .header(CONTENT_TYPE, content_type)
                .body(Body::from(embedded_file.data.into_owned()))
                .unwrap_or_else(|_| {
                    error_response(
                        "embedded asset response failed",
                        StatusCode::INTERNAL_SERVER_ERROR,
                    )
                });
        }
    }

    // Fallback to filesystem (development or asset not found in embedded)
    serve_asset_from_filesystem(state, asset_path)
}

fn serve_asset_from_filesystem(state: &AppState, asset_path: &str) -> Response {
    let asset_root = match state.assets_root.canonicalize() {
        Ok(root) => root,
        Err(error) => {
            let help_message = if !state.assets_root_explicit {
                format!(
                    "Console assets directory not found at {:?}. \
                    \n\nThis binary was built without embedded assets. To fix this:\
                    \n1. Build the UI: cd apps/console && npm install && npm run build\
                    \n2. Set CONSOLE_ASSETS_ROOT to the dist directory\
                    \n3. Or install the console binary with embedded assets:\
                    \n   cargo install kanbus --bin kbsc --features embed-assets\
                    \n\nOriginal error: {}",
                    state.assets_root, error
                )
            } else {
                format!(
                    "Console assets directory not found at {:?} (set via CONSOLE_ASSETS_ROOT). \
                    Original error: {}",
                    state.assets_root, error
                )
            };
            return error_response(help_message, StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let requested = asset_root.join(asset_path);
    let canonical = match requested.canonicalize() {
        Ok(path) => path,
        Err(_) => {
            return error_response("asset not found", StatusCode::NOT_FOUND);
        }
    };
    if !canonical.starts_with(&asset_root) || canonical.is_dir() {
        return error_response("asset not found", StatusCode::NOT_FOUND);
    }
    let bytes = match std::fs::read(&canonical) {
        Ok(bytes) => bytes,
        Err(error) => {
            return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let content_type = mime_guess::from_path(StdPath::new(asset_path))
        .first_or_octet_stream()
        .to_string();
    Response::builder()
        .status(StatusCode::OK)
        .header(CONTENT_TYPE, content_type)
        .body(Body::from(bytes))
        .unwrap_or_else(|_| {
            error_response("asset response failed", StatusCode::INTERNAL_SERVER_ERROR)
        })
}
