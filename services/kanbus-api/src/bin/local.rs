//! Loopback-only development transport for the generic Kanbus API.

use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{Request, StatusCode},
    response::IntoResponse,
    routing::any,
    Json, Router,
};
use kanbus_api::{authenticate_local, Api, ApiRequest, BoardLifecycle, MAX_CANONICAL_OBJECT_BYTES};
use serde_json::{json, Value};
use std::{collections::BTreeMap, sync::Arc};
use virtuus_store::{FileStore, JournaledStore, MemoryCatalog, Scope};

#[derive(Clone)]
struct Server {
    api: Api,
    secret: String,
    served_board: Scope,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::var("KANBUS_BACKEND")?.as_str() != "file" {
        return Err("Local transport requires KANBUS_BACKEND=file".into());
    }
    let secret = std::env::var("KANBUS_LOCAL_TOKEN")?;
    if secret.len() < 16 {
        return Err("KANBUS_LOCAL_TOKEN must contain at least 16 characters".into());
    }
    let scope = Scope::new(
        std::env::var("KANBUS_TENANT")?,
        std::env::var("KANBUS_PROJECT")?,
    )?;
    let root = std::path::PathBuf::from(std::env::var("KANBUS_ROOT")?);
    let archive_directory = root
        .parent()
        .zip(root.file_name())
        .map(|(parent, name)| parent.join(format!(".{}.archive", name.to_string_lossy())))
        .ok_or("KANBUS_ROOT must name a folder with a parent")?;
    let lifecycle = BoardLifecycle::new(
        BoardLifecycle::retention_days_from_environment()?,
        Arc::new(FileStore::new(archive_directory)?),
    )?;
    let objects = FileStore::for_project(&root, scope.clone())?;
    let objects = Arc::new(objects);
    let store = JournaledStore::new(objects.clone(), Arc::new(MemoryCatalog::default()))
        .with_canonical_read_limit(MAX_CANONICAL_OBJECT_BYTES)?;
    let configuration_object = store
        .get(&scope, ".kanbus.yml")
        .await?
        .ok_or("Project configuration is missing")?;
    let configuration: kanbus::models::ProjectConfiguration =
        serde_yaml::from_slice(&configuration_object.bytes)?;
    store
        .rebuild_catalog(
            &scope,
            &format!("{}/issues/", configuration.project_directory),
        )
        .await?;
    let api = Api::new(store, objects, lifecycle).map_err(|error| error.message)?;
    let port = std::env::var("KANBUS_PORT")
        .unwrap_or_else(|_| "5175".into())
        .parse::<u16>()?;
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).await?;
    eprintln!("Kanbus API listening at http://{}", listener.local_addr()?);
    axum::serve(
        listener,
        Router::new().fallback(any(handle)).with_state(Server {
            api,
            secret,
            served_board: scope,
        }),
    )
    .await?;
    Ok(())
}

async fn handle(State(server): State<Server>, request: Request<Body>) -> impl IntoResponse {
    let principal = match authenticate_local(
        request
            .headers()
            .get("authorization")
            .and_then(|value| value.to_str().ok()),
        &server.secret,
        &server.served_board,
        request
            .headers()
            .get("x-kanbus-actor")
            .map(|value| value.to_str().unwrap_or("")),
    ) {
        Ok(principal) => principal,
        Err(error) => {
            return (
                StatusCode::from_u16(error.status).unwrap(),
                Json(error.body()),
            )
        }
    };
    let (parts, body) = request.into_parts();
    let body = match to_bytes(body, 2 * 1024 * 1024).await {
        Ok(bytes) => bytes,
        Err(_) => {
            return (
                StatusCode::PAYLOAD_TOO_LARGE,
                Json(json!({"error":"body_too_large","message":"Request body exceeds 2 MiB."})),
            )
        }
    };
    let body: Value = if body.is_empty() {
        Value::Null
    } else {
        match serde_json::from_slice(&body) {
            Ok(value) => value,
            Err(_) => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error":"invalid_request","message":"Invalid JSON body."})),
                )
            }
        }
    };
    let query: BTreeMap<_, _> =
        url::form_urlencoded::parse(parts.uri.query().unwrap_or("").as_bytes())
            .into_owned()
            .collect();
    let headers = parts
        .headers
        .iter()
        .filter_map(|(name, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (name.as_str().into(), value.into()))
        })
        .collect();
    match server
        .api
        .handle(ApiRequest {
            method: parts.method.to_string(),
            path: parts.uri.path().into(),
            query,
            headers,
            body,
            principal,
        })
        .await
    {
        Ok(response) => (
            StatusCode::from_u16(response.status).unwrap(),
            Json(response.body),
        ),
        Err(error) => (
            StatusCode::from_u16(error.status).unwrap(),
            Json(error.body()),
        ),
    }
}
