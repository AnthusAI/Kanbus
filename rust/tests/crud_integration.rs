use std::fs;
use std::process::Command;

use regex::Regex;
use serde::Deserialize;
use tempfile::TempDir;

use taskulus::cli::run_from_args_with_output;

#[derive(Debug, Deserialize)]
struct ProjectMarker {
    project_dir: String,
}

fn load_project_dir(root: &std::path::Path) -> std::path::PathBuf {
    let contents = fs::read_to_string(root.join(".taskulus.yaml")).expect("read marker");
    let marker: ProjectMarker = serde_yaml::from_str(&contents).expect("parse marker");
    root.join(marker.project_dir)
}

fn load_issue(project_dir: &std::path::Path, identifier: &str) -> serde_json::Value {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[test]
fn crud_workflow() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");

    let init_output =
        run_from_args_with_output(["tsk", "init"], repo_path.as_path()).expect("init");
    assert!(init_output.stdout.is_empty());

    let create_output = run_from_args_with_output(
        ["tsk", "create", "Implement", "OAuth2", "flow"],
        repo_path.as_path(),
    )
    .expect("create");
    let regex = Regex::new(r"(tsk-[0-9a-f]{6})").expect("regex");
    let identifier = regex
        .captures(&create_output.stdout)
        .and_then(|matches| matches.get(1))
        .map(|value| value.as_str().to_string())
        .expect("issue id");

    let show_output =
        run_from_args_with_output(["tsk", "show", identifier.as_str()], repo_path.as_path())
            .expect("show");
    assert!(show_output.stdout.contains("Implement OAuth2 flow"));

    let update_output = run_from_args_with_output(
        ["tsk", "update", identifier.as_str(), "--title", "New Title"],
        repo_path.as_path(),
    )
    .expect("update");
    assert!(update_output.stdout.is_empty());
    let project_dir = load_project_dir(repo_path.as_path());
    let issue = load_issue(&project_dir, &identifier);
    assert_eq!(issue["title"], "New Title");

    let close_output =
        run_from_args_with_output(["tsk", "close", identifier.as_str()], repo_path.as_path())
            .expect("close");
    assert!(close_output.stdout.is_empty());
    let issue = load_issue(&project_dir, &identifier);
    assert_eq!(issue["status"], "closed");
    assert!(issue["closed_at"].is_string());

    let delete_output =
        run_from_args_with_output(["tsk", "delete", identifier.as_str()], repo_path.as_path())
            .expect("delete");
    assert!(delete_output.stdout.is_empty());
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    assert!(!issue_path.exists());
}
