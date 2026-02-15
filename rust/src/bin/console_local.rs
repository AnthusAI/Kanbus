//! Local HTTP server for the console backend.

use std::convert::Infallible;
use std::net::SocketAddr;
use std::path::Path as StdPath;
use std::path::PathBuf;
use std::time::Duration;

use axum::body::Body;
use axum::extract::{Path as AxumPath, State};
use axum::http::header::CONTENT_TYPE;
use axum::http::StatusCode;
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use axum::response::Response;
use axum::routing::get;
use axum::Json;
use axum::Router;
use futures_util::stream;
use futures_util::Stream;
use tokio_stream::wrappers::IntervalStream;
use tokio_stream::StreamExt;

use kanbus::console_backend::{find_issue_matches, FileStore};

#[derive(Clone)]
struct AppState {
    base_root: PathBuf,
    assets_root: PathBuf,
    multi_tenant: bool,
}

#[tokio::main]
async fn main() {
    let port = std::env::var("CONSOLE_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(5174);
    let repo_root = resolve_repo_root();
    let root_override = std::env::var("CONSOLE_ROOT").ok().map(PathBuf::from);
    let data_root = std::env::var("CONSOLE_DATA_ROOT")
        .ok()
        .map(PathBuf::from)
        .or_else(|| root_override.clone())
        .unwrap_or_else(|| repo_root.clone());
    let assets_root = std::env::var("CONSOLE_ASSETS_ROOT")
        .ok()
        .map(PathBuf::from)
        .or_else(|| root_override.clone().map(|root| root.join("console/dist")))
        .unwrap_or_else(|| repo_root.join("console/dist"));

    let multi_tenant = std::env::var("CONSOLE_TENANT_MODE")
        .map(|value| value == "multi")
        .unwrap_or(false);

    let state = AppState {
        base_root: data_root,
        assets_root,
        multi_tenant,
    };

    let app = Router::new()
        .route("/assets/*path", get(get_public_asset))
        .route("/:account/:project/api/config", get(get_config))
        .route("/:account/:project/api/issues", get(get_issues))
        .route("/:account/:project/api/issues/:id", get(get_issue))
        .route("/:account/:project/api/events", get(get_events))
        .route("/:account/:project/", get(get_index))
        .route("/:account/:project/initiatives/", get(get_index))
        .route("/:account/:project/epics/", get(get_index))
        .route("/:account/:project/issues/", get(get_index))
        .route("/:account/:project/issues/:id", get(get_index))
        .route("/:account/:project/issues/:parent/:id", get(get_index))
        .route("/:account/:project/*path", get(get_asset))
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    println!("Console backend listening on http://{addr}");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind failed");
    axum::serve(listener, app.into_make_service())
        .await
        .expect("server failure");
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

async fn get_events(
    State(state): State<AppState>,
    AxumPath((account, project)): AxumPath<(String, String)>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let store = store_for(&state, &account, &project);
    let initial_store = store.clone();
    let initial =
        stream::once(async move { Ok(Event::default().data(snapshot_payload(&initial_store))) });
    let interval = IntervalStream::new(tokio::time::interval(Duration::from_secs(15)));
    let updates_store = store.clone();
    let updates =
        interval.map(move |_| Ok(Event::default().data(snapshot_payload(&updates_store))));
    let stream = initial.chain(updates);

    Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text(": keep-alive"),
    )
}

fn store_for(state: &AppState, account: &str, project: &str) -> FileStore {
    let root = if state.multi_tenant {
        FileStore::resolve_tenant_root(&state.base_root, account, project)
    } else {
        state.base_root.clone()
    };
    FileStore::new(root)
}

fn error_response(message: impl Into<String>, status: StatusCode) -> Response {
    let payload = serde_json::json!({ "error": message.into() });
    (status, Json(payload)).into_response()
}

fn snapshot_payload(store: &FileStore) -> String {
    match store.build_snapshot() {
        Ok(snapshot) => serde_json::to_string(&snapshot).unwrap_or_else(|error| {
            serde_json::json!({
                "error": error.to_string(),
                "updated_at": chrono::Utc::now().to_rfc3339(),
            })
            .to_string()
        }),
        Err(error) => serde_json::json!({
            "error": error.to_string(),
            "updated_at": chrono::Utc::now().to_rfc3339(),
        })
        .to_string(),
    }
}

fn resolve_repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

async fn get_index(
    State(state): State<AppState>,
    AxumPath((_account, _project)): AxumPath<(String, String)>,
) -> Response {
    serve_asset(&state, "index.html")
}

async fn get_asset(
    State(state): State<AppState>,
    AxumPath((_account, _project, path)): AxumPath<(String, String, String)>,
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
    let asset_root = match state.assets_root.canonicalize() {
        Ok(root) => root,
        Err(error) => {
            return error_response(error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
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
