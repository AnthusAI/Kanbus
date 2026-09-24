use regex::Regex;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use crate::error::KanbusError;
use crate::file_io::get_configuration_path;

/// Plan for rekeying a project.
pub struct RekeyPlan {
    pub old_key: String,
    pub new_key: String,
    pub issue_renames: HashMap<String, String>,
    pub text_rewrites: HashMap<String, usize>,
}

/// Plan a project rekey operation.
pub fn plan_rekey(
    root: &Path,
    old_key: &str,
    new_key: &str,
    dry_run: bool,
) -> Result<RekeyPlan, KanbusError> {
    if old_key == new_key {
        return Err(KanbusError::IssueOperation("new key equals old key".to_string()));
    }

    validate_project_key(new_key)?;

    if !dry_run {
        check_git_tree_clean(root)?;
    }

    let project_dir = crate::file_io::load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");

    let mut old_ids = Vec::new();
    if issues_dir.exists() {
        for entry in fs::read_dir(&issues_dir).map_err(|e| KanbusError::Io(e.to_string()))? {
            let entry = entry.map_err(|e| KanbusError::Io(e.to_string()))?;
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                if let Some(filename) = path.file_stem() {
                    let id = filename.to_string_lossy().to_string();
                    if id.starts_with(&format!("{}-", old_key)) {
                        old_ids.push(id);
                    }
                }
            }
        }
    }

    old_ids.sort();

    let mut issue_renames = HashMap::new();
    for old_id in &old_ids {
        let suffix = &old_id[old_key.len() + 1..];
        let new_id = format!("{}-{}", new_key, suffix);

        if !dry_run && issues_dir.join(format!("{}.json", new_id)).exists() {
            return Err(KanbusError::IssueOperation(format!(
                "{} already exists",
                new_id
            )));
        }

        issue_renames.insert(old_id.clone(), new_id);
    }

    let text_rewrites = HashMap::new();

    Ok(RekeyPlan {
        old_key: old_key.to_string(),
        new_key: new_key.to_string(),
        issue_renames,
        text_rewrites,
    })
}

/// Execute a rekey plan.
pub fn execute_rekey(root: &Path, plan: &mut RekeyPlan) -> Result<(), KanbusError> {
    let project_dir = crate::file_io::load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");

    let valid_ids: HashSet<String> = plan.issue_renames.keys().cloned().collect();

    for (old_id, new_id) in &plan.issue_renames {
        let old_path = issues_dir.join(format!("{}.json", old_id));

        if !old_path.exists() {
            continue;
        }

        let content = fs::read_to_string(&old_path)
            .map_err(|e| KanbusError::Io(e.to_string()))?;
        let mut issue_data: Value = serde_json::from_str(&content)
            .map_err(|e| KanbusError::Io(e.to_string()))?;

        issue_data["id"] = json!(new_id);

        // Rewrite parent references
        if let Some(parent) = issue_data.get("parent").and_then(|p| p.as_str()) {
            if parent.contains(&format!("{}-", plan.old_key)) {
                let new_parent = parent.replacen(
                    &format!("{}-", plan.old_key),
                    &format!("{}-", plan.new_key),
                    1,
                );
                if plan.issue_renames.values().any(|v| v == &new_parent) {
                    issue_data["parent"] = json!(new_parent);
                }
            }
        }

        // Rewrite dependency references
        if let Some(dependencies) = issue_data
            .get_mut("dependencies")
            .and_then(|d| d.as_array_mut())
        {
            for dep in dependencies {
                if let Some(target) = dep.get("target").and_then(|t| t.as_str()) {
                    if valid_ids.contains(target) {
                        if let Some(new_target) = plan.issue_renames.get(target) {
                            dep["target"] = json!(new_target);
                        }
                    }
                }
            }
        }

        // Rewrite text fields
        for field in &["title", "description"] {
            if let Some(text) = issue_data.get(field).and_then(|f| f.as_str()) {
                let (rewritten, count) =
                    rewrite_id_references(text, &plan.old_key, &plan.new_key, &valid_ids);
                if count > 0 {
                    issue_data[field] = json!(rewritten);
                    *plan
                        .text_rewrites
                        .entry(old_id.clone())
                        .or_insert(0) += count;
                }
            }
        }

        // Rewrite comments
        if let Some(comments) = issue_data
            .get_mut("comments")
            .and_then(|c| c.as_array_mut())
        {
            for comment in comments {
                if let Some(body) = comment.get("body").and_then(|b| b.as_str()) {
                    let (rewritten, count) =
                        rewrite_id_references(body, &plan.old_key, &plan.new_key, &valid_ids);
                    if count > 0 {
                        comment["body"] = json!(rewritten);
                        *plan
                            .text_rewrites
                            .entry(old_id.clone())
                            .or_insert(0) += count;
                    }
                }
            }
        }

        let new_path = issues_dir.join(format!("{}.json", new_id));
        let formatted = serde_json::to_string_pretty(&issue_data)
            .map_err(|e| KanbusError::Io(e.to_string()))?;
        fs::write(&new_path, format!("{}\n", formatted))
            .map_err(|e| KanbusError::Io(e.to_string()))?;

        if old_path != new_path {
            fs::remove_file(&old_path)
                .map_err(|e| KanbusError::Io(e.to_string()))?;
        }
    }

    // Update .kanbus.yml
    let config_path = get_configuration_path(root)?;
    let config_content = fs::read_to_string(&config_path)
        .map_err(|e| KanbusError::Io(e.to_string()))?;
    let mut config: Value = serde_yaml::from_str(&config_content)
        .map_err(|e| KanbusError::Io(e.to_string()))?;
    config["project_key"] = json!(plan.new_key);

    let yaml_str = serde_yaml::to_string(&config)
        .map_err(|e| KanbusError::Io(e.to_string()))?;
    fs::write(&config_path, yaml_str)
        .map_err(|e| KanbusError::Io(e.to_string()))?;

    invalidate_caches(&project_dir)?;

    Ok(())
}

fn rewrite_id_references(
    text: &str,
    old_key: &str,
    new_key: &str,
    valid_ids: &HashSet<String>,
) -> (String, usize) {
    let mut count = 0;
    let pattern = format!(r"\b{}-[0-9a-fA-F]{{6,}}\b", regex::escape(old_key));
    let re = Regex::new(&pattern).unwrap();

    let result = re.replace_all(text, |caps: &regex::Captures| {
        let full_match = caps.get(0).unwrap().as_str();
        if valid_ids.contains(full_match) {
            count += 1;
            full_match.replacen(&format!("{}-", old_key), &format!("{}-", new_key), 1)
        } else {
            full_match.to_string()
        }
    });

    (result.to_string(), count)
}

fn validate_project_key(key: &str) -> Result<(), KanbusError> {
    if key.is_empty() {
        return Err(KanbusError::IssueOperation(
            "invalid project key: must not be empty".to_string(),
        ));
    }
    if !key.chars().all(|c| c.is_alphanumeric() || c == '-' || c == '_') {
        return Err(KanbusError::IssueOperation(
            "invalid project key: contains invalid characters".to_string(),
        ));
    }
    Ok(())
}

fn check_git_tree_clean(root: &Path) -> Result<(), KanbusError> {
    let output = std::process::Command::new("git")
        .arg("status")
        .arg("--porcelain")
        .arg("project/")
        .current_dir(root)
        .output()
        .map_err(|e| KanbusError::Io(e.to_string()))?;

    if !output.stdout.is_empty() {
        return Err(KanbusError::IssueOperation(
            "uncommitted changes under project/".to_string(),
        ));
    }

    Ok(())
}

fn invalidate_caches(project_dir: &Path) -> Result<(), KanbusError> {
    for cache_name in &[".cache", ".index", ".overlay"] {
        let cache_path = project_dir.join(cache_name);
        if cache_path.exists() {
            fs::remove_dir_all(&cache_path)
                .map_err(|e| KanbusError::Io(e.to_string()))?;
        }
    }
    Ok(())
}
