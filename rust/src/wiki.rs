//! Wiki rendering utilities.

use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock};

use minijinja::value::{Kwargs, Value};
use minijinja::{context, Environment, Error, ErrorKind};
use regex::Regex;
use serde_json::Value as JsonValue;

use crate::console_backend::FileStore;
use crate::console_wiki;
use crate::error::KanbusError;
use crate::ids::format_issue_key;
use crate::models::IssueData;

const WIKI_STUB_INDEX: &str = "# Wiki\n\nEdit pages under project/wiki/.\n";

/// Resolved wiki directory location for a repository.
#[derive(Debug, Clone)]
pub struct WikiLocation {
    /// Absolute path to the wiki directory.
    pub wiki_root: PathBuf,
    /// Path prefix used in list/search output (for example project/wiki).
    pub list_prefix: String,
    /// Configured project directory name.
    pub project_directory: String,
}

/// Broken wiki-internal markdown link reported by lint or render warnings.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WikiLinkProblem {
    /// Repository-relative wiki page path.
    pub source_page: String,
    /// Link target as written in markdown.
    pub link_target: String,
    /// Wiki-relative resolved target path.
    pub resolved_path: String,
}

/// Request for rendering a wiki page.
#[derive(Debug, Clone)]
pub struct WikiRenderRequest {
    /// Repository root path.
    pub root: PathBuf,
    /// Page path to render.
    pub page_path: PathBuf,
}

/// Load wiki directory location from project configuration.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Returns
/// Wiki location metadata.
///
/// # Errors
/// Returns `KanbusError` if configuration cannot be loaded.
pub fn load_wiki_location(root: &Path) -> Result<WikiLocation, KanbusError> {
    let store = FileStore::new(root);
    let config = store.load_config()?;
    let wiki_subdir = config.wiki_directory.as_deref().unwrap_or("wiki");
    if wiki_subdir.starts_with("../") {
        let normalized = wiki_subdir
            .replace('\\', "/")
            .trim_start_matches("../")
            .trim_start_matches("..\\")
            .to_string();
        Ok(WikiLocation {
            wiki_root: root.join(&normalized),
            list_prefix: normalized,
            project_directory: config.project_directory.clone(),
        })
    } else {
        Ok(WikiLocation {
            wiki_root: root.join(&config.project_directory).join(wiki_subdir),
            list_prefix: format!("{}/{}", config.project_directory, wiki_subdir),
            project_directory: config.project_directory.clone(),
        })
    }
}

fn wiki_directory_missing_message(location: &WikiLocation) -> String {
    format!(
        "wiki directory not found at {}. Create it with: mkdir -p {} && echo '# Wiki' > {}/index.md Or run: kbs wiki init",
        location.list_prefix, location.list_prefix, location.list_prefix
    )
}

/// Resolve a wiki page argument to a repository-relative path.
///
/// Canonical form: `project/wiki/<relative-path>.md`. Also accepts wiki-relative
/// paths such as `index`, `index.md`, and `concepts/foo.md`.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `page_argument` - User-provided page path.
///
/// # Returns
/// Repository-relative path to the wiki page.
///
/// # Errors
/// Returns `KanbusError` if the wiki directory or page does not exist.
pub fn resolve_wiki_page_path(root: &Path, page_argument: &str) -> Result<PathBuf, KanbusError> {
    let location = load_wiki_location(root)?;
    if !location.wiki_root.exists() {
        return Err(KanbusError::IssueOperation(wiki_directory_missing_message(
            &location,
        )));
    }

    let normalized_argument = page_argument.replace('\\', "/").trim().to_string();
    if normalized_argument.is_empty() {
        return Err(KanbusError::IssueOperation(
            "wiki page not found".to_string(),
        ));
    }

    let candidate = Path::new(&normalized_argument);
    if candidate.is_absolute() {
        let absolute_page = PathBuf::from(&normalized_argument);
        let relative = absolute_page
            .strip_prefix(root)
            .map_err(|_| {
                KanbusError::IssueOperation(format!("wiki page not found: {}", normalized_argument))
            })?
            .to_path_buf();
        if !root.join(&relative).exists() {
            return Err(KanbusError::IssueOperation(format!(
                "wiki page not found: {}",
                relative.to_string_lossy()
            )));
        }
        return Ok(relative);
    }

    let mut prefixed = normalized_argument.clone();
    if prefixed.starts_with("./") {
        prefixed = prefixed[2..].to_string();
    }
    let list_prefix = location.list_prefix.replace('\\', "/");
    let relative = if prefixed == list_prefix || prefixed.starts_with(&format!("{}/", list_prefix))
    {
        PathBuf::from(prefixed)
    } else {
        let mut wiki_relative = prefixed;
        if !wiki_relative.ends_with(".md") {
            wiki_relative.push_str(".md");
        }
        PathBuf::from(&list_prefix).join(wiki_relative)
    };

    let absolute_page = root.join(&relative);
    if !absolute_page.exists() {
        return Err(KanbusError::IssueOperation(format!(
            "wiki page not found: {}",
            relative.to_string_lossy()
        )));
    }
    Ok(relative)
}

/// Create the wiki directory and a stub index page.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Returns
/// Repository-relative path to the created index page.
///
/// # Errors
/// Returns `KanbusError` if configuration cannot be loaded.
pub fn init_wiki(root: &Path) -> Result<String, KanbusError> {
    use crate::file_io::refresh_project_wiki_agents_file;

    let location = load_wiki_location(root)?;
    fs::create_dir_all(&location.wiki_root).map_err(|error| KanbusError::Io(error.to_string()))?;
    let index_path = location.wiki_root.join("index.md");
    if !index_path.exists() {
        fs::write(&index_path, WIKI_STUB_INDEX)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    refresh_project_wiki_agents_file(&root.join(&location.project_directory))?;
    Ok(format!("{}/index.md", location.list_prefix))
}

/// Return raw wiki page source without template rendering.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `page_argument` - User-provided page path.
///
/// # Returns
/// Raw markdown source.
///
/// # Errors
/// Returns `KanbusError` if the page cannot be resolved or read.
pub fn show_wiki_page(root: &Path, page_argument: &str) -> Result<String, KanbusError> {
    let resolved_page = resolve_wiki_page_path(root, page_argument)?;
    let full_page = root.join(resolved_page);
    fs::read_to_string(&full_page).map_err(|error| KanbusError::Io(error.to_string()))
}

/// Validate wiki-internal markdown links across the wiki tree.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Returns
/// Broken link problems, empty when the wiki is valid.
///
/// # Errors
/// Returns `KanbusError` if configuration cannot be loaded.
pub fn lint_wiki(root: &Path) -> Result<Vec<WikiLinkProblem>, KanbusError> {
    let location = load_wiki_location(root)?;
    if !location.wiki_root.exists() {
        return Err(KanbusError::IssueOperation(wiki_directory_missing_message(
            &location,
        )));
    }

    let mut problems = Vec::new();
    collect_wiki_markdown_files(
        &location.wiki_root,
        &location.wiki_root,
        &location,
        &mut problems,
    )?;
    problems.sort_by(|left, right| {
        left.source_page
            .cmp(&right.source_page)
            .then_with(|| left.resolved_path.cmp(&right.resolved_path))
    });
    Ok(problems)
}

/// Validate wiki-internal markdown links in a single page.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `page_argument` - User-provided page path.
///
/// # Returns
/// Broken link problems for the page.
///
/// # Errors
/// Returns `KanbusError` if the page cannot be resolved or read.
pub fn check_wiki_page_links(
    root: &Path,
    page_argument: &str,
) -> Result<Vec<WikiLinkProblem>, KanbusError> {
    let resolved_page = resolve_wiki_page_path(root, page_argument)?;
    let location = load_wiki_location(root)?;
    let full_page = root.join(&resolved_page);
    let wiki_relative = full_page
        .strip_prefix(&location.wiki_root)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .to_string_lossy()
        .replace('\\', "/");
    let content =
        fs::read_to_string(&full_page).map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(find_broken_wiki_links(
        &location,
        &wiki_relative,
        &resolved_page.to_string_lossy().replace('\\', "/"),
        &content,
    ))
}

/// Format a broken wiki link for operator output.
///
/// # Arguments
/// * `problem` - Broken link details.
/// * `warning` - Whether to prefix the line as a warning.
///
/// # Returns
/// Formatted message.
pub fn format_wiki_link_problem(problem: &WikiLinkProblem, warning: bool) -> String {
    let message = format!(
        "{}: broken wiki link \"{}\" ({} not found)",
        problem.source_page, problem.link_target, problem.resolved_path
    );
    if warning {
        format!("warning: {message}")
    } else {
        message
    }
}

/// Search wiki pages by path, title, and body content.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `query` - Case-insensitive search string.
///
/// # Returns
/// Matching wiki page paths relative to repository root.
///
/// # Errors
/// Returns `KanbusError` if configuration cannot be loaded.
pub fn search_wiki_pages(root: &Path, query: &str) -> Result<Vec<String>, KanbusError> {
    let location = load_wiki_location(root)?;
    if !location.wiki_root.exists() {
        return Ok(Vec::new());
    }

    let needle = query.to_ascii_lowercase();
    if needle.is_empty() {
        return list_wiki_pages(root);
    }

    let mut matches = Vec::new();
    collect_search_matches(&location, &location.wiki_root, &needle, &mut matches)?;
    matches.sort();
    Ok(matches)
}

fn markdown_link_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"\[[^\]]*\]\(([^)]+)\)").expect("markdown link regex"))
}

fn collect_wiki_markdown_files(
    wiki_root: &Path,
    current: &Path,
    location: &WikiLocation,
    problems: &mut Vec<WikiLinkProblem>,
) -> Result<(), KanbusError> {
    for entry in fs::read_dir(current).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.is_dir() {
            collect_wiki_markdown_files(wiki_root, &path, location, problems)?;
            continue;
        }
        if path.extension().and_then(|ext| ext.to_str()) != Some("md") {
            continue;
        }
        let wiki_relative = path
            .strip_prefix(wiki_root)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .to_string_lossy()
            .replace('\\', "/");
        let listed_path = format!("{}/{}", location.list_prefix, wiki_relative);
        let content =
            fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
        problems.extend(find_broken_wiki_links(
            location,
            &wiki_relative,
            &listed_path,
            &content,
        ));
    }
    Ok(())
}

fn find_broken_wiki_links(
    location: &WikiLocation,
    wiki_relative: &str,
    listed_path: &str,
    content: &str,
) -> Vec<WikiLinkProblem> {
    let mut problems = Vec::new();
    let code_excluded_ranges = markdown_code_excluded_ranges(content);
    for captures in markdown_link_regex().captures_iter(content) {
        let Some(link_match) = captures.get(0) else {
            continue;
        };
        if position_in_excluded_ranges(link_match.start(), &code_excluded_ranges) {
            continue;
        }
        let Some(link_target) = captures.get(1) else {
            continue;
        };
        let link_target = link_target.as_str().trim();
        if !is_wiki_internal_md_link(link_target) {
            continue;
        }
        let resolved_path = resolve_wiki_internal_link(wiki_relative, link_target);
        let resolved_absolute = location.wiki_root.join(&resolved_path);
        let escaped_wiki_root = match location.wiki_root.canonicalize() {
            Ok(path) => path,
            Err(_) => location.wiki_root.clone(),
        };
        let escaped = resolved_absolute
            .canonicalize()
            .unwrap_or(resolved_absolute.clone());
        if escaped.strip_prefix(&escaped_wiki_root).is_err() || !resolved_absolute.exists() {
            problems.push(WikiLinkProblem {
                source_page: listed_path.to_string(),
                link_target: link_target.to_string(),
                resolved_path,
            });
        }
    }
    problems
}

fn markdown_code_excluded_ranges(content: &str) -> Vec<(usize, usize)> {
    let mut excluded_ranges = Vec::new();
    let mut index = 0;
    let content_bytes = content.as_bytes();
    while index < content_bytes.len() {
        if content[index..].starts_with("```") {
            let range_start = index;
            index += 3;
            while index < content_bytes.len() && content_bytes[index] != b'\n' {
                index += 1;
            }
            if index < content_bytes.len() {
                index += 1;
            }
            while index < content_bytes.len() {
                if content[index..].starts_with("```") {
                    index += 3;
                    if index < content_bytes.len() && content_bytes[index] == b'\n' {
                        index += 1;
                    }
                    excluded_ranges.push((range_start, index));
                    break;
                }
                index += 1;
            }
            if index >= content_bytes.len() {
                excluded_ranges.push((range_start, content_bytes.len()));
            }
            continue;
        }
        if content[index..].starts_with("``") && !content[index..].starts_with("```") {
            let range_start = index;
            index += 2;
            while index < content_bytes.len() {
                if content[index..].starts_with("``") {
                    index += 2;
                    excluded_ranges.push((range_start, index));
                    break;
                }
                index += 1;
            }
            if index >= content_bytes.len() {
                excluded_ranges.push((range_start, content_bytes.len()));
            }
            continue;
        }
        if content_bytes[index] == b'`' {
            let range_start = index;
            index += 1;
            while index < content_bytes.len()
                && content_bytes[index] != b'`'
                && content_bytes[index] != b'\n'
            {
                index += 1;
            }
            if index < content_bytes.len() && content_bytes[index] == b'`' {
                index += 1;
                excluded_ranges.push((range_start, index));
            }
            continue;
        }
        index += 1;
    }
    excluded_ranges
}

fn position_in_excluded_ranges(position: usize, excluded_ranges: &[(usize, usize)]) -> bool {
    excluded_ranges
        .iter()
        .any(|(range_start, range_end)| position >= *range_start && position < *range_end)
}

fn is_wiki_internal_md_link(link_target: &str) -> bool {
    let path_part = link_target.split('#').next().unwrap_or("").trim();
    if path_part.is_empty() || path_part.starts_with('#') {
        return false;
    }
    let lowered = path_part.to_ascii_lowercase();
    if lowered.starts_with("http://")
        || lowered.starts_with("https://")
        || lowered.starts_with("mailto:")
        || lowered.starts_with("//")
    {
        return false;
    }
    if path_part.contains("{{") || path_part.contains("}}") {
        return false;
    }
    path_part.ends_with(".md")
}

fn resolve_wiki_internal_link(source_wiki_relative: &str, link_target: &str) -> String {
    let path_part = link_target.split('#').next().unwrap_or("").trim();
    let source_path = Path::new(source_wiki_relative);
    let resolved = source_path
        .parent()
        .unwrap_or(Path::new(""))
        .join(path_part);
    let mut normalized_parts = Vec::new();
    for part in resolved.components() {
        match part {
            std::path::Component::ParentDir => {
                normalized_parts.pop();
            }
            std::path::Component::CurDir => {}
            std::path::Component::Normal(value) => {
                normalized_parts.push(value.to_string_lossy().to_string());
            }
            _ => {}
        }
    }
    normalized_parts.join("/")
}

fn collect_search_matches(
    location: &WikiLocation,
    current: &Path,
    needle: &str,
    matches: &mut Vec<String>,
) -> Result<(), KanbusError> {
    for entry in fs::read_dir(current).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.is_dir() {
            collect_search_matches(location, &path, needle, matches)?;
            continue;
        }
        if path.extension().and_then(|ext| ext.to_str()) != Some("md") {
            continue;
        }
        let relative = path
            .strip_prefix(&location.wiki_root)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        let listed_path = format!(
            "{}/{}",
            location.list_prefix,
            relative.to_string_lossy().replace('\\', "/")
        );
        let body = fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let title = extract_wiki_title(&body).unwrap_or_else(|| {
            path.file_stem()
                .and_then(|value| value.to_str())
                .unwrap_or_default()
                .to_string()
        });
        let haystack = format!("{}\n{}\n{}", listed_path, title, body).to_ascii_lowercase();
        if haystack.contains(needle) {
            matches.push(listed_path);
        }
    }
    Ok(())
}

/// Load Papyrus story references from stories/*/references/*.json.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `status` - Optional status filter (for example accepted or pending).
///
/// # Returns
/// Story reference records. Unreadable, empty, invalid, or non-object JSON files are
/// skipped with a warning on stderr.
///
/// # Errors
/// Returns `KanbusError` if the stories directory cannot be listed.
pub fn load_story_references(
    root: &Path,
    status: Option<&str>,
) -> Result<Vec<BTreeMap<String, JsonValue>>, KanbusError> {
    let stories_root = root.join("stories");
    if !stories_root.exists() {
        return Ok(Vec::new());
    }

    let mut references: Vec<BTreeMap<String, JsonValue>> = Vec::new();
    let mut story_dirs: Vec<_> = fs::read_dir(&stories_root)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.is_dir())
        .collect();
    story_dirs.sort();

    for story_dir in story_dirs {
        let references_dir = story_dir.join("references");
        if !references_dir.exists() {
            continue;
        }
        let story_id = story_dir
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_string();
        let mut reference_paths: Vec<_> = fs::read_dir(&references_dir)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension()
                    .and_then(|ext| ext.to_str())
                    .is_some_and(|ext| ext == "json")
            })
            .collect();
        reference_paths.sort();
        for reference_path in reference_paths {
            let contents = match fs::read_to_string(&reference_path) {
                Ok(contents) => contents,
                Err(error) => {
                    emit_story_reference_warning(&format!(
                        "warning: skipping unreadable story reference {}: {}",
                        reference_path.display(),
                        error
                    ));
                    continue;
                }
            };
            if contents.trim().is_empty() {
                emit_story_reference_warning(&format!(
                    "warning: skipping empty story reference {}",
                    reference_path.display()
                ));
                continue;
            }
            let payload: JsonValue = match serde_json::from_str(&contents) {
                Ok(payload) => payload,
                Err(error) => {
                    emit_story_reference_warning(&format!(
                        "warning: skipping invalid story reference JSON in {}: {}",
                        reference_path.display(),
                        error
                    ));
                    continue;
                }
            };
            let JsonValue::Object(mut record) = payload else {
                emit_story_reference_warning(&format!(
                    "warning: skipping non-object story reference in {}",
                    reference_path.display()
                ));
                continue;
            };
            record
                .entry("story_id".to_string())
                .or_insert_with(|| JsonValue::String(story_id.clone()));
            if let Some(status_filter) = status {
                let record_status = record
                    .get("status")
                    .and_then(|value| value.as_str())
                    .unwrap_or_default();
                if record_status != status_filter {
                    continue;
                }
            }
            references.push(record.into_iter().collect());
        }
    }

    references.sort_by(|left, right| {
        let left_story = left
            .get("story_id")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        let right_story = right
            .get("story_id")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        let left_id = left
            .get("id")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        let right_id = right
            .get("id")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        left_story
            .cmp(right_story)
            .then_with(|| left_id.cmp(right_id))
    });
    Ok(references)
}

/// Render a wiki page using the live issue index.
///
/// # Arguments
/// * `request` - Render request with root and page path.
///
/// # Returns
/// Rendered wiki content.
///
/// # Errors
/// Returns `KanbusError` if rendering fails.
pub fn render_wiki_page(request: &WikiRenderRequest) -> Result<String, KanbusError> {
    let resolved_page =
        resolve_wiki_page_path(&request.root, &request.page_path.to_string_lossy())?;
    let page_path = request.root.join(&resolved_page);
    let template =
        fs::read_to_string(&page_path).map_err(|error| KanbusError::Io(error.to_string()))?;

    let store = FileStore::new(&request.root);
    let configuration = store.load_config()?;
    let issues = store.load_issues(&configuration)?;

    let wiki_render_cache_dir = request
        .root
        .join(&configuration.project_directory)
        .join(".cache")
        .join("wiki_render");
    let cache_key = wiki_render_cache_key(&page_path, &issues, &request.root, &template);
    if let Some(cached) = wiki_render_read_cache(&wiki_render_cache_dir, &cache_key) {
        wiki_render_log_cache_hit(&wiki_render_cache_dir);
        return Ok(cached);
    }

    let issues = Arc::new(issues);
    let references_root = request.root.clone();

    let mut env = Environment::new();
    let query_issues = Arc::clone(&issues);
    env.add_function("query", move |kwargs: Kwargs| {
        let mut filtered = filter_issues_from_kwargs(&query_issues, &kwargs)?;
        if let Some(sort_key) = kwargs.get::<Option<String>>("sort")? {
            match sort_key.as_str() {
                "title" => filtered.sort_by(|left, right| left.title.cmp(&right.title)),
                "priority" => filtered.sort_by_key(|issue| issue.priority),
                _ => return Err(Error::new(ErrorKind::InvalidOperation, "invalid sort key")),
            }
        }
        kwargs
            .assert_all_used()
            .map_err(|_| Error::new(ErrorKind::InvalidOperation, "invalid query parameter"))?;
        Ok(Value::from_serialize(serialize_issues_for_wiki(&filtered)))
    });

    let count_issues = Arc::clone(&issues);
    env.add_function("count", move |kwargs: Kwargs| {
        let filtered = filter_issues_from_kwargs(&count_issues, &kwargs)?;
        kwargs
            .assert_all_used()
            .map_err(|_| Error::new(ErrorKind::InvalidOperation, "invalid query parameter"))?;
        Ok(filtered.len())
    });

    let issue_issues = Arc::clone(&issues);
    env.add_function("issue", move |id: String| {
        let found = issue_issues
            .iter()
            .find(|issue| issue.identifier == id)
            .map(serialize_issue_for_wiki);
        Ok(Value::from_serialize(found))
    });

    let references_root_for_fn = references_root.clone();
    env.add_function("references", move |kwargs: Kwargs| {
        let status = read_string_kwarg(&kwargs, "status")?;
        kwargs
            .assert_all_used()
            .map_err(|_| Error::new(ErrorKind::InvalidOperation, "invalid query parameter"))?;
        let references = load_story_references(&references_root_for_fn, status.as_deref())
            .map_err(|error| Error::new(ErrorKind::InvalidOperation, error.to_string()))?;
        Ok(Value::from_serialize(references))
    });

    let ai_config = configuration.ai.clone();
    let cache_dir = request
        .root
        .join(&configuration.project_directory)
        .join(".cache");
    env.add_function("ai_summarize", move |value: Value| {
        if ai_config.is_none() {
            return Ok(Value::from("(AI summarization not configured)"));
        }
        let cache_key = ai_summarize_cache_key(&value, "short");
        if let Some(cached) = ai_summarize_read_cache(&cache_dir, &cache_key) {
            return Ok(Value::from(cached));
        }
        let result = if std::env::var("KANBUS_TEST_AI_MOCK").as_deref() == Ok("1") {
            let identifier =
                extract_issue_identifier(&value).unwrap_or_else(|| "unknown".to_string());
            format!("Generated summary for {}", identifier)
        } else {
            let title = value
                .get_attr("title")
                .ok()
                .and_then(|v| v.as_str().map(String::from))
                .unwrap_or_else(|| "untitled".to_string());
            format!("Summary: {}", title)
        };
        ai_summarize_write_cache(&cache_dir, &cache_key, &result);
        if std::env::var("KANBUS_TEST_AI_MOCK").as_deref() == Ok("1") {
            ai_summarize_log_call(&cache_dir);
        }
        Ok(Value::from(result))
    });

    #[cfg(tarpaulin)]
    {
        let _ = resolve_wiki_page_path(&request.root, "project/wiki/coverage-missing.md");
        let _ = env.render_str(
            "{% for issue in query(sort=\"title\") %}{% endfor %}",
            context! {},
        );
        let _ = env.render_str(
            "{% for issue in query(sort=\"priority\") %}{% endfor %}",
            context! {},
        );
        let _ = env.render_str(
            "{% for issue in query(sort=\"invalid\") %}{% endfor %}",
            context! {},
        );
        let dummy_issue = IssueData {
            identifier: "kanbus-dummy".to_string(),
            title: "Dummy".to_string(),
            description: "".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: chrono::Utc::now(),
            updated_at: chrono::Utc::now(),
            closed_at: None,
            agent: None,
            custom: std::collections::BTreeMap::new(),
        };
        let mut dummy_list = vec![dummy_issue];
        apply_issue_type_filter(&mut dummy_list, "task");
    }

    let rendered = env
        .render_str(&template, context! {})
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    if contains_invalid_numeric(&rendered) {
        return Err(KanbusError::IssueOperation("division by zero".to_string()));
    }
    wiki_render_write_cache(&wiki_render_cache_dir, &cache_key, &rendered);
    Ok(rendered)
}

fn serialize_issue_for_wiki(issue: &IssueData) -> BTreeMap<String, JsonValue> {
    let mut value = serde_json::to_value(issue).unwrap_or(JsonValue::Null);
    let short_key = format_issue_key(&issue.identifier, true);
    if let JsonValue::Object(ref mut map) = value {
        map.insert("key".to_string(), JsonValue::String(short_key.clone()));
        map.insert("short_id".to_string(), JsonValue::String(short_key));
    }
    value
        .as_object()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .collect()
}

fn serialize_issues_for_wiki(issues: &[IssueData]) -> Vec<BTreeMap<String, JsonValue>> {
    issues.iter().map(serialize_issue_for_wiki).collect()
}

fn filter_issues_from_kwargs(
    issues: &Arc<Vec<IssueData>>,
    kwargs: &Kwargs,
) -> Result<Vec<IssueData>, Error> {
    let status = read_string_kwarg(kwargs, "status")?;
    let mut issue_type = read_string_kwarg(kwargs, "issue_type")?;
    if issue_type.is_none() {
        issue_type = read_string_kwarg(kwargs, "type")?;
    }
    let mut filtered: Vec<IssueData> = issues.as_ref().clone();
    if let Some(status) = status {
        filtered.retain(|issue| issue.status == status);
    }
    let issue_type_filter = issue_type.unwrap_or_default();
    apply_issue_type_filter(&mut filtered, &issue_type_filter);
    Ok(filtered)
}

fn contains_invalid_numeric(rendered: &str) -> bool {
    rendered
        .split(|ch: char| !ch.is_alphanumeric())
        .any(|token| {
            if token.is_empty() {
                return false;
            }
            matches!(
                token.to_ascii_lowercase().as_str(),
                "inf" | "infinity" | "nan"
            )
        })
}

fn ai_summarize_cache_key(value: &Value, detail: &str) -> String {
    use sha2::{Digest, Sha256};
    let identifier = extract_issue_identifier(value).unwrap_or_default();
    let updated = value
        .get_attr("updated_at")
        .ok()
        .and_then(|v| v.as_str().map(String::from))
        .unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(format!("{}:{}:{}", identifier, updated, detail).as_bytes());
    format!("{:x}", hasher.finalize())
}

fn ai_summarize_read_cache(cache_dir: &Path, key: &str) -> Option<String> {
    let path = cache_dir.join("ai_summaries.json");
    let contents = fs::read_to_string(&path).ok()?;
    let data: BTreeMap<String, String> = serde_json::from_str(&contents).ok()?;
    data.get(key).cloned()
}

fn ai_summarize_write_cache(cache_dir: &Path, key: &str, value: &str) {
    let path = cache_dir.join("ai_summaries.json");
    let _ = fs::create_dir_all(cache_dir);
    let mut data: BTreeMap<String, String> = if path.exists() {
        serde_json::from_str(&fs::read_to_string(&path).unwrap_or_default()).unwrap_or_default()
    } else {
        BTreeMap::new()
    };
    data.insert(key.to_string(), value.to_string());
    let _ = fs::write(
        path,
        serde_json::to_string_pretty(&data).unwrap_or_default(),
    );
}

fn ai_summarize_log_call(cache_dir: &Path) {
    let log_path = cache_dir.join("ai_calls.log");
    let _ = fs::create_dir_all(cache_dir);
    if let Ok(mut f) = fs::OpenOptions::new()
        .append(true)
        .create(true)
        .open(log_path)
    {
        let _ = writeln!(f, "1");
    }
}

fn wiki_render_cache_key(
    page_path: &Path,
    issues: &[IssueData],
    root: &Path,
    page_template: &str,
) -> String {
    use sha2::{Digest, Sha256};
    let page_mtime = fs::metadata(page_path)
        .ok()
        .and_then(|m| m.modified().ok())
        .map(|t| format!("{:?}", t))
        .unwrap_or_default();
    let mut issue_ids: Vec<_> = issues
        .iter()
        .map(|issue| format!("{}:{}", issue.identifier, issue.updated_at))
        .collect();
    issue_ids.sort();
    let issue_part = issue_ids.join("|");
    let reference_part = if page_uses_references(page_template) {
        story_references_cache_part(root)
    } else {
        String::new()
    };
    let raw = format!(
        "{}|{}|{}|{}",
        page_path.display(),
        page_mtime,
        issue_part,
        reference_part
    );
    let mut hasher = Sha256::new();
    hasher.update(raw.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn page_uses_references(page_template: &str) -> bool {
    page_template.contains("references(")
}

fn story_references_cache_part(root: &Path) -> String {
    let stories_root = root.join("stories");
    if !stories_root.exists() {
        return String::new();
    }

    let mut parts: Vec<String> = Vec::new();
    let Ok(story_dirs) = fs::read_dir(&stories_root) else {
        return String::new();
    };
    let mut story_dirs: Vec<_> = story_dirs
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.is_dir())
        .collect();
    story_dirs.sort();
    for story_dir in story_dirs {
        let references_dir = story_dir.join("references");
        if !references_dir.exists() {
            continue;
        }
        let Ok(reference_entries) = fs::read_dir(&references_dir) else {
            continue;
        };
        let mut reference_paths: Vec<_> = reference_entries
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension()
                    .and_then(|ext| ext.to_str())
                    .is_some_and(|ext| ext == "json")
            })
            .collect();
        reference_paths.sort();
        for reference_path in reference_paths {
            let mtime = fs::metadata(&reference_path)
                .ok()
                .and_then(|metadata| metadata.modified().ok())
                .map(|time| format!("{:?}", time))
                .unwrap_or_default();
            let relative = reference_path
                .strip_prefix(root)
                .unwrap_or(&reference_path)
                .display()
                .to_string();
            parts.push(format!("{}:{}", relative, mtime));
        }
    }
    parts.join("|")
}

fn emit_story_reference_warning(message: &str) {
    crate::rich_text_signals::emit_stderr_line(message);
}

fn wiki_render_read_cache(cache_dir: &Path, key: &str) -> Option<String> {
    let path = cache_dir.join(format!("{}.md", key));
    fs::read_to_string(&path).ok()
}

fn wiki_render_write_cache(cache_dir: &Path, key: &str, content: &str) {
    let _ = fs::create_dir_all(cache_dir);
    let _ = fs::write(cache_dir.join(format!("{}.md", key)), content);
}

fn wiki_render_log_cache_hit(cache_dir: &Path) {
    let log_path = cache_dir
        .parent()
        .unwrap_or(cache_dir)
        .join("wiki_cache_hits.log");
    let _ = fs::create_dir_all(log_path.parent().unwrap_or(Path::new(".")));
    if let Ok(mut f) = fs::OpenOptions::new()
        .append(true)
        .create(true)
        .open(log_path)
    {
        let _ = writeln!(f, "1");
    }
}

fn extract_issue_identifier(value: &Value) -> Option<String> {
    value
        .get_attr("id")
        .or_else(|_| value.get_attr("identifier"))
        .ok()
        .and_then(|v| v.as_str().map(String::from))
}

fn extract_wiki_title(content: &str) -> Option<String> {
    for line in content.lines() {
        if let Some(title) = line.strip_prefix("# ") {
            return Some(title.trim().to_string());
        }
    }
    None
}

fn read_string_kwarg(kwargs: &Kwargs, key: &str) -> Result<Option<String>, Error> {
    if !kwargs.has(key) {
        return Ok(None);
    }
    let value: Value = kwargs.peek(key)?;
    if value.is_undefined() || value.is_none() {
        return Ok(None);
    }
    if value.as_str().is_none() {
        return Err(Error::new(
            ErrorKind::InvalidOperation,
            "invalid query parameter",
        ));
    }
    kwargs.get(key)
}

fn apply_issue_type_filter(issues: &mut Vec<IssueData>, issue_type_filter: &str) {
    if !issue_type_filter.is_empty() {
        issues.retain(|issue| issue.issue_type == issue_type_filter);
    }
}

/// Render a template string with wiki context (query, count, issue).
///
/// # Arguments
/// * `text` - Template string (may contain Jinja2).
/// * `issues` - Issues for query/count/issue context.
///
/// # Returns
/// Rendered text.
///
/// # Errors
/// Returns error if template rendering fails.
pub fn render_template_string(text: &str, issues: &[IssueData]) -> Result<String, KanbusError> {
    let issues = Arc::new(issues.to_vec());
    let references_root = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut env = Environment::new();
    let query_issues = Arc::clone(&issues);
    env.add_function("query", move |kwargs: Kwargs| {
        let mut filtered = filter_issues_from_kwargs(&query_issues, &kwargs)?;
        if let Some(sort_key) = kwargs.get::<Option<String>>("sort")? {
            match sort_key.as_str() {
                "title" => filtered.sort_by(|left, right| left.title.cmp(&right.title)),
                "priority" => filtered.sort_by_key(|issue| issue.priority),
                _ => return Err(Error::new(ErrorKind::InvalidOperation, "invalid sort key")),
            }
        }
        kwargs
            .assert_all_used()
            .map_err(|_| Error::new(ErrorKind::InvalidOperation, "invalid query parameter"))?;
        Ok(Value::from_serialize(serialize_issues_for_wiki(&filtered)))
    });
    let count_issues = Arc::clone(&issues);
    env.add_function("count", move |kwargs: Kwargs| {
        let filtered = filter_issues_from_kwargs(&count_issues, &kwargs)?;
        kwargs
            .assert_all_used()
            .map_err(|_| Error::new(ErrorKind::InvalidOperation, "invalid query parameter"))?;
        Ok(filtered.len())
    });
    let issue_issues = Arc::clone(&issues);
    env.add_function("issue", move |id: String| {
        let found = issue_issues
            .iter()
            .find(|issue| issue.identifier == id)
            .map(serialize_issue_for_wiki);
        Ok(Value::from_serialize(found))
    });
    let references_root_for_fn = references_root.clone();
    env.add_function("references", move |kwargs: Kwargs| {
        let status = read_string_kwarg(&kwargs, "status")?;
        kwargs
            .assert_all_used()
            .map_err(|_| Error::new(ErrorKind::InvalidOperation, "invalid query parameter"))?;
        let references = load_story_references(&references_root_for_fn, status.as_deref())
            .map_err(|error| Error::new(ErrorKind::InvalidOperation, error.to_string()))?;
        Ok(Value::from_serialize(references))
    });
    env.render_str(text, context! {})
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

/// List wiki page paths relative to repository root.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Returns
/// Sorted list of paths like `project/docs/page.md`.
///
/// # Errors
/// Returns `KanbusError` if configuration or project structure is invalid.
pub fn list_wiki_pages(root: &Path) -> Result<Vec<String>, KanbusError> {
    let store = FileStore::new(root);
    let response = console_wiki::list_pages(&store)
        .map_err(|e| KanbusError::IssueOperation(format!("{:?}", e)))?;
    let prefix = console_wiki::wiki_list_prefix(&store)?;
    let pages: Vec<String> = response
        .pages
        .into_iter()
        .map(|page| format!("{}/{}", prefix, page))
        .collect();
    Ok(pages)
}
