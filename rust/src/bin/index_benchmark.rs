use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;
use std::time::Instant;

use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use uuid::Uuid;

use taskulus::cache::{collect_issue_file_mtimes, load_cache_if_valid, write_cache};
use taskulus::index::build_index_from_directory;
use taskulus::index::IssueIndex;
use taskulus::issue_files::read_issue_from_file;
use taskulus::models::{DependencyLink, IssueData};

const ISSUE_COUNT: usize = 1000;
const RUST_INDEX_BUILD_TARGET_MS: f64 = 1.0;
const RUST_CACHE_LOAD_TARGET_MS: f64 = 1.0;

fn create_issue(identifier: &str, now: DateTime<Utc>) -> IssueData {
    let dependencies = if identifier.ends_with('0') {
        vec![DependencyLink {
            target: "tsk-000001".to_string(),
            dependency_type: "blocked-by".to_string(),
        }]
    } else {
        Vec::new()
    };

    IssueData {
        identifier: identifier.to_string(),
        title: format!("Benchmark issue {identifier}"),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: vec!["benchmark".to_string()],
        dependencies,
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: BTreeMap::new(),
    }
}

fn generate_issues(issues_directory: &PathBuf) -> Result<(), Box<dyn std::error::Error>> {
    let now = Utc::now();
    fs::create_dir_all(issues_directory)?;

    for index in 0..ISSUE_COUNT {
        let identifier = format!("tsk-{index:06}");
        let issue = create_issue(&identifier, now);
        let payload = serde_json::to_string_pretty(&issue)?;
        let path = issues_directory.join(format!("{identifier}.json"));
        fs::write(path, payload)?;
    }

    Ok(())
}

fn add_issue_to_index(index: &mut IssueIndex, issue: IssueData) {
    let shared = Arc::new(issue);
    index
        .by_id
        .insert(shared.identifier.clone(), Arc::clone(&shared));
    index
        .by_status
        .entry(shared.status.clone())
        .or_default()
        .push(Arc::clone(&shared));
    index
        .by_type
        .entry(shared.issue_type.clone())
        .or_default()
        .push(Arc::clone(&shared));
    if let Some(parent) = shared.parent.clone() {
        index
            .by_parent
            .entry(parent)
            .or_default()
            .push(Arc::clone(&shared));
    }
    for label in &shared.labels {
        index
            .by_label
            .entry(label.clone())
            .or_default()
            .push(Arc::clone(&shared));
    }
    for dependency in &shared.dependencies {
        if dependency.dependency_type == "blocked-by" {
            index
                .reverse_dependencies
                .entry(dependency.target.clone())
                .or_default()
                .push(Arc::clone(&shared));
        }
    }
}

fn create_index() -> IssueIndex {
    IssueIndex {
        by_id: BTreeMap::new(),
        by_status: BTreeMap::new(),
        by_type: BTreeMap::new(),
        by_parent: BTreeMap::new(),
        by_label: BTreeMap::new(),
        reverse_dependencies: BTreeMap::new(),
    }
}

fn build_index_parallel(issues_directory: &Path) -> Result<IssueIndex, Box<dyn std::error::Error>> {
    let mut json_paths = Vec::new();
    for entry in fs::read_dir(issues_directory)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        json_paths.push(path);
    }
    json_paths.sort();

    let mut handles = Vec::new();
    for path in json_paths {
        handles.push(thread::spawn(move || read_issue_from_file(&path)));
    }

    let mut index = create_index();
    for handle in handles {
        let issue = handle
            .join()
            .map_err(|_| "parallel read thread panicked".to_string())??;
        add_issue_to_index(&mut index, issue);
    }

    Ok(index)
}

fn run_serial(
    issues_directory: &Path,
    cache_path: &Path,
) -> Result<(f64, f64), Box<dyn std::error::Error>> {
    let start = Instant::now();
    let index = build_index_from_directory(issues_directory)?;
    let build_ms = start.elapsed().as_secs_f64() * 1000.0;

    let mtimes = collect_issue_file_mtimes(issues_directory)?;
    write_cache(&index, cache_path, &mtimes)?;

    let start = Instant::now();
    let cached = load_cache_if_valid(cache_path, issues_directory)?;
    let cache_ms = start.elapsed().as_secs_f64() * 1000.0;

    if cached.is_none() {
        let contents = fs::read_to_string(cache_path)?;
        let payload: Value = serde_json::from_str(&contents)?;
        let file_mtimes: BTreeMap<String, f64> = serde_json::from_value(
            payload
                .get("file_mtimes")
                .cloned()
                .unwrap_or_else(|| json!({})),
        )?;
        let current_mtimes = collect_issue_file_mtimes(issues_directory)?;
        let mismatch = file_mtimes != current_mtimes;
        let mut mismatch_sample = None;
        if mismatch {
            for (name, cached) in &file_mtimes {
                if current_mtimes.get(name) != Some(cached) {
                    mismatch_sample =
                        Some((name.clone(), *cached, current_mtimes.get(name).copied()));
                    break;
                }
            }
        }
        let output = json!({
            "issue_count": ISSUE_COUNT,
            "cache_loaded": false,
            "mtimes_match": !mismatch,
            "file_mtimes_count": file_mtimes.len(),
            "current_mtimes_count": current_mtimes.len(),
            "mismatch_sample": mismatch_sample,
            "cache_path": cache_path.to_string_lossy(),
        });
        println!("{}", serde_json::to_string_pretty(&output)?);
        return Err("cache did not load".into());
    }

    Ok((build_ms, cache_ms))
}

fn run_parallel(
    issues_directory: &Path,
    cache_path: &Path,
) -> Result<(f64, f64), Box<dyn std::error::Error>> {
    let start = Instant::now();
    let index = build_index_parallel(issues_directory)?;
    let build_ms = start.elapsed().as_secs_f64() * 1000.0;

    let mtimes = collect_issue_file_mtimes(issues_directory)?;
    write_cache(&index, cache_path, &mtimes)?;

    let start = Instant::now();
    let cached = load_cache_if_valid(cache_path, issues_directory)?;
    let cache_ms = start.elapsed().as_secs_f64() * 1000.0;

    if cached.is_none() {
        return Err("cache did not load".into());
    }

    Ok((build_ms, cache_ms))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let temp_root = std::env::temp_dir().join(format!("taskulus-index-bench-{}", Uuid::new_v4()));
    let issues_directory = temp_root.join("project").join("issues");
    let cache_path = temp_root.join("project").join(".cache").join("index.json");

    generate_issues(&issues_directory)?;

    let (build_ms, cache_ms) = run_serial(&issues_directory, &cache_path)?;
    let (parallel_build_ms, parallel_cache_ms) = run_parallel(&issues_directory, &cache_path)?;

    let output = json!({
        "issue_count": ISSUE_COUNT,
        "build_ms": build_ms,
        "cache_load_ms": cache_ms,
        "parallel": {
            "build_ms": parallel_build_ms,
            "cache_load_ms": parallel_cache_ms,
        },
        "build_target_ms": RUST_INDEX_BUILD_TARGET_MS,
        "cache_load_target_ms": RUST_CACHE_LOAD_TARGET_MS,
    });
    println!("{}", serde_json::to_string_pretty(&output)?);

    Ok(())
}
