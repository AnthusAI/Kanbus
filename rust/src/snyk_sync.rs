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
const SNYK_API_VERSION: &str = "2024-10-15";

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
    let vulns = fetch_all_snyk_issues(&snyk_config.org_id, &token, min_priority)?;

    // Fetch enrichment data (fixedIn, description, cvssScore, etc.) from v1 API
    // per-project, keyed by snyk_key → enrichment map
    let enrichment = fetch_v1_enrichment(
        &snyk_config.org_id,
        &token,
        project_map.keys().cloned().collect(),
    )?;

    // Resolve or auto-create the parent epic
    let mut all_existing = list_issue_identifiers(&issues_dir)?;
    let epic_id = resolve_parent_epic(
        &issues_dir,
        project_key,
        snyk_config.parent_epic.as_deref(),
        dry_run,
        &mut all_existing,
    )?;

    // Build indexes for idempotency
    let snyk_key_index = build_snyk_key_index(&all_existing, &issues_dir);
    let file_task_index = build_file_task_index(&all_existing, &issues_dir);

    // Group vulnerabilities by target_file, deduplicating by (project_id, key).
    let mut file_to_vulns: BTreeMap<String, Vec<&Value>> = BTreeMap::new();
    let mut seen_proj_key: HashMap<String, bool> = HashMap::new();
    for vuln in &vulns {
        let proj_id = vuln["relationships"]["scan_item"]["data"]["id"]
            .as_str()
            .unwrap_or("");
        let target_file = match project_map.get(proj_id) {
            Some(f) => f.clone(),
            None => continue, // skip issues not in filtered project set
        };
        let key = vuln["attributes"]["key"].as_str().unwrap_or("");
        let dedup_key = format!("{proj_id}:{key}");
        if seen_proj_key.insert(dedup_key, true).is_some() {
            continue; // duplicate (project_id, key) pair
        }
        file_to_vulns.entry(target_file).or_default().push(vuln);
    }

    let mut pulled = 0usize;
    let mut updated = 0usize;
    let skipped = 0usize;

    for (target_file, file_vulns) in &file_to_vulns {
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
            let mut issue = map_snyk_to_kanbus(vuln, &Some(task_id.clone()), v1_data, target_file)?;
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
    ctx: &FileTaskContext<'_>,
    file_task_index: &BTreeMap<String, String>,
    all_existing: &mut HashSet<String>,
) -> Result<String, KanbusError> {
    if let Some(id) = file_task_index.get(target_file) {
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
                    if !name.starts_with(p.as_str()) {
                        continue;
                    }
                }
                let target_file = project["attributes"]["target_file"]
                    .as_str()
                    .or_else(|| project["attributes"]["name"].as_str())
                    .unwrap_or("")
                    .to_string();
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
) -> Result<Vec<Value>, KanbusError> {
    let client = reqwest::blocking::Client::new();
    let mut all_issues: Vec<Value> = Vec::new();

    let mut url = Some(format!(
        "{SNYK_API_BASE}/rest/orgs/{org_id}/issues?version={SNYK_API_VERSION}&limit=100"
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
) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for id in existing_ids {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if issue.issue_type == "task" {
                if let Some(Value::String(target_file)) = issue.custom.get("snyk_target_file") {
                    index.insert(target_file.clone(), id.clone());
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

/// Map a Snyk issue JSON object to a Kanbus IssueData sub-task.
fn map_snyk_to_kanbus(
    issue: &Value,
    parent_task_id: &Option<String>,
    v1: Option<&Value>,
    target_file: &str,
) -> Result<IssueData, KanbusError> {
    let attrs = &issue["attributes"];

    let snyk_key = attrs["key"].as_str().unwrap_or("").to_string();
    let severity = attrs["effective_severity_level"]
        .as_str()
        .unwrap_or("low")
        .to_string();
    let priority = severity_to_priority(&severity);

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

    let title = if pkg_name.is_empty() {
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

    let description = format!(
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

    let now = Utc::now();
    let mut custom: BTreeMap<String, serde_json::Value> = BTreeMap::new();
    custom.insert("snyk_key".to_string(), serde_json::Value::String(snyk_key));
    custom.insert(
        "snyk_severity".to_string(),
        serde_json::Value::String(severity),
    );

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
