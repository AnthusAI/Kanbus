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
    let wiki_subdir = config.wiki_directory.as_deref().unwrap_or("wiki");
    if wiki_subdir.starts_with("../") {
        let normalized = wiki_subdir
            .replace('\\', "/")
            .trim_start_matches("../")
            .trim_start_matches("..\\")
            .to_string();
        Ok(store.root().join(&normalized))
    } else {
        Ok(store
            .root()
            .join(&config.project_directory)
            .join(wiki_subdir))
    }
}

/// Return the prefix for wiki page paths (e.g. "project/docs" or "wiki").
pub fn wiki_list_prefix(store: &FileStore) -> Result<String, KanbusError> {
    let config = store.load_config()?;
    let wiki_subdir = config.wiki_directory.as_deref().unwrap_or("wiki");
    if wiki_subdir.starts_with("../") {
        let normalized = wiki_subdir
            .replace('\\', "/")
            .trim_start_matches("../")
            .trim_start_matches("..\\")
            .to_string();
        Ok(normalized)
    } else {
        Ok(format!("{}/{}", config.project_directory, wiki_subdir))
    }
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
/// Returns an empty list when the wiki directory does not exist yet (e.g. first use).
pub fn list_pages(store: &FileStore) -> Result<WikiPagesResponse, WikiServiceError> {
    let root = wiki_root(store).map_err(to_service_error)?;
    if !root.exists() {
        return Ok(WikiPagesResponse { pages: vec![] });
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::console_backend::FileStore;

    fn write_config(root: &Path, extra_yaml: &str) {
        let mut contents = String::from("project_key: kanbus\nproject_directory: project\n");
        contents.push_str(extra_yaml);
        std::fs::write(root.join(".kanbus.yml"), contents).expect("write config");
    }

    #[test]
    fn normalize_path_accepts_nested_markdown_and_normalizes_separators() {
        let normalized = normalize_path(r"docs\guide.md").expect("normalized path");
        assert_eq!(normalized, "docs/guide.md");
    }

    #[test]
    fn normalize_path_rejects_invalid_forms() {
        assert!(matches!(
            normalize_path(""),
            Err(WikiServiceError::InvalidPath(_))
        ));
        assert!(matches!(
            normalize_path("/abs/path.md"),
            Err(WikiServiceError::InvalidPath(_))
        ));
        assert!(matches!(
            normalize_path("../escape.md"),
            Err(WikiServiceError::InvalidPath(_))
        ));
        assert!(matches!(
            normalize_path("notes.txt"),
            Err(WikiServiceError::InvalidPath(message)) if message.contains(".md")
        ));
    }

    #[test]
    fn temp_render_path_stays_in_parent_directory_and_uses_tmp_suffix() {
        let target = Path::new("/tmp/wiki/index.md");
        let temp = temp_render_path(target);
        assert_eq!(temp.parent(), target.parent());
        let name = temp
            .file_name()
            .and_then(|value| value.to_str())
            .expect("temp filename");
        assert!(name.starts_with("index.tmp."));
        assert!(name.ends_with(".md"));
    }

    #[test]
    fn write_atomic_creates_parent_and_overwrites_content() {
        let temp = tempfile::tempdir().expect("tempdir");
        let target = temp.path().join("project/wiki/notes.md");
        write_atomic(&target, "first").expect("first write");
        assert_eq!(
            std::fs::read_to_string(&target).expect("read first"),
            "first"
        );
        write_atomic(&target, "second").expect("second write");
        assert_eq!(
            std::fs::read_to_string(&target).expect("read second"),
            "second"
        );
    }

    #[test]
    fn relative_to_root_for_render_uses_project_directory_prefix() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let store = FileStore::new(temp.path());
        let path = relative_to_root_for_render(&store, "docs/page.md").expect("relative path");
        assert_eq!(path, PathBuf::from("project/wiki/docs/page.md"));
    }

    #[test]
    fn list_pages_returns_empty_when_wiki_root_missing() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let store = FileStore::new(temp.path());
        let response = list_pages(&store).expect("list pages");
        assert!(response.pages.is_empty());
    }

    #[test]
    fn to_service_error_maps_known_error_variants() {
        let io = to_service_error(KanbusError::Io("io".to_string()));
        assert!(matches!(io, WikiServiceError::Io(message) if message == "io"));

        let invalid = to_service_error(KanbusError::IssueOperation("bad path".to_string()));
        assert!(matches!(
            invalid,
            WikiServiceError::InvalidPath(message) if message == "bad path"
        ));
    }

    #[test]
    fn wiki_list_prefix_supports_default_and_external_wiki_directory() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let store = FileStore::new(temp.path());
        assert_eq!(
            wiki_list_prefix(&store).expect("default prefix"),
            "project/wiki"
        );

        write_config(temp.path(), "wiki_directory: ../docs/wiki\n");
        let store = FileStore::new(temp.path());
        assert_eq!(
            wiki_list_prefix(&store).expect("external prefix"),
            "docs/wiki"
        );
    }

    #[test]
    fn list_pages_collects_nested_markdown_and_sorts() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let root = temp.path().join("project").join("wiki");
        std::fs::create_dir_all(root.join("guides")).expect("create guides");
        std::fs::write(root.join("zeta.md"), "# zeta").expect("write zeta");
        std::fs::write(root.join("guides").join("alpha.md"), "# alpha").expect("write alpha");
        std::fs::write(root.join("notes.txt"), "ignore").expect("write txt");

        let store = FileStore::new(temp.path());
        let pages = list_pages(&store).expect("list pages");
        assert_eq!(pages.pages, vec!["guides/alpha.md", "zeta.md"]);
    }

    #[test]
    fn get_page_returns_content_and_not_found() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let root = temp.path().join("project").join("wiki");
        std::fs::create_dir_all(&root).expect("create wiki root");
        std::fs::write(root.join("readme.md"), "hello wiki").expect("write page");
        let store = FileStore::new(temp.path());

        let page = get_page(&store, "readme.md").expect("get page");
        assert_eq!(page.path, "readme.md");
        assert_eq!(page.content, "hello wiki");
        assert!(page.exists);

        let missing = get_page(&store, "missing.md").expect_err("missing page");
        assert!(matches!(missing, WikiServiceError::NotFound(_)));
    }

    #[test]
    fn create_update_rename_delete_page_cover_success_and_conflicts() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let store = FileStore::new(temp.path());

        let created = create_page(
            &store,
            &WikiCreateRequest {
                path: "docs/guide.md".to_string(),
                content: Some("v1".to_string()),
                overwrite: None,
            },
        )
        .expect("create page");
        assert_eq!(created.path, "docs/guide.md");
        assert!(created.created);

        let create_conflict = create_page(
            &store,
            &WikiCreateRequest {
                path: "docs/guide.md".to_string(),
                content: Some("v2".to_string()),
                overwrite: Some(false),
            },
        )
        .expect_err("create conflict");
        assert!(matches!(create_conflict, WikiServiceError::Conflict(_)));

        let overwritten = create_page(
            &store,
            &WikiCreateRequest {
                path: "docs/guide.md".to_string(),
                content: Some("v2".to_string()),
                overwrite: Some(true),
            },
        )
        .expect("overwrite create");
        assert_eq!(overwritten.path, "docs/guide.md");

        let updated = update_page(
            &store,
            &WikiUpdateRequest {
                path: "docs/guide.md".to_string(),
                content: "v3".to_string(),
            },
        )
        .expect("update page");
        assert!(updated.updated);

        let update_missing = update_page(
            &store,
            &WikiUpdateRequest {
                path: "docs/missing.md".to_string(),
                content: "nope".to_string(),
            },
        )
        .expect_err("update missing");
        assert!(matches!(update_missing, WikiServiceError::NotFound(_)));

        let rename = rename_page(
            &store,
            &WikiRenameRequest {
                from_path: "docs/guide.md".to_string(),
                to_path: "docs/archive/guide.md".to_string(),
                overwrite: None,
            },
        )
        .expect("rename page");
        assert_eq!(rename.from_path, "docs/guide.md");
        assert_eq!(rename.to_path, "docs/archive/guide.md");
        assert!(rename.renamed);

        create_page(
            &store,
            &WikiCreateRequest {
                path: "docs/conflict.md".to_string(),
                content: Some("left".to_string()),
                overwrite: None,
            },
        )
        .expect("create source");
        create_page(
            &store,
            &WikiCreateRequest {
                path: "docs/archive/conflict.md".to_string(),
                content: Some("right".to_string()),
                overwrite: None,
            },
        )
        .expect("create target");
        let rename_conflict = rename_page(
            &store,
            &WikiRenameRequest {
                from_path: "docs/conflict.md".to_string(),
                to_path: "docs/archive/conflict.md".to_string(),
                overwrite: Some(false),
            },
        )
        .expect_err("rename conflict");
        assert!(matches!(rename_conflict, WikiServiceError::Conflict(_)));

        let deleted = delete_page(&store, "docs/archive/guide.md").expect("delete page");
        assert_eq!(deleted.path, "docs/archive/guide.md");
        assert!(deleted.deleted);

        let delete_missing = delete_page(&store, "docs/archive/guide.md").expect_err("missing");
        assert!(matches!(delete_missing, WikiServiceError::NotFound(_)));
    }

    #[test]
    fn render_page_not_found_and_draft_error_cleanup_path() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_config(temp.path(), "");
        let store = FileStore::new(temp.path());

        let missing = render_page(
            &store,
            &WikiRenderRequestPayload {
                path: "drafts/missing.md".to_string(),
                content: None,
            },
        )
        .expect_err("missing render page");
        assert!(matches!(missing, WikiServiceError::NotFound(_)));

        let draft_error = render_page(
            &store,
            &WikiRenderRequestPayload {
                path: "drafts/test.md".to_string(),
                content: Some("# Draft".to_string()),
            },
        )
        .expect_err("draft render error");
        assert!(matches!(draft_error, WikiServiceError::Render(_)));

        let drafts_dir = temp.path().join("project").join("wiki").join("drafts");
        let leftovers = std::fs::read_dir(&drafts_dir)
            .expect("read drafts dir")
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.file_name().to_string_lossy().to_string())
            .filter(|name| name.starts_with("test.tmp.") && name.ends_with(".md"))
            .collect::<Vec<_>>();
        assert!(leftovers.is_empty());
    }
}
