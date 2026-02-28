//! Snyk vulnerability synchronization support.
//!
//! Pulls vulnerabilities from the Snyk REST API and creates/updates Kanbus bug
//! issues under a configured parent epic.  Secrets are read from the environment
//! variable SNYK_TOKEN (OAuth bearer token or legacy API key).
//!
//! Hierarchy created:
//!   epic  "Snyk Vulnerabilities"
//!     task  "<repo>:<manifest-file>"  (one per affected file)
//!       sub-task  "[Snyk] KEY in pkg@version"  (one per vulnerability)

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;

use chrono::Utc;
use serde_json::Value;

use crate::error::KanbusError;
use crate::file_io::load_project_directory;
use crate::ids::{generate_issue_identifier, IssueIdentifierRequest};
use crate::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use crate::models::{IssueData, SnykConfiguration};

const SNYK_API_BASE: &str = "https://api.snyk.io";
const SNYK_API_VERSION: &str = "2025-11-05";
const SNYK_INITIATIVE_TITLE: &str = "Snyk Vulnerability Remediation";
const SNYK_DEP_EPIC_TITLE: &str = "Snyk Dependency Vulnerabilities";
const SNYK_CODE_EPIC_TITLE: &str = "Snyk Code Vulnerabilities";
type SourceLocation = (String, Option<i64>, Option<i64>, Option<i64>, Option<i64>);

struct SnykEpicOptions {
    include_dependency: bool,
    include_code: bool,
    dependency_priority: Option<i32>,
    code_priority: Option<i32>,
}

struct SnykContext<'a> {
    issues_dir: &'a Path,
    project_key: &'a str,
    dry_run: bool,
    all_existing: &'a mut HashSet<String>,
}

/// Result of a Snyk pull operation.
#[derive(Debug)]
pub struct SnykPullResult {
    pub pulled: usize,
    pub updated: usize,
    pub skipped: usize,
}

/// Pull vulnerabilities from Snyk and create/update Kanbus issues.
///
/// Creates the hierarchy: epic → task-per-file → sub-task-per-vulnerability.
pub fn pull_from_snyk(
    root: &Path,
    snyk_config: &SnykConfiguration,
    project_key: &str,
    dry_run: bool,
) -> Result<SnykPullResult, KanbusError> {
    let token = std::env::var("SNYK_TOKEN").map_err(|_| {
        KanbusError::Configuration("SNYK_TOKEN environment variable is not set".to_string())
    })?;

    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");

    if !issues_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "issues directory does not exist".to_string(),
        ));
    }

    let min_priority = severity_to_priority(&snyk_config.min_severity);

    // Resolve repo filter: use config value or auto-detect from git remote
    let repo_filter = snyk_config
        .repo
        .clone()
        .or_else(|| detect_repo_from_git(root));

    // Fetch projects map: project_id → target_file name (filtered to this repo)
    let project_map = fetch_snyk_projects(&snyk_config.org_id, &token, repo_filter.as_deref())?;

    // Fetch all vulnerabilities
    let issue_types = ["package_vulnerability", "code"];
    let vulns = fetch_all_snyk_issues(&snyk_config.org_id, &token, min_priority, &issue_types)?;

    if std::env::var("KANBUS_SNYK_DEBUG").ok().as_deref() == Some("1") {
        println!(
            "debug: repo_filter={:?} projects={} issues={}",
            repo_filter,
            project_map.len(),
            vulns.len()
        );
        if let Some((id, target)) = project_map.iter().next() {
            println!("debug: sample_project_id={} target_file={}", id, target);
        }
        if let Some(issue) = vulns.first() {
            let scan_id = issue["relationships"]["scan_item"]["data"]["id"]
                .as_str()
                .unwrap_or("");
            let key = issue["attributes"]["key"].as_str().unwrap_or("");
            println!("debug: sample_issue_key={} scan_item_id={}", key, scan_id);
        }
    }

    // Fetch enrichment data (fixedIn, description, cvssScore, etc.) from v1 API
    // per-project, keyed by snyk_key → enrichment map
    let enrichment = fetch_v1_enrichment(
        &snyk_config.org_id,
        &token,
        project_map.keys().cloned().collect(),
    )?;

    // Resolve or auto-create the parent epic(s) after we know which categories exist.
    let mut all_existing = list_issue_identifiers(&issues_dir)?;

    // Build indexes for idempotency
    let snyk_key_index = build_snyk_key_index(&all_existing, &issues_dir);
    let file_task_index = build_file_task_index(&all_existing, &issues_dir);

    // Group vulnerabilities by target_file, deduplicating by (project_id, key).
    let mut file_to_vulns: BTreeMap<(String, String), Vec<&Value>> = BTreeMap::new();
    let mut has_code = false;
    let mut has_dependency = false;
    let mut category_priority: HashMap<String, i32> = HashMap::new();
    let mut seen_proj_key: HashMap<String, bool> = HashMap::new();
    for vuln in &vulns {
        let proj_id = vuln["relationships"]["scan_item"]["data"]["id"]
            .as_str()
            .unwrap_or("");
        let target_file = match project_map.get(proj_id) {
            Some(f) => f.clone(),
            None => continue, // skip issues not in filtered project set
        };
        let issue_type = vuln["attributes"]["type"]
            .as_str()
            .unwrap_or("package_vulnerability");
        let category = if issue_type == "code" {
            has_code = true;
            "code"
        } else {
            has_dependency = true;
            "dependency"
        };
        let sev = vuln["attributes"]["effective_severity_level"]
            .as_str()
            .unwrap_or("low");
        let priority = severity_to_priority(sev);
        category_priority
            .entry(category.to_string())
            .and_modify(|current| {
                if priority < *current {
                    *current = priority;
                }
            })
            .or_insert(priority);
        let key = vuln["attributes"]["key"].as_str().unwrap_or("");
        let dedup_key = format!("{proj_id}:{key}");
        if seen_proj_key.insert(dedup_key, true).is_some() {
            continue; // duplicate (project_id, key) pair
        }
        file_to_vulns
            .entry((category.to_string(), target_file))
            .or_default()
            .push(vuln);
    }

    let mut ctx = SnykContext {
        issues_dir: &issues_dir,
        project_key,
        dry_run,
        all_existing: &mut all_existing,
    };
    let epic_ids = resolve_snyk_epics(
        &mut ctx,
        snyk_config.parent_epic.as_deref(),
        &SnykEpicOptions {
            include_dependency: has_dependency,
            include_code: has_code,
            dependency_priority: category_priority.get("dependency").cloned(),
            code_priority: category_priority.get("code").cloned(),
        },
    )?;

    let mut pulled = 0usize;
    let mut updated = 0usize;
    let skipped = 0usize;

    for ((category, target_file), file_vulns) in &file_to_vulns {
        let epic_id = epic_ids
            .get(category)
            .cloned()
            .or_else(|| epic_ids.get("dependency").cloned())
            .unwrap_or_else(|| epic_ids.values().next().cloned().unwrap_or_default());
        // Highest priority (lowest number) among this file's vulnerabilities
        let file_priority = file_vulns
            .iter()
            .map(|v| {
                let sev = v["attributes"]["effective_severity_level"]
                    .as_str()
                    .unwrap_or("low");
                severity_to_priority(sev)
            })
            .min()
            .unwrap_or(3);

        // Resolve or create a task for this file
        let task_id = resolve_file_task(
            &issues_dir,
            project_key,
            target_file,
            category,
            &FileTaskContext {
                epic_id: &epic_id,
                priority: file_priority,
                dry_run,
            },
            &file_task_index,
            &mut all_existing,
        )?;

        // Create/update sub-tasks for each vulnerability in this file
        for vuln in file_vulns {
            let snyk_key = vuln_key(vuln);

            let existing_kanbus_id = snyk_key_index.get(&snyk_key);
            let (kanbus_id, action) = if let Some(id) = existing_kanbus_id {
                (id.clone(), "updated")
            } else {
                let request = IssueIdentifierRequest {
                    title: vuln_title(vuln),
                    existing_ids: all_existing.clone(),
                    prefix: project_key.to_string(),
                };
                let result = generate_issue_identifier(&request)?;
                let new_id = result.identifier.clone();
                all_existing.insert(new_id.clone());
                (new_id, "pulled ")
            };

            let v1_data = enrichment.get(&snyk_key);
            let mut issue =
                map_snyk_to_kanbus(vuln, &Some(task_id.clone()), v1_data, target_file, root)?;
            issue.identifier = kanbus_id.clone();

            // Preserve created_at for updates
            let issue_path = issue_path_for_identifier(&issues_dir, &kanbus_id);
            if action == "updated" {
                if let Ok(existing) = read_issue_from_file(&issue_path) {
                    issue.created_at = existing.created_at;
                }
            }

            let short_key = &kanbus_id[..kanbus_id
                .len()
                .min(kanbus_id.find('-').map_or(6, |i| i + 7))];
            let severity = vuln["attributes"]["effective_severity_level"]
                .as_str()
                .unwrap_or("?");
            println!(
                "{action}  [{severity:<8}]  {short_key:<14}  \"{}\"",
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

    Ok(SnykPullResult {
        pulled,
        updated,
        skipped,
    })
}

/// Resolve the parent epic ID, creating one if it doesn't exist.
fn resolve_parent_epic(
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

    let request = IssueIdentifierRequest {
        title: "Snyk Vulnerabilities".to_string(),
        existing_ids: all_existing.clone(),
        prefix: project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let epic_id = result.identifier.clone();
    all_existing.insert(epic_id.clone());

    let now = Utc::now();
    let epic = IssueData {
        identifier: epic_id.clone(),
        title: "Snyk Vulnerabilities".to_string(),
        description: "Security vulnerabilities imported from Snyk.".to_string(),
        issue_type: "epic".to_string(),
        status: "open".to_string(),
        priority: 1,
        assignee: None,
        creator: None,
        parent: None,
        labels: vec!["security".to_string(), "snyk".to_string()],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: BTreeMap::new(),
    };

    println!("created  [epic    ]  {epic_id:<14}  \"Snyk Vulnerabilities\"");

    if !dry_run {
        let epic_path = issue_path_for_identifier(issues_dir, &epic_id);
        write_issue_to_file(&epic, &epic_path)?;
    }

    Ok(epic_id)
}

fn resolve_snyk_epics(
    ctx: &mut SnykContext<'_>,
    configured_id: Option<&str>,
    options: &SnykEpicOptions,
) -> Result<HashMap<String, String>, KanbusError> {
    let mut epics = HashMap::new();
    if configured_id.is_some() {
        let epic_id = resolve_parent_epic(
            ctx.issues_dir,
            ctx.project_key,
            configured_id,
            ctx.dry_run,
            ctx.all_existing,
        )?;
        if options.include_dependency {
            epics.insert("dependency".to_string(), epic_id.clone());
        }
        if options.include_code {
            epics.insert("code".to_string(), epic_id.clone());
        }
        return Ok(epics);
    }

    if !options.include_dependency && !options.include_code {
        return Ok(epics);
    }

    let initiative_id = resolve_snyk_initiative(
        ctx.issues_dir,
        ctx.project_key,
        ctx.dry_run,
        ctx.all_existing,
    )?;
    if options.include_dependency {
        let dep_epic = resolve_snyk_epic(
            ctx,
            &initiative_id,
            SNYK_DEP_EPIC_TITLE,
            "dependency",
            options.dependency_priority.unwrap_or(2),
        )?;
        epics.insert("dependency".to_string(), dep_epic);
    }
    if options.include_code {
        let code_epic = resolve_snyk_epic(
            ctx,
            &initiative_id,
            SNYK_CODE_EPIC_TITLE,
            "code",
            options.code_priority.unwrap_or(2),
        )?;
        epics.insert("code".to_string(), code_epic);
    }
    Ok(epics)
}

fn resolve_snyk_initiative(
    issues_dir: &Path,
    project_key: &str,
    dry_run: bool,
    all_existing: &mut HashSet<String>,
) -> Result<String, KanbusError> {
    if let Some(id) = find_existing_snyk_initiative(issues_dir, all_existing) {
        return Ok(id);
    }

    let request = IssueIdentifierRequest {
        title: SNYK_INITIATIVE_TITLE.to_string(),
        existing_ids: all_existing.clone(),
        prefix: project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let initiative_id = result.identifier.clone();
    all_existing.insert(initiative_id.clone());

    let now = Utc::now();
    let initiative = IssueData {
        identifier: initiative_id.clone(),
        title: SNYK_INITIATIVE_TITLE.to_string(),
        description: "Track remediation of Snyk vulnerabilities.".to_string(),
        issue_type: "initiative".to_string(),
        status: "open".to_string(),
        priority: 1,
        assignee: None,
        creator: None,
        parent: None,
        labels: vec!["security".to_string(), "snyk".to_string()],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: BTreeMap::new(),
    };

    println!("created  [initiative]  {initiative_id:<14}  \"{SNYK_INITIATIVE_TITLE}\"");

    if !dry_run {
        let path = issue_path_for_identifier(issues_dir, &initiative_id);
        write_issue_to_file(&initiative, &path)?;
    }

    Ok(initiative_id)
}

fn resolve_snyk_epic(
    ctx: &mut SnykContext<'_>,
    parent_initiative: &str,
    title: &str,
    category: &str,
    priority: i32,
) -> Result<String, KanbusError> {
    if let Some(id) =
        find_existing_snyk_epic(ctx.issues_dir, ctx.all_existing, title, parent_initiative)
    {
        let path = issue_path_for_identifier(ctx.issues_dir, &id);
        if let Ok(mut issue) = read_issue_from_file(&path) {
            if issue.priority != priority {
                issue.priority = priority;
                issue.updated_at = Utc::now();
                if !ctx.dry_run {
                    write_issue_to_file(&issue, &path)?;
                }
            }
        }
        return Ok(id);
    }

    let request = IssueIdentifierRequest {
        title: title.to_string(),
        existing_ids: ctx.all_existing.clone(),
        prefix: ctx.project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let epic_id = result.identifier.clone();
    ctx.all_existing.insert(epic_id.clone());

    let now = Utc::now();
    let mut custom = BTreeMap::new();
    custom.insert(
        "snyk_category".to_string(),
        serde_json::Value::String(category.to_string()),
    );
    let epic = IssueData {
        identifier: epic_id.clone(),
        title: title.to_string(),
        description: "Security vulnerabilities imported from Snyk.".to_string(),
        issue_type: "epic".to_string(),
        status: "open".to_string(),
        priority,
        assignee: None,
        creator: None,
        parent: Some(parent_initiative.to_string()),
        labels: vec![
            "security".to_string(),
            "snyk".to_string(),
            category.to_string(),
        ],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom,
    };

    println!("created  [epic    ]  {epic_id:<14}  \"{title}\"");

    if !ctx.dry_run {
        let epic_path = issue_path_for_identifier(ctx.issues_dir, &epic_id);
        write_issue_to_file(&epic, &epic_path)?;
    }

    Ok(epic_id)
}

fn find_existing_snyk_initiative(
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
            if issue.title != SNYK_INITIATIVE_TITLE {
                continue;
            }
            if !issue.labels.iter().any(|l| l == "snyk") {
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

fn find_existing_snyk_epic(
    issues_dir: &Path,
    all_existing: &HashSet<String>,
    title: &str,
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
            if issue.title != title {
                continue;
            }
            if !issue.labels.iter().any(|l| l == "snyk") {
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

/// Resolve or create a task for a manifest file under the epic.
struct FileTaskContext<'a> {
    epic_id: &'a str,
    priority: i32,
    dry_run: bool,
}

fn resolve_file_task(
    issues_dir: &Path,
    project_key: &str,
    target_file: &str,
    category: &str,
    ctx: &FileTaskContext<'_>,
    file_task_index: &BTreeMap<(String, String), String>,
    all_existing: &mut HashSet<String>,
) -> Result<String, KanbusError> {
    if let Some(id) = file_task_index.get(&(category.to_string(), target_file.to_string())) {
        if !ctx.dry_run {
            let task_path = issue_path_for_identifier(issues_dir, id);
            if let Ok(mut issue) = read_issue_from_file(&task_path) {
                if issue.issue_type == "task" {
                    let mut changed = false;
                    if issue.parent.as_deref() != Some(ctx.epic_id) {
                        issue.parent = Some(ctx.epic_id.to_string());
                        changed = true;
                    }
                    if issue.priority != ctx.priority {
                        issue.priority = ctx.priority;
                        changed = true;
                    }
                    let target = serde_json::Value::String(target_file.to_string());
                    if issue.custom.get("snyk_target_file") != Some(&target) {
                        issue.custom.insert("snyk_target_file".to_string(), target);
                        changed = true;
                    }
                    let cat = serde_json::Value::String(category.to_string());
                    if issue.custom.get("snyk_category") != Some(&cat) {
                        issue.custom.insert("snyk_category".to_string(), cat);
                        changed = true;
                    }
                    if !issue.labels.iter().any(|l| l == "snyk") {
                        issue.labels.push("snyk".to_string());
                        changed = true;
                    }
                    if !issue.labels.iter().any(|l| l == "security") {
                        issue.labels.push("security".to_string());
                        changed = true;
                    }
                    if changed {
                        issue.updated_at = Utc::now();
                        write_issue_to_file(&issue, &task_path)?;
                        let short_key = &id[..id.len().min(id.find('-').map_or(6, |i| i + 7))];
                        println!("updated  [task    ]  {short_key:<14}  \"{target_file}\"");
                    }
                }
            }
        }
        return Ok(id.clone());
    }

    let request = IssueIdentifierRequest {
        title: target_file.to_string(),
        existing_ids: all_existing.clone(),
        prefix: project_key.to_string(),
    };
    let result = generate_issue_identifier(&request)?;
    let task_id = result.identifier.clone();
    all_existing.insert(task_id.clone());

    let now = Utc::now();
    let mut custom: BTreeMap<String, serde_json::Value> = BTreeMap::new();
    custom.insert(
        "snyk_target_file".to_string(),
        serde_json::Value::String(target_file.to_string()),
    );
    custom.insert(
        "snyk_category".to_string(),
        serde_json::Value::String(category.to_string()),
    );

    let task = IssueData {
        identifier: task_id.clone(),
        title: target_file.to_string(),
        description: format!("Snyk vulnerabilities found in `{target_file}`."),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: ctx.priority,
        assignee: None,
        creator: None,
        parent: Some(ctx.epic_id.to_string()),
        labels: vec!["security".to_string(), "snyk".to_string()],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom,
    };

    let short_key = &task_id[..task_id.len().min(task_id.find('-').map_or(6, |i| i + 7))];
    println!("created  [task    ]  {short_key:<14}  \"{target_file}\"");

    if !ctx.dry_run {
        let task_path = issue_path_for_identifier(issues_dir, &task_id);
        write_issue_to_file(&task, &task_path)?;
    }

    Ok(task_id)
}

/// Detect the GitHub repo slug from git remote origin URL.
/// Returns e.g. "AnthusAI/Plexus" from "https://github.com/AnthusAI/Plexus.git".
fn detect_repo_from_git(root: &Path) -> Option<String> {
    let output = std::process::Command::new("git")
        .args(["remote", "get-url", "origin"])
        .current_dir(root)
        .output()
        .ok()?;
    let url = String::from_utf8(output.stdout).ok()?;
    let url = url.trim();
    // Handle https://github.com/Org/Repo.git and git@github.com:Org/Repo.git
    let slug = if let Some(rest) = url.strip_prefix("https://github.com/") {
        rest.trim_end_matches(".git").to_string()
    } else if let Some(rest) = url.strip_prefix("git@github.com:") {
        rest.trim_end_matches(".git").to_string()
    } else {
        return None;
    };
    Some(slug)
}

/// Fetch all projects for the org, returning a map of project_id → target_file.
/// If `repo_filter` is set, only includes projects whose name starts with
/// `"{repo_filter}:"` (Snyk project names are formatted as "Org/Repo:file/path").
fn fetch_snyk_projects(
    org_id: &str,
    token: &str,
    repo_filter: Option<&str>,
) -> Result<BTreeMap<String, String>, KanbusError> {
    let client = reqwest::blocking::Client::new();
    let mut map: BTreeMap<String, String> = BTreeMap::new();
    let prefix = repo_filter.map(|r| format!("{r}:"));

    let mut url = Some(format!(
        "{SNYK_API_BASE}/rest/orgs/{org_id}/projects?version={SNYK_API_VERSION}&limit=100"
    ));

    while let Some(current_url) = url {
        let response = client
            .get(&current_url)
            .bearer_auth(token)
            .header("Accept", "application/vnd.api+json")
            .send()
            .map_err(|e| KanbusError::IssueOperation(format!("Snyk request failed: {e}")))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            return Err(KanbusError::IssueOperation(format!(
                "Snyk projects API returned {status}: {body}"
            )));
        }

        let body: Value = response.json().map_err(|e| {
            KanbusError::IssueOperation(format!("Failed to parse Snyk projects response: {e}"))
        })?;

        if let Some(data) = body["data"].as_array() {
            for project in data {
                let id = project["id"].as_str().unwrap_or("").to_string();
                let name = project["attributes"]["name"].as_str().unwrap_or("");
                // Filter by repo if specified
                if let Some(ref p) = prefix {
                    let repo = p.trim_end_matches(':');
                    let matches_repo = name == repo || name.starts_with(p.as_str());
                    if std::env::var("KANBUS_SNYK_DEBUG").ok().as_deref() == Some("1")
                        && (name.starts_with(repo) || name == repo)
                    {
                        println!(
                            "debug: project name={:?} repo={:?} matches={}",
                            name, repo, matches_repo
                        );
                    }
                    if !matches_repo {
                        continue;
                    }
                }
                let target_file = project["attributes"]["target_file"]
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .or_else(|| project["attributes"]["name"].as_str())
                    .unwrap_or("")
                    .to_string();
                if std::env::var("KANBUS_SNYK_DEBUG").ok().as_deref() == Some("1")
                    && repo_filter == Some(name)
                {
                    println!(
                        "debug: base_project id='{}' target_file='{}'",
                        id, target_file
                    );
                }
                if !id.is_empty() && !target_file.is_empty() {
                    map.insert(id, target_file);
                }
            }
        }

        url = body["links"]["next"]
            .as_str()
            .map(|next| format!("{SNYK_API_BASE}{next}"));
    }

    Ok(map)
}

/// Fetch enrichment data from the Snyk v1 aggregated-issues API for a set of
/// projects.  Returns a map of snyk_key → JSON object with fields like
/// `fixedIn`, `title`, `description`, `cvssScore`, `exploitMaturity`, `priorityScore`.
fn fetch_v1_enrichment(
    org_id: &str,
    token: &str,
    project_ids: Vec<String>,
) -> Result<BTreeMap<String, Value>, KanbusError> {
    let client = reqwest::blocking::Client::new();
    let mut enrichment: BTreeMap<String, Value> = BTreeMap::new();

    for proj_id in &project_ids {
        let url =
            format!("{SNYK_API_BASE}/api/v1/org/{org_id}/project/{proj_id}/aggregated-issues");
        let response = client
            .post(&url)
            .bearer_auth(token)
            .header("Content-Type", "application/json")
            .json(&serde_json::json!({"filters": {}, "includeDescription": true}))
            .send()
            .map_err(|e| KanbusError::IssueOperation(format!("Snyk v1 request failed: {e}")))?;

        if !response.status().is_success() {
            // Non-fatal: skip this project if v1 call fails
            continue;
        }

        let body: Value = response.json().map_err(|e| {
            KanbusError::IssueOperation(format!("Failed to parse Snyk v1 response: {e}"))
        })?;

        if let Some(issues) = body["issues"].as_array() {
            for issue in issues {
                let key = issue["issueData"]["id"].as_str().unwrap_or("").to_string();
                if !key.is_empty() {
                    enrichment.insert(key, issue.clone());
                }
            }
        }
    }

    Ok(enrichment)
}

/// Fetch all issues from the Snyk REST API for an org, filtering to those at
/// or above `min_priority`.  Returns all occurrences (one per project), so the
/// same vulnerability key may appear multiple times if it affects multiple files.
fn fetch_all_snyk_issues(
    org_id: &str,
    token: &str,
    min_priority: i32,
    issue_types: &[&str],
) -> Result<Vec<Value>, KanbusError> {
    let mut all_issues: Vec<Value> = Vec::new();

    for issue_type in issue_types {
        match fetch_snyk_issues_for_type(org_id, token, min_priority, issue_type) {
            Ok(mut issues) => all_issues.append(&mut issues),
            Err(err) => {
                if *issue_type == "package_vulnerability" {
                    return Err(err);
                }
                eprintln!("warning: failed to fetch Snyk issues type '{issue_type}': {err}");
            }
        }
    }

    Ok(all_issues)
}

fn fetch_snyk_issues_for_type(
    org_id: &str,
    token: &str,
    min_priority: i32,
    issue_type: &str,
) -> Result<Vec<Value>, KanbusError> {
    let client = reqwest::blocking::Client::new();
    let mut all_issues: Vec<Value> = Vec::new();

    let mut url = Some(format!(
        "{SNYK_API_BASE}/rest/orgs/{org_id}/issues?version={SNYK_API_VERSION}&limit=100&type={issue_type}"
    ));

    while let Some(current_url) = url {
        let response = client
            .get(&current_url)
            .bearer_auth(token)
            .header("Accept", "application/vnd.api+json")
            .send()
            .map_err(|e| KanbusError::IssueOperation(format!("Snyk request failed: {e}")))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            return Err(KanbusError::IssueOperation(format!(
                "Snyk API returned {status}: {body}"
            )));
        }

        let body: Value = response.json().map_err(|e| {
            KanbusError::IssueOperation(format!("Failed to parse Snyk response: {e}"))
        })?;

        let data = body["data"].as_array().ok_or_else(|| {
            KanbusError::IssueOperation("Snyk response missing 'data'".to_string())
        })?;

        for issue in data {
            let key = issue["attributes"]["key"].as_str().unwrap_or("");
            if key.is_empty() {
                continue;
            }
            let sev = issue["attributes"]["effective_severity_level"]
                .as_str()
                .unwrap_or("low");
            let priority = severity_to_priority(sev);
            if priority <= min_priority {
                all_issues.push(issue.clone());
            }
        }

        url = body["links"]["next"]
            .as_str()
            .map(|next| format!("{SNYK_API_BASE}{next}"));
    }

    Ok(all_issues)
}

/// Build a map from snyk_key → kanbus identifier by scanning existing issue files.
fn build_snyk_key_index(
    existing_ids: &HashSet<String>,
    issues_dir: &Path,
) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for id in existing_ids {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if let Some(Value::String(snyk_key)) = issue.custom.get("snyk_key") {
                index.insert(snyk_key.clone(), id.clone());
            }
        }
    }
    index
}

/// Build a map from target_file → kanbus task identifier by scanning existing task files.
fn build_file_task_index(
    existing_ids: &HashSet<String>,
    issues_dir: &Path,
) -> BTreeMap<(String, String), String> {
    let mut index = BTreeMap::new();
    for id in existing_ids {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if issue.issue_type == "task" {
                if let Some(Value::String(target_file)) = issue.custom.get("snyk_target_file") {
                    let category = issue
                        .custom
                        .get("snyk_category")
                        .and_then(|v| v.as_str())
                        .unwrap_or("dependency")
                        .to_string();
                    index.insert((category, target_file.clone()), id.clone());
                }
            }
        }
    }
    index
}

fn vuln_key(issue: &Value) -> String {
    issue["attributes"]["key"]
        .as_str()
        .unwrap_or("")
        .to_string()
}

fn vuln_title(issue: &Value) -> String {
    let attrs = &issue["attributes"];
    let issue_type = attrs["type"].as_str().unwrap_or("package_vulnerability");
    if issue_type == "code" {
        let title = attrs["title"].as_str().unwrap_or("Snyk Code issue");
        return format!("[Snyk Code] {title}");
    }
    let key = attrs["key"].as_str().unwrap_or("unknown");
    let pkg = attrs["coordinates"][0]["representations"][0]["dependency"]["package_name"]
        .as_str()
        .unwrap_or("");
    if pkg.is_empty() {
        format!("[Snyk] {key}")
    } else {
        format!("[Snyk] {key} in {pkg}")
    }
}

fn extract_source_location(issue: &Value) -> Option<SourceLocation> {
    let coords = issue["attributes"]["coordinates"].as_array()?;
    for coord in coords {
        let reps = coord["representations"].as_array()?;
        if let Some(rep) = reps.iter().next() {
            let loc = rep
                .get("source_location")
                .or_else(|| rep.get("sourceLocation"))?;
            let file = loc.get("file").and_then(|v| v.as_str())?.to_string();

            if let Some(region) = loc.get("region") {
                let start = region.get("start").unwrap_or(region);
                let end = region.get("end").unwrap_or(region);
                let start_line = start.get("line").and_then(|v| v.as_i64());
                let start_col = start.get("column").and_then(|v| v.as_i64());
                let end_line = end.get("line").and_then(|v| v.as_i64());
                let end_col = end.get("column").and_then(|v| v.as_i64());
                return Some((file, start_line, start_col, end_line, end_col));
            }

            let line = loc.get("line").and_then(|v| v.as_i64());
            let column = loc
                .get("column")
                .or_else(|| loc.get("col"))
                .and_then(|v| v.as_i64());
            return Some((file, line, column, None, None));
        }
    }
    None
}

fn extract_classes(issue: &Value) -> Vec<String> {
    issue["attributes"]["classes"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| {
                    if let Some(s) = v.as_str() {
                        return Some(s.to_string());
                    }
                    let id = v.get("id").and_then(|v| v.as_str());
                    let source = v.get("source").and_then(|v| v.as_str());
                    if let (Some(source), Some(id)) = (source, id) {
                        Some(format!("{source}-{id}"))
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_default()
}

const SNIPPET_CONTEXT: i64 = 2;
const MAX_SNIPPET_LINES: i64 = 25;

fn build_snippet(
    repo_root: &Path,
    file: &str,
    start_line: Option<i64>,
    end_line: Option<i64>,
) -> Option<String> {
    let start_line = start_line?;
    let end_line = end_line.unwrap_or(start_line);
    if start_line <= 0 || end_line <= 0 {
        return None;
    }

    let path = repo_root.join(file);
    let content = std::fs::read_to_string(path).ok()?;
    let lines: Vec<&str> = content.lines().collect();
    if lines.is_empty() {
        return None;
    }

    let total = lines.len() as i64;
    let mut snippet_start = (start_line - SNIPPET_CONTEXT).max(1);
    let mut snippet_end = (end_line + SNIPPET_CONTEXT).min(total);
    if snippet_end - snippet_start + 1 > MAX_SNIPPET_LINES {
        snippet_start = (start_line - SNIPPET_CONTEXT).max(1);
        snippet_end = (snippet_start + MAX_SNIPPET_LINES - 1).min(total);
    }

    let mut body = String::new();
    for line_no in snippet_start..=snippet_end {
        let idx = (line_no - 1) as usize;
        if let Some(line) = lines.get(idx) {
            body.push_str(&format!("{:>4} | {}\n", line_no, line));
        }
    }

    Some(format!(
        "### Snippet ({file}:{snippet_start}-{snippet_end})\n```\n{body}```\n\n"
    ))
}

/// Map a Snyk issue JSON object to a Kanbus IssueData sub-task.
fn map_snyk_to_kanbus(
    issue: &Value,
    parent_task_id: &Option<String>,
    v1: Option<&Value>,
    target_file: &str,
    repo_root: &Path,
) -> Result<IssueData, KanbusError> {
    let attrs = &issue["attributes"];
    let issue_type = attrs["type"].as_str().unwrap_or("package_vulnerability");

    let snyk_key = attrs["key"].as_str().unwrap_or("").to_string();
    let severity = attrs["effective_severity_level"]
        .as_str()
        .unwrap_or("low")
        .to_string();
    let priority = severity_to_priority(&severity);

    let description;
    let title;
    let mut custom: BTreeMap<String, serde_json::Value> = BTreeMap::new();

    custom.insert(
        "snyk_key".to_string(),
        serde_json::Value::String(snyk_key.clone()),
    );
    custom.insert(
        "snyk_severity".to_string(),
        serde_json::Value::String(severity.clone()),
    );
    custom.insert(
        "snyk_type".to_string(),
        serde_json::Value::String(issue_type.to_string()),
    );

    if issue_type == "code" {
        let issue_title = attrs["title"].as_str().unwrap_or(&snyk_key);
        let description_text = attrs["description"].as_str().unwrap_or("");
        let classes = extract_classes(issue);
        let class_line = if classes.is_empty() {
            String::new()
        } else {
            format!("**Classes:** {}\n", classes.join(", "))
        };
        let location = extract_source_location(issue);
        let (file_line, loc_line) = if let Some((file, line, col, end_line, end_col)) = &location {
            let mut loc = String::new();
            if let Some(line) = line {
                if let Some(col) = col {
                    if let (Some(end_line), Some(end_col)) = (end_line, end_col) {
                        loc = format!(
                            "**Location:** line {line}, column {col} to line {end_line}, column {end_col}\n"
                        );
                    } else {
                        loc = format!("**Location:** line {line}, column {col}\n");
                    }
                } else {
                    loc = format!("**Location:** line {line}\n");
                }
            }
            (format!("**File:** `{file}`\n"), loc)
        } else {
            (String::new(), String::new())
        };

        let snippet_block = if let Some((file, line, col, end_line, end_col)) = location {
            let file_path = file.clone();
            custom.insert(
                "snyk_file".to_string(),
                serde_json::Value::String(file_path.clone()),
            );
            if let Some(line) = line {
                custom.insert(
                    "snyk_line".to_string(),
                    serde_json::Value::Number(line.into()),
                );
            }
            if let Some(col) = col {
                custom.insert(
                    "snyk_column".to_string(),
                    serde_json::Value::Number(col.into()),
                );
            }
            if let Some(end_line) = end_line {
                custom.insert(
                    "snyk_end_line".to_string(),
                    serde_json::Value::Number(end_line.into()),
                );
            }
            if let Some(end_col) = end_col {
                custom.insert(
                    "snyk_end_column".to_string(),
                    serde_json::Value::Number(end_col.into()),
                );
            }
            build_snippet(repo_root, &file_path, line, end_line)
                .or_else(|| build_snippet(repo_root, &file_path, line, line))
                .unwrap_or_default()
        } else {
            String::new()
        };

        title = format!("[Snyk Code] {issue_title}");
        description = format!(
            "## {issue_title}\n\n\
             **Severity:** {severity}\n\
             **Project:** `{target_file}`\n\
             {file_line}\
             {loc_line}\
             {class_line}\
             {snippet_block}\
             **Issue Key:** {snyk_key}\n\n\
             {details}\
             **Fix:** Review and remediate in code.",
            details = if description_text.is_empty() {
                String::new()
            } else {
                format!("### Details\n{description_text}\n\n")
            }
        );
    } else {
        let pkg_name = attrs["coordinates"][0]["representations"][0]["dependency"]["package_name"]
            .as_str()
            .unwrap_or("");
        let pkg_version = attrs["coordinates"][0]["representations"][0]["dependency"]
            ["package_version"]
            .as_str()
            .unwrap_or("");

        // Prefer v1 human-readable title over key
        let vuln_title = v1
            .and_then(|v| v["issueData"]["title"].as_str())
            .unwrap_or(&snyk_key);

        title = if pkg_name.is_empty() {
            format!("[Snyk] {snyk_key}")
        } else {
            format!("[Snyk] {snyk_key} in {pkg_name}@{pkg_version}")
        };

        let cves: Vec<&str> = attrs["problems"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter(|p| p["source"].as_str() == Some("NVD"))
                    .filter_map(|p| p["id"].as_str())
                    .collect()
            })
            .unwrap_or_default();

        let cve_line = if cves.is_empty() {
            "No CVE assigned.".to_string()
        } else {
            cves.iter()
                .map(|cve| format!("- [{cve}](https://nvd.nist.gov/vuln/detail/{cve})"))
                .collect::<Vec<_>>()
                .join("\n")
        };

        let fixable = attrs["coordinates"][0]["is_fixable_snyk"]
            .as_bool()
            .unwrap_or(false);
        let upgradeable = attrs["coordinates"][0]["is_upgradeable"]
            .as_bool()
            .unwrap_or(false);
        let pinnable = attrs["coordinates"][0]["is_pinnable"]
            .as_bool()
            .unwrap_or(false);

        // Get exact fixed version from v1 if available
        let fixed_in: Vec<String> = v1
            .and_then(|v| v["fixInfo"]["fixedIn"].as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str())
                    .map(|s| s.to_string())
                    .collect()
            })
            .unwrap_or_default();

        let fix_advice = if !fixed_in.is_empty() {
            let versions = fixed_in.join(", ");
            if upgradeable {
                format!("**Fix:** Upgrade `{pkg_name}` to version {versions} or later.")
            } else {
                format!("**Fix:** Pin `{pkg_name}` to version {versions} or later.")
            }
        } else if upgradeable {
            format!("**Fix:** Upgrade `{pkg_name}` to a patched version.")
        } else if pinnable {
            format!("**Fix:** Pin `{pkg_name}` to a patched version.")
        } else if fixable {
            "**Fix:** Snyk fix available — run `snyk fix`.".to_string()
        } else {
            "**Fix:** No automatic fix available. Review manually.".to_string()
        };

        // Extra metadata from v1
        let cvss_score = v1
            .and_then(|v| v["issueData"]["cvssScore"].as_f64())
            .map(|s| format!("{s:.1}"))
            .unwrap_or_default();
        let exploit_maturity = v1
            .and_then(|v| v["issueData"]["exploitMaturity"].as_str())
            .unwrap_or_default();
        let priority_score = v1
            .and_then(|v| v["priorityScore"].as_i64())
            .map(|s| s.to_string())
            .unwrap_or_default();
        let v1_description = v1
            .and_then(|v| v["issueData"]["description"].as_str())
            .unwrap_or_default();

        let mut meta_lines = Vec::new();
        if !cvss_score.is_empty() {
            meta_lines.push(format!("**CVSS Score:** {cvss_score}"));
        }
        if !exploit_maturity.is_empty() && exploit_maturity != "no-known-exploit" {
            meta_lines.push(format!("**Exploit Maturity:** {exploit_maturity}"));
        }
        if !priority_score.is_empty() {
            meta_lines.push(format!("**Snyk Priority Score:** {priority_score}/1000"));
        }
        let meta_block = if meta_lines.is_empty() {
            String::new()
        } else {
            format!("{}\n\n", meta_lines.join("  \n"))
        };

        let detail_block = if v1_description.is_empty() {
            String::new()
        } else {
            format!("### Details\n{v1_description}\n\n")
        };

        let snyk_url = format!("https://security.snyk.io/vuln/{snyk_key}");

        description = format!(
            "## {vuln_title}\n\n\
             **Severity:** {severity}\n\
             **Package:** {pkg_name}@{pkg_version}\n\
             **File:** `{target_file}`\n\n\
             {meta_block}\
             ### CVEs\n{cve_line}\n\n\
             {fix_advice}\n\n\
             {detail_block}\
             ### Reference\n- [Snyk advisory]({snyk_url})"
        );
    }

    let now = Utc::now();

    Ok(IssueData {
        identifier: String::new(), // filled in by caller
        title,
        description,
        issue_type: "sub-task".to_string(),
        status: "open".to_string(),
        priority,
        assignee: None,
        creator: None,
        parent: parent_task_id.clone(),
        labels: vec!["security".to_string(), "snyk".to_string()],
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom,
    })
}

/// Map a Snyk severity string to a Kanbus priority integer.
/// critical=0, high=1, medium=2, low=3.
fn severity_to_priority(severity: &str) -> i32 {
    match severity.to_lowercase().as_str() {
        "critical" => 0,
        "high" => 1,
        "medium" => 2,
        _ => 3,
    }
}
