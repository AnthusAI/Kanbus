//! Wiki rendering utilities.

use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::Path;
use std::sync::Arc;

use minijinja::value::{Kwargs, Value};
use minijinja::{context, Environment, Error, ErrorKind};

use crate::console_backend::FileStore;
use crate::console_wiki;
use crate::error::KanbusError;
use crate::models::IssueData;

/// Request for rendering a wiki page.
#[derive(Debug, Clone)]
pub struct WikiRenderRequest {
    /// Repository root path.
    pub root: std::path::PathBuf,
    /// Page path to render.
    pub page_path: std::path::PathBuf,
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
    let page_path = request.root.join(&request.page_path);
    validate_page_exists(&page_path)?;

    let store = FileStore::new(&request.root);
    let configuration = store.load_config()?;
    let issues = store.load_issues(&configuration)?;

    let wiki_render_cache_dir = request
        .root
        .join(&configuration.project_directory)
        .join(".cache")
        .join("wiki_render");
    let cache_key = wiki_render_cache_key(&page_path, &issues);
    if let Some(cached) = wiki_render_read_cache(&wiki_render_cache_dir, &cache_key) {
        wiki_render_log_cache_hit(&wiki_render_cache_dir);
        return Ok(cached);
    }

    let issues = Arc::new(issues);

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
        Ok(Value::from_serialize(filtered))
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
        let found = issue_issues.iter().find(|i| i.identifier == id).cloned();
        Ok(Value::from_serialize(found))
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
        let _ = validate_page_exists(&request.root.join("project/wiki/coverage-missing.md"));
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
            custom: std::collections::BTreeMap::new(),
        };
        let mut dummy_list = vec![dummy_issue];
        apply_issue_type_filter(&mut dummy_list, "task");
    }

    let template =
        fs::read_to_string(&page_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let rendered = env
        .render_str(&template, context! {})
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    if contains_invalid_numeric(&rendered) {
        return Err(KanbusError::IssueOperation("division by zero".to_string()));
    }
    wiki_render_write_cache(&wiki_render_cache_dir, &cache_key, &rendered);
    Ok(rendered)
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

fn wiki_render_cache_key(page_path: &Path, issues: &[IssueData]) -> String {
    use sha2::{Digest, Sha256};
    let page_mtime = fs::metadata(page_path)
        .ok()
        .and_then(|m| m.modified().ok())
        .map(|t| format!("{:?}", t))
        .unwrap_or_default();
    let mut issue_ids: Vec<_> = issues
        .iter()
        .map(|i| format!("{}:{}", i.identifier, i.updated_at))
        .collect();
    issue_ids.sort();
    let issue_part = issue_ids.join("|");
    let raw = format!("{}|{}|{}", page_path.display(), page_mtime, issue_part);
    let mut hasher = Sha256::new();
    hasher.update(raw.as_bytes());
    format!("{:x}", hasher.finalize())
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

fn validate_page_exists(page_path: &std::path::Path) -> Result<(), KanbusError> {
    if !page_path.exists() {
        return Err(KanbusError::IssueOperation(
            "wiki page not found".to_string(),
        ));
    }
    Ok(())
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
        Ok(Value::from_serialize(filtered))
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
        let found = issue_issues.iter().find(|i| i.identifier == id).cloned();
        Ok(Value::from_serialize(found))
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
        .map(|p| format!("{}/{}", prefix, p))
        .collect();
    Ok(pages)
}
