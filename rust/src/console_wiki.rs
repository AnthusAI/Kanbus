//! Console wiki service and API models.
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::console_backend::FileStore;
use crate::error::KanbusError;
use crate::wiki::{render_wiki_page, WikiRenderRequest};

/// Response for listing wiki pages.
#[derive(Debug, Clone, Serialize)]
pub struct WikiPagesResponse {
    pub pages: Vec<String>,
}

/// Response for fetching a wiki page.
#[derive(Debug, Clone, Serialize)]
pub struct WikiPageResponse {
    pub path: String,
    pub content: String,
    pub exists: bool,
}

/// Request for creating a wiki page.
#[derive(Debug, Clone, Deserialize)]
pub struct WikiCreateRequest {
    pub path: String,
    #[serde(default)]
    pub content: Option<String>,
    #[serde(default)]
    pub overwrite: Option<bool>,
}

/// Response for creating a wiki page.
#[derive(Debug, Clone, Serialize)]
pub struct WikiCreateResponse {
    pub path: String,
    pub created: bool,
}

/// Request for updating a wiki page.
#[derive(Debug, Clone, Deserialize)]
pub struct WikiUpdateRequest {
    pub path: String,
    pub content: String,
}

/// Response for updating a wiki page.
#[derive(Debug, Clone, Serialize)]
pub struct WikiUpdateResponse {
    pub path: String,
    pub updated: bool,
}

/// Request for renaming or moving a wiki page.
#[derive(Debug, Clone, Deserialize)]
pub struct WikiRenameRequest {
    pub from_path: String,
    pub to_path: String,
    #[serde(default)]
    pub overwrite: Option<bool>,
}

/// Response for renaming or moving a wiki page.
#[derive(Debug, Clone, Serialize)]
pub struct WikiRenameResponse {
    pub from_path: String,
    pub to_path: String,
    pub renamed: bool,
}

/// Response for deleting a wiki page.
#[derive(Debug, Clone, Serialize)]
pub struct WikiDeleteResponse {
    pub path: String,
    pub deleted: bool,
}

/// Request for rendering a wiki page.
#[derive(Debug, Clone, Deserialize)]
pub struct WikiRenderRequestPayload {
    pub path: String,
    #[serde(default)]
    pub content: Option<String>,
}

/// Response for rendering a wiki page.
#[derive(Debug, Clone, Serialize)]
pub struct WikiRenderResponse {
    pub path: String,
    pub rendered_markdown: String,
}

/// Service error types for wiki operations.
#[derive(Debug)]
pub enum WikiServiceError {
    InvalidPath(String),
    NotFound(String),
    Conflict(String),
    Io(String),
    Render(String),
}

/// Normalize and validate a wiki path.
fn normalize_path(path: &str) -> Result<String, WikiServiceError> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err(WikiServiceError::InvalidPath(
            "invalid wiki path".to_string(),
        ));
    }
    if trimmed.starts_with('/') || trimmed.contains(':') {
        return Err(WikiServiceError::InvalidPath(
            "invalid wiki path".to_string(),
        ));
    }

    let replaced = trimmed.replace('\\', "/");
    let mut parts = Vec::new();
    for part in replaced.split('/') {
        if part.is_empty() || part == "." {
            return Err(WikiServiceError::InvalidPath(
                "invalid wiki path".to_string(),
            ));
        }
        if part == ".." {
            return Err(WikiServiceError::InvalidPath(
                "invalid wiki path".to_string(),
            ));
        }
        parts.push(part);
    }
    let canonical = parts.join("/");
    if !canonical.ends_with(".md") {
        return Err(WikiServiceError::InvalidPath(
            "wiki path must end with .md".to_string(),
        ));
    }
    Ok(canonical)
}

fn wiki_root(store: &FileStore) -> Result<PathBuf, KanbusError> {
    let config = store.load_config()?;
    Ok(store.root().join(&config.project_directory).join("wiki"))
}

fn absolute_page_path(store: &FileStore, path: &str) -> Result<PathBuf, KanbusError> {
    let normalized = normalize_path(path).map_err(|error| match error {
        WikiServiceError::InvalidPath(message) => KanbusError::IssueOperation(message),
        _ => KanbusError::IssueOperation("invalid wiki path".to_string()),
    })?;
    let root = wiki_root(store)?;
    Ok(root.join(normalized))
}

/// List all markdown pages under wiki root.
pub fn list_pages(store: &FileStore) -> Result<WikiPagesResponse, WikiServiceError> {
    let root = wiki_root(store).map_err(to_service_error)?;
    if !root.exists() {
        return Err(WikiServiceError::NotFound(
            "wiki page not found".to_string(),
        ));
    }
    let mut pages = Vec::new();
    collect_markdown(&root, &root, &mut pages)?;
    pages.sort();
    Ok(WikiPagesResponse { pages })
}

fn collect_markdown(
    root: &Path,
    current: &Path,
    pages: &mut Vec<String>,
) -> Result<(), WikiServiceError> {
    for entry in fs::read_dir(current).map_err(|error| WikiServiceError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| WikiServiceError::Io(error.to_string()))?;
        let path = entry.path();
        if path.is_dir() {
            collect_markdown(root, &path, pages)?;
            continue;
        }
        if path.extension().and_then(|ext| ext.to_str()) != Some("md") {
            continue;
        }
        let relative = path
            .strip_prefix(root)
            .map_err(|error| WikiServiceError::Io(error.to_string()))?;
        let normalized = relative
            .to_str()
            .ok_or_else(|| WikiServiceError::Io("invalid unicode path".to_string()))?
            .replace('\\', "/");
        pages.push(normalized);
    }
    Ok(())
}

/// Fetch page content.
pub fn get_page(store: &FileStore, path: &str) -> Result<WikiPageResponse, WikiServiceError> {
    let absolute = absolute_page_path(store, path).map_err(to_service_error)?;
    if !absolute.exists() {
        return Err(WikiServiceError::NotFound(
            "wiki page not found".to_string(),
        ));
    }
    let content =
        fs::read_to_string(&absolute).map_err(|error| WikiServiceError::Io(error.to_string()))?;
    Ok(WikiPageResponse {
        path: normalize_path(path)?,
        content,
        exists: true,
    })
}

/// Create a new page.
pub fn create_page(
    store: &FileStore,
    request: &WikiCreateRequest,
) -> Result<WikiCreateResponse, WikiServiceError> {
    let path = normalize_path(&request.path)?;
    let absolute = absolute_page_path(store, &path).map_err(to_service_error)?;
    let overwrite = request.overwrite.unwrap_or(false);
    if absolute.exists() && !overwrite {
        return Err(WikiServiceError::Conflict(
            "wiki page already exists".to_string(),
        ));
    }
    let content = request.content.clone().unwrap_or_default();
    write_atomic(&absolute, &content)?;
    Ok(WikiCreateResponse {
        path,
        created: true,
    })
}

/// Update an existing page.
pub fn update_page(
    store: &FileStore,
    request: &WikiUpdateRequest,
) -> Result<WikiUpdateResponse, WikiServiceError> {
    let path = normalize_path(&request.path)?;
    let absolute = absolute_page_path(store, &path).map_err(to_service_error)?;
    if !absolute.exists() {
        return Err(WikiServiceError::NotFound(
            "wiki page not found".to_string(),
        ));
    }
    write_atomic(&absolute, &request.content)?;
    Ok(WikiUpdateResponse {
        path,
        updated: true,
    })
}

/// Rename or move a page.
pub fn rename_page(
    store: &FileStore,
    request: &WikiRenameRequest,
) -> Result<WikiRenameResponse, WikiServiceError> {
    let from_path = normalize_path(&request.from_path)?;
    let to_path = normalize_path(&request.to_path)?;
    let from_absolute = absolute_page_path(store, &from_path).map_err(to_service_error)?;
    let to_absolute = absolute_page_path(store, &to_path).map_err(to_service_error)?;
    if !from_absolute.exists() {
        return Err(WikiServiceError::NotFound(
            "wiki page not found".to_string(),
        ));
    }
    let overwrite = request.overwrite.unwrap_or(false);
    if to_absolute.exists() && !overwrite {
        return Err(WikiServiceError::Conflict(
            "wiki page already exists".to_string(),
        ));
    }
    if let Some(parent) = to_absolute.parent() {
        fs::create_dir_all(parent).map_err(|error| WikiServiceError::Io(error.to_string()))?;
    }
    fs::rename(&from_absolute, &to_absolute)
        .map_err(|error| WikiServiceError::Io(error.to_string()))?;
    Ok(WikiRenameResponse {
        from_path,
        to_path,
        renamed: true,
    })
}

/// Delete a page.
pub fn delete_page(store: &FileStore, path: &str) -> Result<WikiDeleteResponse, WikiServiceError> {
    let normalized = normalize_path(path)?;
    let absolute = absolute_page_path(store, &normalized).map_err(to_service_error)?;
    if !absolute.exists() {
        return Err(WikiServiceError::NotFound(
            "wiki page not found".to_string(),
        ));
    }
    fs::remove_file(&absolute).map_err(|error| WikiServiceError::Io(error.to_string()))?;
    Ok(WikiDeleteResponse {
        path: normalized,
        deleted: true,
    })
}

/// Render a page, using draft content when provided.
pub fn render_page(
    store: &FileStore,
    request: &WikiRenderRequestPayload,
) -> Result<WikiRenderResponse, WikiServiceError> {
    let normalized = normalize_path(&request.path)?;
    let absolute = absolute_page_path(store, &normalized).map_err(to_service_error)?;
    let root = store.root().to_path_buf();
    let relative_for_render =
        relative_to_root_for_render(store, &normalized).map_err(to_service_error)?;
    if let Some(content) = &request.content {
        if let Some(parent) = absolute.parent() {
            fs::create_dir_all(parent).map_err(|error| WikiServiceError::Io(error.to_string()))?;
        }
        let temp_path = temp_render_path(&absolute);
        write_atomic(&temp_path, content)?;
        let result = render_wiki_page(&WikiRenderRequest {
            root,
            page_path: relative_for_render.with_file_name(
                temp_path
                    .file_name()
                    .unwrap_or_else(|| std::ffi::OsStr::new("temp.md")),
            ),
        })
        .map_err(|error| WikiServiceError::Render(error.to_string()));
        let _ = fs::remove_file(&temp_path);
        return result.map(|rendered| WikiRenderResponse {
            path: normalized,
            rendered_markdown: rendered,
        });
    }

    if !absolute.exists() {
        return Err(WikiServiceError::NotFound(
            "wiki page not found".to_string(),
        ));
    }

    let rendered = render_wiki_page(&WikiRenderRequest {
        root,
        page_path: relative_for_render,
    })
    .map_err(|error| WikiServiceError::Render(error.to_string()))?;
    Ok(WikiRenderResponse {
        path: normalized,
        rendered_markdown: rendered,
    })
}

fn write_atomic(target: &Path, content: &str) -> Result<(), WikiServiceError> {
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|error| WikiServiceError::Io(error.to_string()))?;
    }
    let temp_path = temp_render_path(target);
    {
        let mut file = fs::File::create(&temp_path)
            .map_err(|error| WikiServiceError::Io(error.to_string()))?;
        file.write_all(content.as_bytes())
            .map_err(|error| WikiServiceError::Io(error.to_string()))?;
        file.sync_all()
            .map_err(|error| WikiServiceError::Io(error.to_string()))?;
    }
    fs::rename(&temp_path, target).map_err(|error| WikiServiceError::Io(error.to_string()))?;
    Ok(())
}

fn temp_render_path(target: &Path) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let file_name = format!(
        "{}.tmp.{}.md",
        target
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("temp"),
        nanos
    );
    target
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(file_name)
}

fn relative_to_root_for_render(
    store: &FileStore,
    normalized: &str,
) -> Result<PathBuf, KanbusError> {
    let config = store.load_config()?;
    Ok(PathBuf::from(&config.project_directory)
        .join("wiki")
        .join(normalized))
}

fn to_service_error(error: KanbusError) -> WikiServiceError {
    match error {
        KanbusError::Io(message) => WikiServiceError::Io(message),
        KanbusError::IssueOperation(message) => WikiServiceError::InvalidPath(message),
        other => WikiServiceError::Io(other.to_string()),
    }
}
