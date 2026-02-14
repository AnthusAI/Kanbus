use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::Instant;

use chrono::{TimeZone, Utc};
use serde_json::json;

use kanbus::dependencies::list_ready_issues;
use kanbus::issue_files::read_issue_from_file;
use kanbus::issue_listing::list_issues;
use kanbus::models::IssueData;
use kanbus::project::discover_project_directories;

#[derive(Clone, Copy)]
struct FixturePlan {
    projects: usize,
    issues_per_project: usize,
}

#[derive(serde::Serialize)]
struct ScenarioResult {
    discover_ms: f64,
    list_ms: f64,
    ready_ms: f64,
    project_count: usize,
    issue_count: usize,
}

fn issue_identifier(project_index: usize, issue_index: usize) -> String {
    format!("kanbus-{project_index:02}{issue_index:04}")
}

fn issue_title(project_index: usize, issue_index: usize) -> String {
    format!("Project {project_index} issue {issue_index}")
}

fn build_issue(identifier: &str, title: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: BTreeMap::new(),
    }
}

fn write_issue(project_dir: &Path, issue: &IssueData) -> Result<(), Box<dyn std::error::Error>> {
    let issues_dir = project_dir.join("issues");
    fs::create_dir_all(&issues_dir)?;
    let payload = serde_json::to_string_pretty(issue)?;
    let path = issues_dir.join(format!("{}.json", issue.identifier));
    fs::write(path, payload)?;
    Ok(())
}

fn generate_project_issues(
    project_dir: &Path,
    project_index: usize,
    plan: FixturePlan,
) -> Result<(), Box<dyn std::error::Error>> {
    for issue_index in 1..=plan.issues_per_project {
        let identifier = issue_identifier(project_index, issue_index);
        let title = issue_title(project_index, issue_index);
        let issue = build_issue(&identifier, &title);
        write_issue(project_dir, &issue)?;
    }
    Ok(())
}

fn generate_single_project(
    root: &Path,
    plan: FixturePlan,
) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let project_root = root.join("single").join("project");
    generate_project_issues(&project_root, 1, plan)?;
    Ok(project_root)
}

fn generate_multi_project(
    root: &Path,
    plan: FixturePlan,
) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let repo_root = root.join("multi");
    for project_index in 1..=plan.projects {
        let project_root = repo_root
            .join("services")
            .join(format!("service-{project_index:02}"))
            .join("project");
        generate_project_issues(&project_root, project_index, plan)?;
    }
    Ok(repo_root)
}

fn remove_cache(project_dir: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let cache_dir = project_dir.join(".cache");
    if cache_dir.exists() {
        fs::remove_dir_all(cache_dir)?;
    }
    Ok(())
}

fn clear_caches(project_dirs: &[PathBuf]) -> Result<(), Box<dyn std::error::Error>> {
    for project_dir in project_dirs {
        remove_cache(project_dir)?;
    }
    Ok(())
}

fn blocked_by_dependency(issue: &IssueData) -> bool {
    issue
        .dependencies
        .iter()
        .any(|dependency| dependency.dependency_type == "blocked-by")
}

fn load_issues_for_project(project_dir: PathBuf) -> Result<Vec<IssueData>, String> {
    let issues_dir = project_dir.join("issues");
    let mut issues = Vec::new();
    let entries = fs::read_dir(&issues_dir).map_err(|error| error.to_string())?;
    for entry in entries {
        let entry = entry.map_err(|error| error.to_string())?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let issue = read_issue_from_file(&path).map_err(|error| error.to_string())?;
        issues.push(issue);
    }
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    Ok(issues)
}

fn parallel_load(project_dirs: &[PathBuf]) -> Result<Vec<IssueData>, Box<dyn std::error::Error>> {
    if project_dirs.is_empty() {
        return Ok(Vec::new());
    }
    let mut handles = Vec::new();
    for project_dir in project_dirs.iter().cloned() {
        handles.push(thread::spawn(move || load_issues_for_project(project_dir)));
    }
    let mut issues = Vec::new();
    for handle in handles {
        let batch = handle
            .join()
            .map_err(|_| "parallel load thread panicked".to_string())??;
        issues.extend(batch);
    }
    Ok(issues)
}

fn time_call<F: FnOnce() -> Result<(), Box<dyn std::error::Error>>>(
    call: F,
) -> Result<f64, Box<dyn std::error::Error>> {
    let start = Instant::now();
    call()?;
    Ok(start.elapsed().as_secs_f64() * 1000.0)
}

fn benchmark_scenario(root: &Path) -> Result<ScenarioResult, Box<dyn std::error::Error>> {
    let discover_ms = time_call(|| {
        discover_project_directories(root)?;
        Ok(())
    })?;
    let project_dirs = discover_project_directories(root)?;
    clear_caches(&project_dirs)?;

    let list_ms = time_call(|| {
        list_issues(root, None, None, None, None, None, None, true, false)?;
        Ok(())
    })?;
    let ready_ms = time_call(|| {
        list_ready_issues(root, true, false)?;
        Ok(())
    })?;

    let issues = list_issues(root, None, None, None, None, None, None, true, false)?;

    Ok(ScenarioResult {
        discover_ms,
        list_ms,
        ready_ms,
        project_count: project_dirs.len(),
        issue_count: issues.len(),
    })
}

fn benchmark_parallel(root: &Path) -> Result<ScenarioResult, Box<dyn std::error::Error>> {
    let discover_ms = time_call(|| {
        discover_project_directories(root)?;
        Ok(())
    })?;
    let project_dirs = discover_project_directories(root)?;
    clear_caches(&project_dirs)?;

    let list_ms = time_call(|| {
        parallel_load(&project_dirs)?;
        Ok(())
    })?;
    let ready_ms = time_call(|| {
        let issues = parallel_load(&project_dirs)?;
        let _ready: Vec<IssueData> = issues
            .into_iter()
            .filter(|issue| issue.status != "closed" && !blocked_by_dependency(issue))
            .collect();
        Ok(())
    })?;

    let issues = parallel_load(&project_dirs)?;

    Ok(ScenarioResult {
        discover_ms,
        list_ms,
        ready_ms,
        project_count: project_dirs.len(),
        issue_count: issues.len(),
    })
}

fn parse_args() -> (PathBuf, FixturePlan) {
    let mut root = PathBuf::from("tools/tmp/benchmark-discovery-fixtures");
    let mut projects = 10usize;
    let mut issues_per_project = 200usize;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--root" => {
                if let Some(value) = args.next() {
                    root = PathBuf::from(value);
                }
            }
            "--projects" => {
                if let Some(value) = args.next() {
                    projects = value.parse().unwrap_or(projects);
                }
            }
            "--issues-per-project" => {
                if let Some(value) = args.next() {
                    issues_per_project = value.parse().unwrap_or(issues_per_project);
                }
            }
            _ => {}
        }
    }

    (
        root,
        FixturePlan {
            projects,
            issues_per_project,
        },
    )
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (root, plan) = parse_args();

    let single_root = generate_single_project(&root, plan)?
        .parent()
        .unwrap()
        .to_path_buf();
    let multi_root = generate_multi_project(&root, plan)?;

    let single_result = benchmark_scenario(&single_root)?;
    let multi_result = benchmark_scenario(&multi_root)?;
    let single_parallel = benchmark_parallel(&single_root)?;
    let multi_parallel = benchmark_parallel(&multi_root)?;

    let payload = json!({
        "fixtures_root": root.to_string_lossy(),
        "projects": plan.projects,
        "issues_per_project": plan.issues_per_project,
        "serial": {
            "single": single_result,
            "multi": multi_result,
        },
        "parallel": {
            "single": single_parallel,
            "multi": multi_parallel,
        },
    });
    println!("{}", serde_json::to_string_pretty(&payload)?);
    Ok(())
}
