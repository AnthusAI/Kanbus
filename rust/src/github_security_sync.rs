//! GitHub security synchronization support.
//!
//! Pulls Dependabot alerts from the GitHub REST API and creates/updates Kanbus
//! issues under a managed hierarchy.

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use chrono::Utc;
use serde_json::Value;

use crate::beads_write::{create_beads_issue, update_beads_issue};
use crate::error::KanbusError;
use crate::file_io::load_project_directory;
use crate::ids::{generate_issue_identifier, IssueIdentifierRequest};
use crate::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use crate::migration::load_beads_issues;
use crate::models::{GithubSecurityConfiguration, IssueData};

const GITHUB_API_BASE: &str = "https://api.github.com";
const GITHUB_API_VERSION: &str = "2022-11-28";
const GITHUB_SECURITY_INITIATIVE_TITLE: &str = "GitHub Security Remediation";
const GITHUB_DEPENDABOT_EPIC_TITLE: &str = "GitHub Dependabot Alerts";

/// Result of a Dependabot pull operation.
#[derive(Debug)]
pub struct DependabotPullResult {
    pub pulled: usize,
    pub updated: usize,
    pub skipped: usize,
}

/// Pull Dependabot alerts from GitHub and create/update Kanbus issues.
pub fn pull_dependabot_from_github(
    root: &Path,
    github_security_config: &GithubSecurityConfiguration,
    project_key: &str,
    dry_run: bool,
) -> Result<DependabotPullResult, KanbusError> {
    let token = std::env::var("GITHUB_TOKEN")
        .or_else(|_| std::env::var("GH_TOKEN"))
        .map_err(|_| {
            KanbusError::Configuration(
                "GITHUB_TOKEN or GH_TOKEN environment variable is not set".to_string(),
            )
        })?;

    let dependabot_config = github_security_config
        .dependabot
        .clone()
        .unwrap_or_default();
    let repo = github_security_config
        .repo
        .clone()
        .or_else(|| detect_repo_from_git(root))
        .ok_or_else(|| {
            KanbusError::Configuration(
                "could not determine GitHub repository slug (use --repo or github_security.repo)"
                    .to_string(),
            )
        })?;

    validate_dependabot_state(&dependabot_config.state)?;
    let min_priority = severity_to_priority(&dependabot_config.min_severity);

    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "issues directory does not exist".to_string(),
        ));
    }

    let alerts = fetch_dependabot_alerts(&repo, &token, &dependabot_config.state)?;
    let filtered_alerts: Vec<Value> = alerts
        .into_iter()
        .filter(|alert| severity_to_priority(&alert_severity(alert)) <= min_priority)
        .collect();

    let mut all_existing = list_issue_identifiers(&issues_dir)?;
    let alert_index = build_alert_index(&all_existing, &issues_dir);
    let task_index = build_manifest_task_index(&all_existing, &issues_dir);

    let parent_epic = resolve_dependabot_epic(
        &issues_dir,
        project_key,
        dependabot_config.parent_epic.as_deref(),
        dry_run,
        &mut all_existing,
    )?;

    let mut grouped: BTreeMap<String, Vec<&Value>> = BTreeMap::new();
    for alert in &filtered_alerts {
        grouped
            .entry(task_target_key(alert))
            .or_default()
            .push(alert);
    }

    let mut pulled = 0usize;
    let mut updated = 0usize;
    let skipped = 0usize;

    for (target_key, alerts_for_target) in grouped {
        let task_ctx = ManifestTaskContext {
            issues_dir: &issues_dir,
            project_key,
            repo: &repo,
            parent_epic: &parent_epic,
            priority: min_priority_for_alerts(&alerts_for_target),
            dry_run,
        };
        let task_id =
            resolve_manifest_task(&task_ctx, &target_key, &task_index, &mut all_existing)?;

        for alert in alerts_for_target {
            let alert_number = alert_number(alert);
            if alert_number <= 0 {
                continue;
            }
            let index_key = format!("{repo}#{alert_number}");
            let existing_kanbus_id = alert_index.get(&index_key);
            let (kanbus_id, action) = if let Some(id) = existing_kanbus_id {
                (id.clone(), "updated")
            } else {
                let request = IssueIdentifierRequest {
                    title: dependabot_alert_title(alert),
                    existing_ids: all_existing.clone(),
                    prefix: project_key.to_string(),
                };
                let result = generate_issue_identifier(&request)?;
                let new_id = result.identifier.clone();
                all_existing.insert(new_id.clone());
                (new_id, "pulled ")
            };

            let mut issue = map_dependabot_to_kanbus(alert, &repo, &task_id);
            issue.identifier = kanbus_id.clone();

            let issue_path = issue_path_for_identifier(&issues_dir, &kanbus_id);
            if action == "updated" {
                if let Ok(existing) = read_issue_from_file(&issue_path) {
                    issue.created_at = existing.created_at;
                }
            }

            let severity = alert_severity(alert);
            println!(
                "{action}  [{severity:<8}]  {:<14}  \"{}\"",
                short_key(&kanbus_id),
                issue.title
            );

            if !dry_run {
                write_issue_to_file(&issue, &issue_path)?;
            }

            if action == "updated" {
                updated += 1;
            } else {
                pulled += 1;
            }
        }
    }

    Ok(DependabotPullResult {
        pulled,
        updated,
        skipped,
    })
}

/// Pull Dependabot alerts from GitHub and create/update Beads issues.
pub fn pull_dependabot_from_github_beads(
    root: &Path,
    github_security_config: &GithubSecurityConfiguration,
    dry_run: bool,
) -> Result<DependabotPullResult, KanbusError> {
    let token = std::env::var("GITHUB_TOKEN")
        .or_else(|_| std::env::var("GH_TOKEN"))
        .map_err(|_| {
            KanbusError::Configuration(
                "GITHUB_TOKEN or GH_TOKEN environment variable is not set".to_string(),
            )
        })?;

    let dependabot_config = github_security_config
        .dependabot
        .clone()
        .unwrap_or_default();
    let repo = github_security_config
        .repo
        .clone()
        .or_else(|| detect_repo_from_git(root))
        .ok_or_else(|| {
            KanbusError::Configuration(
                "could not determine GitHub repository slug (use --repo or github_security.repo)"
                    .to_string(),
            )
        })?;

    validate_dependabot_state(&dependabot_config.state)?;
    let min_priority = severity_to_priority(&dependabot_config.min_severity);

    let alerts = fetch_dependabot_alerts(&repo, &token, &dependabot_config.state)?;
    let filtered_alerts: Vec<Value> = alerts
        .into_iter()
        .filter(|alert| severity_to_priority(&alert_severity(alert)) <= min_priority)
        .collect();

    let existing_issues = load_beads_issues(root)?;
    let alert_index = build_beads_alert_index(&existing_issues);
    let task_index = build_beads_task_index(&existing_issues);

    let initiative_id = resolve_beads_initiative(root, &existing_issues, dry_run)?;
    let parent_epic = resolve_beads_epic(
        root,
        &existing_issues,
        dependabot_config.parent_epic.as_deref(),
        &initiative_id,
        dry_run,
    )?;

    let mut grouped: BTreeMap<String, Vec<&Value>> = BTreeMap::new();
    for alert in &filtered_alerts {
        grouped
            .entry(task_target_key(alert))
            .or_default()
            .push(alert);
    }

    let mut pulled = 0usize;
    let mut updated = 0usize;
    let skipped = 0usize;
    let mut runtime_alert_index = alert_index.clone();
    let mut runtime_task_index = task_index.clone();

    for (target_key, alerts_for_target) in grouped {
        let task_id = resolve_beads_task(
            root,
            &repo,
            &target_key,
            &parent_epic,
            min_priority_for_alerts(&alerts_for_target),
            dry_run,
            &mut runtime_task_index,
        )?;

        for alert in alerts_for_target {
            let alert_number = alert_number(alert);
            if alert_number <= 0 {
                continue;
            }
            let index_key = format!("{repo}#{alert_number}");
            let existing_kanbus_id = runtime_alert_index.get(&index_key).cloned();

            let title = dependabot_alert_title(alert);
            let description = map_dependabot_to_beads_description(alert, &repo);
            let priority_u8 = priority_to_u8(severity_to_priority(&alert_severity(alert)))?;

            let (kanbus_id, action) = if let Some(id) = existing_kanbus_id {
                if !dry_run {
                    let add_labels: Vec<String> = Vec::new();
                    let remove_labels: Vec<String> = Vec::new();
                    update_beads_issue(
                        root,
                        &id,
                        Some("open"),
                        Some(priority_u8),
                        Some(&title),
                        Some(&description),
                        None,
                        &add_labels,
                        &remove_labels,
                        Some("security,github,dependabot"),
                    )?;
                }
                (id, "updated")
            } else if dry_run {
                ("would-create".to_string(), "pulled ")
            } else {
                let created = create_beads_issue(
                    root,
                    &title,
                    Some("sub-task"),
                    Some(priority_u8),
                    None,
                    Some(&task_id),
                    Some(&description),
                )?;
                let add_labels: Vec<String> = Vec::new();
                let remove_labels: Vec<String> = Vec::new();
                let created_id = created.identifier.clone();
                update_beads_issue(
                    root,
                    &created_id,
                    Some("open"),
                    Some(priority_u8),
                    Some(&title),
                    Some(&description),
                    None,
                    &add_labels,
                    &remove_labels,
                    Some("security,github,dependabot"),
                )?;
                runtime_alert_index.insert(index_key.clone(), created_id.clone());
                (created_id, "pulled ")
            };

            let severity = alert_severity(alert);
            println!(
                "{action}  [{severity:<8}]  {:<14}  \"{}\"",
                short_key(&kanbus_id),
                title
            );

            if action == "updated" {
                updated += 1;
            } else {
                pulled += 1;
            }
        }
    }

    Ok(DependabotPullResult {
        pulled,
        updated,
        skipped,
    })
}

fn validate_dependabot_state(state: &str) -> Result<(), KanbusError> {
    let valid = ["open", "fixed", "dismissed", "auto_dismissed"];
    if valid.contains(&state) {
        Ok(())
    } else {
        Err(KanbusError::Configuration(format!(
            "invalid dependabot state '{state}' (expected one of: {})",
            valid.join(", ")
        )))
    }
}

fn resolve_dependabot_epic(
    issues_dir: &Path,
    project_key: &str,
    configured_id: Option<&str>,
    dry_run: bool,
    all_existing: &mut HashSet<String>,
) -> Result<String, KanbusError> {
    if let Some(id) = configured_id {
        let path = issue_path_for_identifier(issues_dir, id);
        if path.exists() {
            return Ok(id.to_string());
        }
    }

    let initiative_id =
        resolve_security_initiative(issues_dir, project_key, dry_run, all_existing)?;

    if let Some(existing) = find_existing_dependabot_epic(issues_dir, all_existing, &initiative_id)
    {
        return Ok(existing);
    }

    let request = IssueIdentifierRequest {
        title: GITHUB_DEPENDABOT_EPIC_TITLE.to_string(),
        existing_ids: all_existing.clone(),
        prefix: project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let epic_id = result.identifier.clone();
    all_existing.insert(epic_id.clone());

    let now = Utc::now();
    let epic = IssueData {
        identifier: epic_id.clone(),
        title: GITHUB_DEPENDABOT_EPIC_TITLE.to_string(),
        description: "Dependabot alerts imported from GitHub Security.".to_string(),
        issue_type: "epic".to_string(),
        status: "open".to_string(),
        priority: 1,
        assignee: None,
        creator: None,
        parent: Some(initiative_id),
        labels: vec![
            "security".to_string(),
            "github".to_string(),
            "dependabot".to_string(),
        ],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: BTreeMap::new(),
    };

    println!("created  [epic    ]  \"{GITHUB_DEPENDABOT_EPIC_TITLE}\"");

    if !dry_run {
        let path = issue_path_for_identifier(issues_dir, &epic_id);
        write_issue_to_file(&epic, &path)?;
    }

    Ok(epic_id)
}

fn resolve_security_initiative(
    issues_dir: &Path,
    project_key: &str,
    dry_run: bool,
    all_existing: &mut HashSet<String>,
) -> Result<String, KanbusError> {
    if let Some(existing) = find_existing_security_initiative(issues_dir, all_existing) {
        return Ok(existing);
    }

    let request = IssueIdentifierRequest {
        title: GITHUB_SECURITY_INITIATIVE_TITLE.to_string(),
        existing_ids: all_existing.clone(),
        prefix: project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let initiative_id = result.identifier.clone();
    all_existing.insert(initiative_id.clone());

    let now = Utc::now();
    let initiative = IssueData {
        identifier: initiative_id.clone(),
        title: GITHUB_SECURITY_INITIATIVE_TITLE.to_string(),
        description: "Track remediation of GitHub security findings.".to_string(),
        issue_type: "initiative".to_string(),
        status: "open".to_string(),
        priority: 1,
        assignee: None,
        creator: None,
        parent: None,
        labels: vec!["security".to_string(), "github".to_string()],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: BTreeMap::new(),
    };

    println!("created  [initiative]  \"{GITHUB_SECURITY_INITIATIVE_TITLE}\"");

    if !dry_run {
        let path = issue_path_for_identifier(issues_dir, &initiative_id);
        write_issue_to_file(&initiative, &path)?;
    }

    Ok(initiative_id)
}

fn find_existing_security_initiative(
    issues_dir: &Path,
    all_existing: &HashSet<String>,
) -> Option<String> {
    let mut best_id: Option<String> = None;
    let mut best_updated = None;

    for id in all_existing {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if issue.issue_type != "initiative" {
                continue;
            }
            if issue.title != GITHUB_SECURITY_INITIATIVE_TITLE {
                continue;
            }
            if !issue.labels.iter().any(|l| l == "github") {
                continue;
            }
            let updated = issue.updated_at;
            if best_updated.is_none_or(|current| updated > current) {
                best_updated = Some(updated);
                best_id = Some(issue.identifier.clone());
            }
        }
    }

    best_id
}

fn find_existing_dependabot_epic(
    issues_dir: &Path,
    all_existing: &HashSet<String>,
    parent_initiative: &str,
) -> Option<String> {
    let mut best_id: Option<String> = None;
    let mut best_updated = None;

    for id in all_existing {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if issue.issue_type != "epic" {
                continue;
            }
            if issue.title != GITHUB_DEPENDABOT_EPIC_TITLE {
                continue;
            }
            if !issue.labels.iter().any(|l| l == "dependabot") {
                continue;
            }
            if issue.parent.as_deref() != Some(parent_initiative) {
                continue;
            }
            let updated = issue.updated_at;
            if best_updated.is_none_or(|current| updated > current) {
                best_updated = Some(updated);
                best_id = Some(issue.identifier.clone());
            }
        }
    }

    best_id
}

fn resolve_manifest_task(
    ctx: &ManifestTaskContext<'_>,
    target_key: &str,
    task_index: &BTreeMap<String, String>,
    all_existing: &mut HashSet<String>,
) -> Result<String, KanbusError> {
    if let Some(existing_id) = task_index.get(target_key) {
        if !ctx.dry_run {
            let path = issue_path_for_identifier(ctx.issues_dir, existing_id);
            if let Ok(mut issue) = read_issue_from_file(&path) {
                let mut changed = false;
                if issue.parent.as_deref() != Some(ctx.parent_epic) {
                    issue.parent = Some(ctx.parent_epic.to_string());
                    changed = true;
                }
                if issue.priority != ctx.priority {
                    issue.priority = ctx.priority;
                    changed = true;
                }
                if !issue.labels.iter().any(|l| l == "github") {
                    issue.labels.push("github".to_string());
                    changed = true;
                }
                if !issue.labels.iter().any(|l| l == "dependabot") {
                    issue.labels.push("dependabot".to_string());
                    changed = true;
                }
                if !issue.labels.iter().any(|l| l == "security") {
                    issue.labels.push("security".to_string());
                    changed = true;
                }
                if changed {
                    issue.updated_at = Utc::now();
                    write_issue_to_file(&issue, &path)?;
                    println!(
                        "updated  [task    ]  {:<14}  \"{}\"",
                        short_key(existing_id),
                        issue.title
                    );
                }
            }
        }
        return Ok(existing_id.clone());
    }

    let title = format!("{}:{target_key}", ctx.repo);
    let request = IssueIdentifierRequest {
        title: title.clone(),
        existing_ids: all_existing.clone(),
        prefix: ctx.project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let task_id = result.identifier.clone();
    all_existing.insert(task_id.clone());

    let now = Utc::now();
    let mut custom = BTreeMap::new();
    custom.insert(
        "github_provider".to_string(),
        Value::String("dependabot".to_string()),
    );
    custom.insert(
        "github_repository".to_string(),
        Value::String(ctx.repo.to_string()),
    );
    custom.insert(
        "github_manifest_path".to_string(),
        Value::String(target_key.to_string()),
    );

    let task = IssueData {
        identifier: task_id.clone(),
        title: title.clone(),
        description: format!("Dependabot alerts for `{target_key}`."),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: ctx.priority,
        assignee: None,
        creator: None,
        parent: Some(ctx.parent_epic.to_string()),
        labels: vec![
            "security".to_string(),
            "github".to_string(),
            "dependabot".to_string(),
        ],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom,
    };

    println!("created  [task    ]  \"{title}\"");
    if !ctx.dry_run {
        let path = issue_path_for_identifier(ctx.issues_dir, &task_id);
        write_issue_to_file(&task, &path)?;
    }

    Ok(task_id)
}

struct ManifestTaskContext<'a> {
    issues_dir: &'a Path,
    project_key: &'a str,
    repo: &'a str,
    parent_epic: &'a str,
    priority: i32,
    dry_run: bool,
}

fn map_dependabot_to_kanbus(alert: &Value, repo: &str, task_id: &str) -> IssueData {
    let number = alert_number(alert);
    let package_name = alert_package_name(alert);
    let severity = alert_severity(alert);
    let state = alert_state(alert);
    let advisory_summary = alert["security_advisory"]["summary"]
        .as_str()
        .unwrap_or("Dependabot alert")
        .to_string();
    let advisory_description = alert["security_advisory"]["description"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let html_url = alert["html_url"].as_str().unwrap_or("").to_string();
    let manifest_path = alert_manifest_path(alert);
    let ecosystem = alert_ecosystem(alert);
    let ghsa_id = alert["security_advisory"]["ghsa_id"]
        .as_str()
        .unwrap_or("")
        .to_string();

    let title = if package_name.is_empty() {
        format!("[Dependabot] Alert #{number}: {advisory_summary}")
    } else {
        format!("[Dependabot] {ghsa_id} in {package_name}")
    };

    let description = format!(
        "## {advisory_summary}\n\n\
         **Provider:** GitHub Dependabot\n\
         **Repository:** `{repo}`\n\
         **Alert Number:** {number}\n\
         **Severity:** {severity}\n\
         **State:** {state}\n\
         **Package:** `{package_name}`\n\
         **Ecosystem:** `{ecosystem}`\n\
         **Manifest:** `{manifest_path}`\n\n\
         ### Advisory\n\
         {advisory_description}\n\n\
         ### Reference\n\
         - {html_url}"
    );

    let mut custom = BTreeMap::new();
    custom.insert(
        "github_provider".to_string(),
        Value::String("dependabot".to_string()),
    );
    custom.insert(
        "github_alert_number".to_string(),
        Value::Number(number.into()),
    );
    custom.insert(
        "github_repository".to_string(),
        Value::String(repo.to_string()),
    );
    custom.insert(
        "github_manifest_path".to_string(),
        Value::String(manifest_path.clone()),
    );
    custom.insert(
        "github_ecosystem".to_string(),
        Value::String(ecosystem.clone()),
    );
    custom.insert(
        "github_package".to_string(),
        Value::String(package_name.clone()),
    );
    custom.insert(
        "github_severity".to_string(),
        Value::String(severity.clone()),
    );
    custom.insert(
        "github_alert_state".to_string(),
        Value::String(state.clone()),
    );
    custom.insert(
        "github_html_url".to_string(),
        Value::String(html_url.clone()),
    );

    let now = Utc::now();
    IssueData {
        identifier: String::new(),
        title,
        description,
        issue_type: "sub-task".to_string(),
        status: "open".to_string(),
        priority: severity_to_priority(&severity),
        assignee: None,
        creator: None,
        parent: Some(task_id.to_string()),
        labels: vec![
            "security".to_string(),
            "github".to_string(),
            "dependabot".to_string(),
        ],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom,
    }
}

fn build_alert_index(
    existing_ids: &HashSet<String>,
    issues_dir: &Path,
) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for id in existing_ids {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            let provider = issue
                .custom
                .get("github_provider")
                .and_then(Value::as_str)
                .unwrap_or("");
            let number = issue
                .custom
                .get("github_alert_number")
                .and_then(Value::as_i64)
                .unwrap_or_default();
            let repository = issue
                .custom
                .get("github_repository")
                .and_then(Value::as_str)
                .unwrap_or("");
            if provider == "dependabot" && number > 0 && !repository.is_empty() {
                index.insert(format!("{repository}#{number}"), id.clone());
            }
        }
    }
    index
}

fn build_manifest_task_index(
    existing_ids: &HashSet<String>,
    issues_dir: &Path,
) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for id in existing_ids {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if issue.issue_type != "task" {
                continue;
            }
            let provider = issue
                .custom
                .get("github_provider")
                .and_then(Value::as_str)
                .unwrap_or("");
            let manifest = issue
                .custom
                .get("github_manifest_path")
                .and_then(Value::as_str)
                .unwrap_or("");
            if provider == "dependabot" && !manifest.is_empty() {
                index.insert(manifest.to_string(), id.clone());
            }
        }
    }
    index
}

fn fetch_dependabot_alerts(
    repository: &str,
    token: &str,
    state: &str,
) -> Result<Vec<Value>, KanbusError> {
    let client = reqwest::blocking::Client::new();
    let mut alerts = Vec::new();

    let mut next_url = Some(format!(
        "{GITHUB_API_BASE}/repos/{repository}/dependabot/alerts?state={state}&per_page=100"
    ));

    while let Some(url) = next_url {
        let response = client
            .get(&url)
            .bearer_auth(token)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", GITHUB_API_VERSION)
            .header("User-Agent", "kanbus-cli")
            .send()
            .map_err(|error| {
                KanbusError::IssueOperation(format!("GitHub request failed: {error}"))
            })?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            return Err(KanbusError::IssueOperation(format!(
                "GitHub Dependabot API returned {status}: {body}"
            )));
        }

        let headers = response.headers().clone();
        let page: Vec<Value> = response.json().map_err(|error| {
            KanbusError::IssueOperation(format!("Failed to parse Dependabot response: {error}"))
        })?;
        alerts.extend(page);

        let link = headers.get("link").and_then(|value| value.to_str().ok());
        next_url = parse_next_link(link);
    }

    Ok(alerts)
}

fn parse_next_link(link_header: Option<&str>) -> Option<String> {
    let header = link_header?;
    for part in header.split(',') {
        let trimmed = part.trim();
        if !trimmed.contains("rel=\"next\"") {
            continue;
        }
        let start = trimmed.find('<')?;
        let end = trimmed.find('>')?;
        if start + 1 >= end {
            return None;
        }
        return Some(trimmed[start + 1..end].to_string());
    }
    None
}

fn min_priority_for_alerts(alerts: &[&Value]) -> i32 {
    alerts
        .iter()
        .map(|alert| severity_to_priority(&alert_severity(alert)))
        .min()
        .unwrap_or(3)
}

fn task_target_key(alert: &Value) -> String {
    let manifest = alert_manifest_path(alert);
    if manifest.is_empty() {
        let ecosystem = alert_ecosystem(alert);
        if ecosystem.is_empty() {
            "unknown".to_string()
        } else {
            ecosystem
        }
    } else {
        manifest
    }
}

fn alert_number(alert: &Value) -> i64 {
    alert["number"].as_i64().unwrap_or_default()
}

fn alert_state(alert: &Value) -> String {
    alert["state"].as_str().unwrap_or("open").to_string()
}

fn alert_severity(alert: &Value) -> String {
    alert["security_advisory"]["severity"]
        .as_str()
        .or_else(|| alert["security_vulnerability"]["severity"].as_str())
        .unwrap_or("low")
        .to_string()
}

fn alert_manifest_path(alert: &Value) -> String {
    alert["dependency"]["manifest_path"]
        .as_str()
        .unwrap_or("unknown")
        .to_string()
}

fn alert_ecosystem(alert: &Value) -> String {
    alert["dependency"]["package"]["ecosystem"]
        .as_str()
        .or_else(|| alert["security_vulnerability"]["package"]["ecosystem"].as_str())
        .unwrap_or("unknown")
        .to_string()
}

fn alert_package_name(alert: &Value) -> String {
    alert["dependency"]["package"]["name"]
        .as_str()
        .or_else(|| alert["security_vulnerability"]["package"]["name"].as_str())
        .unwrap_or("unknown")
        .to_string()
}

fn dependabot_alert_title(alert: &Value) -> String {
    let number = alert_number(alert);
    let package = alert_package_name(alert);
    let advisory = alert["security_advisory"]["ghsa_id"]
        .as_str()
        .unwrap_or("dependabot-alert");
    format!("[Dependabot] {advisory} in {package} #{number}")
}

fn short_key(identifier: &str) -> String {
    if let Some(index) = identifier.find('-') {
        identifier[..identifier.len().min(index + 7)].to_string()
    } else {
        identifier[..identifier.len().min(6)].to_string()
    }
}

fn severity_to_priority(severity: &str) -> i32 {
    match severity.to_lowercase().as_str() {
        "critical" => 0,
        "high" => 1,
        "medium" => 2,
        _ => 3,
    }
}

fn priority_to_u8(priority: i32) -> Result<u8, KanbusError> {
    u8::try_from(priority)
        .map_err(|_| KanbusError::IssueOperation(format!("invalid priority '{priority}'")))
}

fn metadata_marker_alert(repository: &str, alert_number: i64) -> String {
    format!("kanbus-gh-alert:dependabot|{repository}|{alert_number}")
}

fn metadata_marker_target(repository: &str, target_key: &str) -> String {
    format!("kanbus-gh-target:dependabot|{repository}|{target_key}")
}

fn append_marker(description: &str, marker: &str) -> String {
    format!("{description}\n\n<!-- {marker} -->")
}

fn find_marker_value(description: &str, prefix: &str) -> Option<String> {
    for line in description.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("<!-- ") && trimmed.ends_with(" -->") {
            let inner = trimmed
                .trim_start_matches("<!-- ")
                .trim_end_matches(" -->")
                .trim();
            if let Some(rest) = inner.strip_prefix(prefix) {
                return Some(rest.to_string());
            }
        }
    }
    None
}

fn build_beads_alert_index(issues: &[IssueData]) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for issue in issues {
        if let Some(rest) = find_marker_value(&issue.description, "kanbus-gh-alert:dependabot|") {
            let parts: Vec<&str> = rest.split('|').collect();
            if parts.len() == 2 {
                let key = format!("{}#{}", parts[0], parts[1]);
                index.insert(key, issue.identifier.clone());
            }
        }
    }
    index
}

fn build_beads_task_index(issues: &[IssueData]) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for issue in issues {
        if issue.issue_type != "task" {
            continue;
        }
        if let Some(rest) = find_marker_value(&issue.description, "kanbus-gh-target:dependabot|") {
            let parts: Vec<&str> = rest.split('|').collect();
            if parts.len() == 2 {
                index.insert(parts[1].to_string(), issue.identifier.clone());
            }
        }
    }
    index
}

fn resolve_beads_initiative(
    root: &Path,
    issues: &[IssueData],
    dry_run: bool,
) -> Result<String, KanbusError> {
    if let Some(existing) = latest_beads_match(issues, |issue| {
        issue.issue_type == "initiative"
            && issue.title == GITHUB_SECURITY_INITIATIVE_TITLE
            && issue.labels.iter().any(|label| label == "github")
    })
    .or_else(|| {
        latest_beads_match(issues, |issue| {
            issue.issue_type == "initiative" && issue.title == GITHUB_SECURITY_INITIATIVE_TITLE
        })
    }) {
        return Ok(existing);
    }
    println!("created  [initiative]  \"{GITHUB_SECURITY_INITIATIVE_TITLE}\"");
    if dry_run {
        return Ok("would-create-initiative".to_string());
    }
    let created = create_beads_issue(
        root,
        GITHUB_SECURITY_INITIATIVE_TITLE,
        Some("initiative"),
        Some(1),
        None,
        None,
        Some("Track remediation of GitHub security findings."),
    )?;
    let add_labels: Vec<String> = Vec::new();
    let remove_labels: Vec<String> = Vec::new();
    update_beads_issue(
        root,
        &created.identifier,
        Some("open"),
        Some(1),
        Some(GITHUB_SECURITY_INITIATIVE_TITLE),
        Some("Track remediation of GitHub security findings."),
        None,
        &add_labels,
        &remove_labels,
        Some("security,github"),
    )?;
    Ok(created.identifier)
}

fn resolve_beads_epic(
    root: &Path,
    issues: &[IssueData],
    configured_id: Option<&str>,
    initiative_id: &str,
    dry_run: bool,
) -> Result<String, KanbusError> {
    if let Some(id) = configured_id {
        if issues.iter().any(|issue| issue.identifier == id) {
            return Ok(id.to_string());
        }
    }
    if let Some(existing) = latest_beads_match(issues, |issue| {
        issue.issue_type == "epic"
            && issue.title == GITHUB_DEPENDABOT_EPIC_TITLE
            && issue.labels.iter().any(|label| label == "dependabot")
    })
    .or_else(|| {
        latest_beads_match(issues, |issue| {
            issue.issue_type == "epic" && issue.title == GITHUB_DEPENDABOT_EPIC_TITLE
        })
    }) {
        return Ok(existing);
    }
    println!("created  [epic    ]  \"{GITHUB_DEPENDABOT_EPIC_TITLE}\"");
    if dry_run {
        return Ok("would-create-epic".to_string());
    }
    let created = create_beads_issue(
        root,
        GITHUB_DEPENDABOT_EPIC_TITLE,
        Some("epic"),
        Some(1),
        None,
        Some(initiative_id),
        Some("Dependabot alerts imported from GitHub Security."),
    )?;
    let add_labels: Vec<String> = Vec::new();
    let remove_labels: Vec<String> = Vec::new();
    update_beads_issue(
        root,
        &created.identifier,
        Some("open"),
        Some(1),
        Some(GITHUB_DEPENDABOT_EPIC_TITLE),
        Some("Dependabot alerts imported from GitHub Security."),
        None,
        &add_labels,
        &remove_labels,
        Some("security,github,dependabot"),
    )?;
    Ok(created.identifier)
}

fn latest_beads_match(
    issues: &[IssueData],
    predicate: impl Fn(&IssueData) -> bool,
) -> Option<String> {
    issues
        .iter()
        .filter(|issue| predicate(issue))
        .max_by_key(|issue| issue.updated_at)
        .map(|issue| issue.identifier.clone())
}

fn resolve_beads_task(
    root: &Path,
    repository: &str,
    target_key: &str,
    parent_epic: &str,
    priority: i32,
    dry_run: bool,
    task_index: &mut BTreeMap<String, String>,
) -> Result<String, KanbusError> {
    if let Some(existing) = task_index.get(target_key) {
        if !dry_run {
            let title = format!("{repository}:{target_key}");
            let description = append_marker(
                &format!("Dependabot alerts for `{target_key}`."),
                &metadata_marker_target(repository, target_key),
            );
            let add_labels: Vec<String> = Vec::new();
            let remove_labels: Vec<String> = Vec::new();
            update_beads_issue(
                root,
                existing,
                Some("open"),
                Some(priority_to_u8(priority)?),
                Some(&title),
                Some(&description),
                None,
                &add_labels,
                &remove_labels,
                Some("security,github,dependabot"),
            )?;
        }
        return Ok(existing.clone());
    }
    let title = format!("{repository}:{target_key}");
    println!("created  [task    ]  \"{title}\"");
    if dry_run {
        let synthetic = format!("would-create-task-{target_key}");
        task_index.insert(target_key.to_string(), synthetic.clone());
        return Ok(synthetic);
    }
    let description = append_marker(
        &format!("Dependabot alerts for `{target_key}`."),
        &metadata_marker_target(repository, target_key),
    );
    let created = create_beads_issue(
        root,
        &title,
        Some("task"),
        Some(priority_to_u8(priority)?),
        None,
        Some(parent_epic),
        Some(&description),
    )?;
    let add_labels: Vec<String> = Vec::new();
    let remove_labels: Vec<String> = Vec::new();
    update_beads_issue(
        root,
        &created.identifier,
        Some("open"),
        Some(priority_to_u8(priority)?),
        Some(&title),
        Some(&description),
        None,
        &add_labels,
        &remove_labels,
        Some("security,github,dependabot"),
    )?;
    task_index.insert(target_key.to_string(), created.identifier.clone());
    Ok(created.identifier)
}

fn map_dependabot_to_beads_description(alert: &Value, repo: &str) -> String {
    let number = alert_number(alert);
    let package_name = alert_package_name(alert);
    let severity = alert_severity(alert);
    let state = alert_state(alert);
    let advisory_summary = alert["security_advisory"]["summary"]
        .as_str()
        .unwrap_or("Dependabot alert")
        .to_string();
    let advisory_description = alert["security_advisory"]["description"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let html_url = alert["html_url"].as_str().unwrap_or("").to_string();
    let manifest_path = alert_manifest_path(alert);
    let ecosystem = alert_ecosystem(alert);

    let description = format!(
        "## {advisory_summary}\n\n\
         **Provider:** GitHub Dependabot\n\
         **Repository:** `{repo}`\n\
         **Alert Number:** {number}\n\
         **Severity:** {severity}\n\
         **State:** {state}\n\
         **Package:** `{package_name}`\n\
         **Ecosystem:** `{ecosystem}`\n\
         **Manifest:** `{manifest_path}`\n\n\
         ### Advisory\n\
         {advisory_description}\n\n\
         ### Reference\n\
         - {html_url}"
    );

    append_marker(&description, &metadata_marker_alert(repo, number))
}

fn detect_repo_from_git(root: &Path) -> Option<String> {
    let output = std::process::Command::new("git")
        .args(["remote", "get-url", "origin"])
        .current_dir(root)
        .output()
        .ok()?;
    let remote = String::from_utf8(output.stdout).ok()?;
    extract_repo_slug(remote.trim())
}

fn extract_repo_slug(remote: &str) -> Option<String> {
    if let Some(rest) = remote.strip_prefix("https://github.com/") {
        return Some(rest.trim_end_matches(".git").to_string());
    }
    if let Some(rest) = remote.strip_prefix("git@github.com:") {
        return Some(rest.trim_end_matches(".git").to_string());
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_github_remote_slug() {
        assert_eq!(
            extract_repo_slug("https://github.com/AnthusAI/Kanbus.git"),
            Some("AnthusAI/Kanbus".to_string())
        );
        assert_eq!(
            extract_repo_slug("git@github.com:AnthusAI/Kanbus.git"),
            Some("AnthusAI/Kanbus".to_string())
        );
        assert_eq!(extract_repo_slug("ssh://gitlab.com/foo/bar.git"), None);
    }

    #[test]
    fn parses_next_link_header() {
        let header =
            "<https://api.github.com/foo?page=2>; rel=\"next\", <https://api.github.com/foo?page=3>; rel=\"last\"";
        assert_eq!(
            parse_next_link(Some(header)),
            Some("https://api.github.com/foo?page=2".to_string())
        );
        assert_eq!(
            parse_next_link(Some("<https://api.github.com/foo?page=3>; rel=\"last\"")),
            None
        );
    }

    #[test]
    fn maps_severity_to_priority() {
        assert_eq!(severity_to_priority("critical"), 0);
        assert_eq!(severity_to_priority("high"), 1);
        assert_eq!(severity_to_priority("medium"), 2);
        assert_eq!(severity_to_priority("low"), 3);
        assert_eq!(severity_to_priority("unknown"), 3);
    }
}
