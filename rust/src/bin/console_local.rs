//! Local HTTP server for the console backend.

use std::collections::hash_map::DefaultHasher;
use std::convert::Infallible;
use std::hash::{Hash, Hasher};
use std::io::{self, IsTerminal, Write};
use std::net::{IpAddr, SocketAddr};
use std::path::Path as StdPath;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;
use std::sync::Mutex as StdMutex;
use std::time::Duration;

use axum::body::Body;
use axum::body::Bytes;
use axum::extract::{Path as AxumPath, Query, State};
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
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use tokio::sync::broadcast;
use tokio::sync::Mutex;
use tokio_stream::wrappers::BroadcastStream;
use tokio_stream::wrappers::IntervalStream;
use tower_http::cors::{Any, CorsLayer};

use kanbus::console_backend::{find_issue_matches, FileStore};
use kanbus::console_ui_state::{load_state, save_state, ConsoleUiState};
use kanbus::daemon_paths::get_console_state_path;
use kanbus::event_history::{load_issue_events, EventRecord};
use kanbus::notification_events::{NotificationEvent, UiControlAction};

#[cfg(feature = "embed-assets")]
use rust_embed::RustEmbed;

#[cfg(feature = "embed-assets")]
#[derive(RustEmbed)]
#[folder = "embedded_assets/console"]
struct EmbeddedAssets;

#[derive(Clone)]
struct AppState {
    base_root: PathBuf,
    assets_root: PathBuf,
    multi_tenant: bool,
    assets_root_explicit: bool,
    telemetry_tx: broadcast::Sender<String>,
    telemetry_log: Option<Arc<StdMutex<std::fs::File>>>,
    notification_tx: broadcast::Sender<NotificationEvent>,
    /// Cache of the last URL route pushed to clients, for CLI query commands.
    ui_state: Arc<tokio::sync::RwLock<ConsoleUiState>>,
    /// Path to the persisted console state JSON file.
    state_file_path: PathBuf,
}

#[derive(Debug, Deserialize)]
struct IssueEventsQuery {
    limit: Option<usize>,
    before: Option<String>,
}

#[derive(Debug, Serialize)]
struct IssueEventsResponse {
    issue_id: String,
    events: Vec<EventRecord>,
    next_before: Option<String>,
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
    let (bind_ip, bind_host) = resolve_bind_host(std::env::var("CONSOLE_HOST").ok());

    // Try to load console_port from project config
    let config_port = match FileStore::new(&data_root).load_config() {
        Ok(cfg) => {
            if let Some(port) = cfg.console_port {
                eprintln!("Loaded console_port from config: {}", port);
                Some(port)
            } else {
                eprintln!("No console_port specified in config, using default");
                None
            }
        }
        Err(e) => {
            eprintln!(
                "Warning: Failed to load project config: {}. Using default port.",
                e
            );
            None
        }
    };

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
        .or_else(|| {
            // Try Kanbus repo location as fallback
            let kanbus_dist = repo_root.join("apps/console/dist");
            if kanbus_dist.exists() {
                Some(kanbus_dist)
            } else {
                None
            }
        })
        .unwrap_or_else(|| repo_root.join("apps/console/dist"));

    let multi_tenant = std::env::var("CONSOLE_TENANT_MODE")
        .map(|value| value == "multi")
        .unwrap_or(false);

    let (telemetry_tx, _) = broadcast::channel(256);
    let (notification_tx, _) = broadcast::channel::<NotificationEvent>(256);
    let telemetry_log = open_telemetry_log(&repo_root);

    // Load persisted console UI state (or start with empty state)
    let state_file_path = get_console_state_path(&data_root).unwrap_or_else(|_| {
        data_root
            .join(".kanbus")
            .join(".cache")
            .join("console_state.json")
    });
    let initial_ui_state = load_state(&state_file_path).unwrap_or_default();
    eprintln!("Console UI state loaded from {}", state_file_path.display());

    let state = AppState {
        base_root: data_root,
        assets_root: assets_root.clone(),
        multi_tenant,
        assets_root_explicit,
        telemetry_tx,
        telemetry_log,
        notification_tx,
        ui_state: Arc::new(tokio::sync::RwLock::new(initial_ui_state)),
        state_file_path,
    };
    let _assets_root = state.assets_root.clone();

    let app = Router::new()
        .route("/assets/*path", get(get_public_asset))
        .route("/api/config", get(get_config_root))
        .route("/api/issues", get(get_issues_root))
        .route("/api/issues/:id", get(get_issue_root))
        .route("/api/issues/:id/events", get(get_issue_events_root))
        .route("/api/events", get(get_events_root))
        .route("/api/events/realtime", get(get_realtime_events_root))
        .route("/api/notifications", post(post_notification_root))
        .route("/api/ui-state", get(get_ui_state_root))
        .route("/api/render/d2", post(post_render_d2))
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
        .route(
            "/:account/:project/api/issues/:id/events",
            get(get_issue_events),
        )
        .route("/:account/:project/api/events", get(get_events))
        .route(
            "/:account/:project/api/events/realtime",
            get(get_realtime_events),
        )
        .route(
            "/:account/:project/api/notifications",
            post(post_notification),
        )
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
        .fallback(get(get_asset_root));

    // Start Unix socket listener for notifications before moving state
    #[cfg(unix)]
    {
        let socket_path = get_notification_socket_path(&state.base_root);
        let socket_state = state.clone();
        tokio::spawn(async move {
            if let Err(e) = listen_on_socket(socket_path, socket_state).await {
                eprintln!("Unix socket listener error: {}", e);
            }
        });
    }
    #[cfg(not(unix))]
    {
        eprintln!(
            "Unix domain sockets are unavailable on this platform; disabling console notifications."
        );
    }

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any)
        .allow_private_network(true);

    let app = app.with_state(state).layer(cors);
    let (listener, port) = acquire_listener(bind_ip, desired_port).await;

    #[cfg(feature = "embed-assets")]
    println!("Console backend listening on http://{bind_host}:{port} (embedded assets)");
    #[cfg(not(feature = "embed-assets"))]
    {
        // Verify assets directory exists before starting server
        if !assets_root.exists() {
            eprintln!("\nNote: Console UI assets not found at {:?}", assets_root);
            eprintln!("The API will work, but the web UI won't load.");
            eprintln!("\nTo use the web UI:");
            eprintln!("Install the official release with embedded assets: cargo install kanbus --bin kbsc\n");
        }
        println!(
            "Console backend listening on http://{bind_host}:{port} (filesystem assets at {:?})",
            assets_root
        );
    }

    axum::serve(listener, app.into_make_service())
        .await
        .expect("server failure");
}

fn resolve_bind_host(value: Option<String>) -> (IpAddr, String) {
    let fallback = "127.0.0.1";
    let raw = value.unwrap_or_else(|| fallback.to_string());
    let candidate = raw.trim();
    if candidate.is_empty() {
        return (
            fallback.parse().expect("valid fallback ip"),
            fallback.to_string(),
        );
    }
    if candidate.eq_ignore_ascii_case("localhost") {
        return (
            fallback.parse().expect("valid localhost ip"),
            fallback.to_string(),
        );
    }
    match candidate.parse::<IpAddr>() {
        Ok(ip) => (ip, candidate.to_string()),
        Err(_) => {
            eprintln!(
                "Warning: CONSOLE_HOST '{}' is invalid; defaulting to 127.0.0.1",
                candidate
            );
            (
                fallback.parse().expect("valid fallback ip"),
                fallback.to_string(),
            )
        }
    }
}

async fn acquire_listener(bind_ip: IpAddr, desired_port: u16) -> (tokio::net::TcpListener, u16) {
    let initial_addr = SocketAddr::from((bind_ip, desired_port));
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
            let fallback_addr = SocketAddr::from((bind_ip, fallback_port));
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

async fn get_issue_events_root(
    State(state): State<AppState>,
    AxumPath(id): AxumPath<String>,
    Query(query): Query<IssueEventsQuery>,
) -> Response {
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
    let issue_id = matches[0].identifier.clone();
    let project_dir = store.root().join(&snapshot.config.project_directory);
    let limit = query.limit.unwrap_or(50).clamp(1, 200);
    let (events, next_before) =
        match load_issue_events(&project_dir, &issue_id, query.before.as_deref(), limit) {
            Ok(result) => result,
            Err(error) => {
                return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
            }
        };
    Json(IssueEventsResponse {
        issue_id,
        events,
        next_before,
    })
    .into_response()
}

async fn get_issue_events(
    State(state): State<AppState>,
    AxumPath((account, project, id)): AxumPath<(String, String, String)>,
    Query(query): Query<IssueEventsQuery>,
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
    let issue_id = matches[0].identifier.clone();
    let project_dir = store.root().join(&snapshot.config.project_directory);
    let limit = query.limit.unwrap_or(50).clamp(1, 200);
    let (events, next_before) =
        match load_issue_events(&project_dir, &issue_id, query.before.as_deref(), limit) {
            Ok(result) => result,
            Err(error) => {
                return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
            }
        };
    Json(IssueEventsResponse {
        issue_id,
        events,
        next_before,
    })
    .into_response()
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

async fn post_console_telemetry_root(State(state): State<AppState>, body: Bytes) -> StatusCode {
    let message = build_telemetry_payload(parse_json_body(&body), None);
    let _ = state.telemetry_tx.send(message);
    write_telemetry_log(&state, &body);
    StatusCode::NO_CONTENT
}

async fn post_console_telemetry(
    State(state): State<AppState>,
    AxumPath((account, project)): AxumPath<(String, String)>,
    body: Bytes,
) -> StatusCode {
    let message = build_telemetry_payload(parse_json_body(&body), Some((account, project)));
    let _ = state.telemetry_tx.send(message);
    write_telemetry_log(&state, &body);
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

// Notification handlers for real-time issue updates

async fn post_notification_root(
    State(state): State<AppState>,
    Json(event): Json<NotificationEvent>,
) -> StatusCode {
    // Update cached UI state based on the event
    update_ui_state_from_event(&state, &event).await;
    // Broadcast the notification to all SSE subscribers
    let _ = state.notification_tx.send(event);
    StatusCode::OK
}

async fn get_ui_state_root(State(state): State<AppState>) -> axum::Json<ConsoleUiState> {
    let ui_state = state.ui_state.read().await;
    axum::Json(ui_state.clone())
}

/// Update the cached UI state when a relevant notification is received,
/// then persist to disk.
async fn update_ui_state_from_event(state: &AppState, event: &NotificationEvent) {
    let mut changed = false;
    {
        let mut ui_state = state.ui_state.write().await;
        match event {
            NotificationEvent::IssueFocused {
                issue_id,
                comment_id,
                ..
            } => {
                ui_state.focused_issue_id = Some(issue_id.clone());
                ui_state.focused_comment_id = comment_id.clone();
                changed = true;
            }
            NotificationEvent::UiControl { action } => match action {
                UiControlAction::ClearFocus => {
                    ui_state.focused_issue_id = None;
                    ui_state.focused_comment_id = None;
                    changed = true;
                }
                UiControlAction::SetViewMode { mode } => {
                    ui_state.view_mode = Some(mode.clone());
                    changed = true;
                }
                UiControlAction::SetSearch { query } => {
                    ui_state.search_query = if query.is_empty() {
                        None
                    } else {
                        Some(query.clone())
                    };
                    changed = true;
                }
                _ => {}
            },
            _ => {}
        }
    }
    if changed {
        let ui_state = state.ui_state.read().await;
        if let Err(e) = save_state(&state.state_file_path, &ui_state) {
            eprintln!("Warning: failed to persist console UI state: {}", e);
        }
    }
}

async fn get_realtime_events_root(
    State(state): State<AppState>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    // Replay last-known UI state to the new subscriber, if any state has been set
    let replay_events: Vec<Result<Event, Infallible>> = {
        let ui_state = state.ui_state.read().await;
        let mut events = Vec::new();
        if let Some(ref issue_id) = ui_state.focused_issue_id {
            let notification = NotificationEvent::IssueFocused {
                issue_id: issue_id.clone(),
                user: None,
                comment_id: ui_state.focused_comment_id.clone(),
            };
            if let Ok(data) = serde_json::to_string(&notification) {
                events.push(Ok(Event::default().data(data)));
            }
        } else if ui_state.view_mode.is_some() || ui_state.search_query.is_some() {
            // Replay view mode if set
            if let Some(ref mode) = ui_state.view_mode {
                let notification = NotificationEvent::UiControl {
                    action: UiControlAction::SetViewMode { mode: mode.clone() },
                };
                if let Ok(data) = serde_json::to_string(&notification) {
                    events.push(Ok(Event::default().data(data)));
                }
            }
            // Replay search query if set
            if let Some(ref query) = ui_state.search_query {
                let notification = NotificationEvent::UiControl {
                    action: UiControlAction::SetSearch {
                        query: query.clone(),
                    },
                };
                if let Ok(data) = serde_json::to_string(&notification) {
                    events.push(Ok(Event::default().data(data)));
                }
            }
        }
        events
    };

    let receiver = state.notification_tx.subscribe();
    let replay_stream = stream::iter(replay_events);
    let live_stream = BroadcastStream::new(receiver).filter_map(|event| async move {
        match event {
            Ok(notification) => {
                // Serialize the notification event to JSON
                match serde_json::to_string(&notification) {
                    Ok(data) => Some(Ok(Event::default().data(data))),
                    Err(_) => None,
                }
            }
            Err(_) => None,
        }
    });
    let combined: BoxStream<Result<Event, Infallible>> = Box::pin(replay_stream.chain(live_stream));
    Sse::new(combined).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text(": keep-alive"),
    )
}

async fn post_notification(
    State(state): State<AppState>,
    AxumPath((_account, _project)): AxumPath<(String, String)>,
    Json(event): Json<NotificationEvent>,
) -> StatusCode {
    post_notification_root(State(state), Json(event)).await
}

async fn get_realtime_events(
    State(state): State<AppState>,
    AxumPath((_account, _project)): AxumPath<(String, String)>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    get_realtime_events_root(State(state)).await
}

async fn post_render_d2(body: Bytes) -> Response {
    // Check if d2 is installed
    let d2_available = Command::new("which")
        .arg("d2")
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false);

    if !d2_available {
        return error_response(
            "D2 CLI not installed. Install from https://d2lang.com",
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }

    // Parse request body to get D2 source
    let request: JsonValue = match serde_json::from_slice(&body) {
        Ok(json) => json,
        Err(_) => return error_response("Invalid JSON", StatusCode::BAD_REQUEST),
    };

    let source = match request.get("source").and_then(|s| s.as_str()) {
        Some(s) => s,
        None => return error_response("Missing 'source' field", StatusCode::BAD_REQUEST),
    };

    // Get theme from request, default to light theme
    let theme = request
        .get("theme")
        .and_then(|t| t.as_str())
        .unwrap_or("light");

    eprintln!("D2 render request: theme={}", theme);

    // Prepend neutral gray theme overrides to D2 source
    let theme_overrides = if theme == "dark" {
        "vars: {
  d2-config: {
    dark-theme-overrides: {
      N1: \"#ffffff\"
      N2: \"#cccccc\"
      N3: \"#999999\"
      N4: \"#666666\"
      N5: \"#555555\"
      N6: \"#333333\"
      N7: \"#1a1a1a\"
      B1: \"#ffffff\"
      B2: \"#dddddd\"
      B3: \"#bbbbbb\"
      B4: \"#888888\"
      B5: \"#666666\"
      B6: \"#444444\"
      AA2: \"#cccccc\"
      AA4: \"#999999\"
      AA5: \"#777777\"
      AB4: \"#999999\"
      AB5: \"#777777\"
    }
  }
}

"
    } else {
        ""
    };

    let full_source = format!("{}{}", theme_overrides, source);

    // Create temp files for input and output with unique names
    let temp_dir = std::env::temp_dir();
    let unique_id = format!(
        "{}-{}",
        std::process::id(),
        chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0)
    );
    let input_path = temp_dir.join(format!("kanbus_d2_{}.d2", unique_id));
    let output_path = temp_dir.join(format!("kanbus_d2_{}.svg", unique_id));

    // Write D2 source to temp file
    if let Err(e) = std::fs::write(&input_path, &full_source) {
        return error_response(
            format!("Failed to write temp file: {}", e),
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    }

    // Run d2 to render SVG with neutral theme
    let mut cmd = Command::new("d2");

    if theme == "dark" {
        // Dark mode: Use theme 0 with custom neutral gray palette overrides
        cmd.arg("--dark-theme").arg("0");
    } else {
        // Light mode: Use theme 1 (Neutral Grey) - works perfectly as-is
        cmd.arg("--theme").arg("1");
    }

    cmd.arg(input_path.to_str().unwrap_or(""));
    cmd.arg(output_path.to_str().unwrap_or(""));
    let output = cmd.output();

    // Clean up input file
    let _ = std::fs::remove_file(&input_path);

    match output {
        Ok(result) if result.status.success() => {
            // Read the SVG output
            match std::fs::read_to_string(&output_path) {
                Ok(svg) => {
                    let _ = std::fs::remove_file(&output_path);
                    let response_json = serde_json::json!({ "svg": svg });
                    Json(response_json).into_response()
                }
                Err(e) => {
                    let _ = std::fs::remove_file(&output_path);
                    error_response(
                        format!("Failed to read SVG output: {}", e),
                        StatusCode::INTERNAL_SERVER_ERROR,
                    )
                }
            }
        }
        Ok(result) => {
            let _ = std::fs::remove_file(&output_path);
            let stderr = String::from_utf8_lossy(&result.stderr);
            error_response(
                format!("D2 rendering failed: {}", stderr),
                StatusCode::BAD_REQUEST,
            )
        }
        Err(e) => {
            let _ = std::fs::remove_file(&output_path);
            error_response(
                format!("Failed to execute d2: {}", e),
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
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

fn open_telemetry_log(_repo_root: &StdPath) -> Option<Arc<StdMutex<std::fs::File>>> {
    let log_path = match std::env::var("CONSOLE_LOG_PATH") {
        Ok(path) => PathBuf::from(path),
        Err(_) => return None,
    };
    if let Some(parent) = log_path.parent() {
        if let Err(error) = std::fs::create_dir_all(parent) {
            eprintln!("[console] failed to create log dir: {error}");
            return None;
        }
    }
    match std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
    {
        Ok(file) => {
            let wrapped = Arc::new(StdMutex::new(file));
            if let Err(error) = write_log_line(
                &wrapped,
                &format!(
                    "{{\"type\":\"startup\",\"at\":\"{}\",\"logPath\":\"{}\"}}",
                    chrono::Utc::now().to_rfc3339(),
                    log_path.display()
                ),
            ) {
                eprintln!("[console] failed to write startup log: {error}");
            }
            Some(wrapped)
        }
        Err(error) => {
            eprintln!("[console] failed to open log file: {error}");
            None
        }
    }
}

fn write_telemetry_log(state: &AppState, body: &Bytes) {
    let Some(handle) = &state.telemetry_log else {
        return;
    };
    let line = String::from_utf8_lossy(body);
    let sanitized = line.trim();
    let payload = if sanitized.is_empty() {
        format!(
            "{{\"type\":\"telemetry\",\"at\":\"{}\",\"payload\":null}}",
            chrono::Utc::now().to_rfc3339()
        )
    } else {
        format!(
            "{{\"type\":\"telemetry\",\"at\":\"{}\",\"payload\":{}}}",
            chrono::Utc::now().to_rfc3339(),
            sanitized
        )
    };
    if let Err(error) = write_log_line(handle, &payload) {
        eprintln!("[console] failed to write telemetry log: {error}");
    }
}

fn write_log_line(handle: &Arc<StdMutex<std::fs::File>>, line: &str) -> io::Result<()> {
    let mut guard = handle
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    writeln!(guard, "{line}")?;
    guard.flush()
}

fn parse_json_body(body: &Bytes) -> JsonValue {
    if body.is_empty() {
        return JsonValue::Null;
    }
    serde_json::from_slice(body)
        .unwrap_or_else(|_| JsonValue::String(String::from_utf8_lossy(body).to_string()))
}

fn resolve_repo_root() -> PathBuf {
    // Start from current directory and walk up to find .kanbus.yml
    let current = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));

    let mut path = current.as_path();
    loop {
        if path.join(".kanbus.yml").exists() {
            return path.to_path_buf();
        }
        match path.parent() {
            Some(parent) => path = parent,
            None => break,
        }
    }

    // No .kanbus.yml found - fail with a helpful error message
    eprintln!("Error: Could not find .kanbus.yml in current directory or any parent directory.");
    eprintln!("Current directory: {}", current.display());
    eprintln!("\nTo initialize a Kanbus project, run: kanbus init");
    std::process::exit(1);
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

/// Get the Unix domain socket path for notifications based on project root.
///
/// Uses the same hash-based approach as the CLI publisher to ensure they connect to the same socket.
fn get_notification_socket_path(root: &StdPath) -> PathBuf {
    use sha2::{Digest, Sha256};

    let canonical = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let mut hasher = Sha256::new();
    hasher.update(canonical.to_string_lossy().as_bytes());
    let hash = format!("{:x}", hasher.finalize());
    let socket_name = format!("kanbus-{}.sock", &hash[..12]);

    std::env::temp_dir().join(socket_name)
}

/// Listen on Unix domain socket for notification events from CLI commands.
#[cfg(unix)]
async fn listen_on_socket(socket_path: PathBuf, state: AppState) -> io::Result<()> {
    use tokio::io::{AsyncBufReadExt, BufReader};
    use tokio::net::UnixListener;

    // Remove stale socket file if it exists
    if socket_path.exists() {
        let _ = std::fs::remove_file(&socket_path);
    }

    let listener = UnixListener::bind(&socket_path)?;
    println!("Notification socket listening at {}", socket_path.display());

    loop {
        match listener.accept().await {
            Ok((stream, _addr)) => {
                let conn_state = state.clone();
                tokio::spawn(async move {
                    let mut reader = BufReader::new(stream);
                    let mut line = String::new();

                    while let Ok(n) = reader.read_line(&mut line).await {
                        if n == 0 {
                            break; // EOF
                        }

                        // Try to parse the JSON event
                        match serde_json::from_str::<NotificationEvent>(&line) {
                            Ok(event) => {
                                eprintln!(
                                    "Socket received notification: {:?}",
                                    event.description()
                                );
                                // Update cached UI state before broadcasting
                                update_ui_state_from_event(&conn_state, &event).await;
                                match conn_state.notification_tx.send(event) {
                                    Ok(receiver_count) => {
                                        eprintln!("Broadcast sent to {} receivers", receiver_count);
                                    }
                                    Err(e) => {
                                        eprintln!("Failed to broadcast notification: {:?}", e);
                                    }
                                }
                            }
                            Err(e) => {
                                eprintln!("Failed to parse notification event: {}", e);
                            }
                        }

                        line.clear();
                    }
                });
            }
            Err(e) => {
                eprintln!("Failed to accept socket connection: {}", e);
            }
        }
    }
}

#[cfg(not(unix))]
async fn listen_on_socket(_socket_path: PathBuf, _state: AppState) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "unix domain sockets unsupported on this platform",
    ))
}
