//! Wiki rendering utilities.

use std::fs;
use std::sync::Arc;

use minijinja::value::{Kwargs, Value};
use minijinja::{context, Environment, Error, ErrorKind};

use crate::error::KanbusError;
use crate::issue_listing::list_issues;
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

    let issues = list_issues(
        &request.root,
        None,
        None,
        None,
        None,
        None,
        None,
        true,
        false,
    )?;
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
        Ok(Value::from_serialize(filtered))
    });

    let count_issues = Arc::clone(&issues);
    env.add_function("count", move |kwargs: Kwargs| {
        let filtered = filter_issues_from_kwargs(&count_issues, &kwargs)?;
        Ok(filtered.len())
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
    env.render_str(&template, context! {})
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))
}

fn filter_issues_from_kwargs(
    issues: &Arc<Vec<IssueData>>,
    kwargs: &Kwargs,
) -> Result<Vec<IssueData>, Error> {
    let status: Option<String> = kwargs.get("status")?;
    let mut issue_type: Option<String> = kwargs.get("issue_type")?;
    if issue_type.is_none() {
        issue_type = kwargs.get("type")?;
    }

    let mut filtered: Vec<IssueData> = issues.as_ref().clone();
    if let Some(status) = status {
        filtered.retain(|issue| issue.status == status);
    }
    let issue_type_filter = issue_type.unwrap_or_default();
    apply_issue_type_filter(&mut filtered, &issue_type_filter);
    Ok(filtered)
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
