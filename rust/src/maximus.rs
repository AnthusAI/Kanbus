//! Kanbus-native orchestration primitives.

use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use chrono::{DateTime, Utc};
use minijinja::Environment;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::dependencies::list_ready_issues;
use crate::error::KanbusError;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_update::update_issue;
use crate::models::IssueData;
use crate::project::load_project_directory;

/// Durable status for a Kanbus Maximus run.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum MaximusRunStatus {
    Claimed,
    Running,
    Completed,
    Failed,
    Cancelled,
}

/// Durable run metadata managed by Kanbus commands.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MaximusRunRecord {
    pub run_id: String,
    pub issue_id: String,
    pub worker_id: String,
    pub status: MaximusRunStatus,
    pub workspace_path: Option<String>,
    pub branch: Option<String>,
    pub started_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub heartbeat_at: Option<DateTime<Utc>>,
    pub last_event: Option<String>,
    pub commit_sha: Option<String>,
    pub remote_branch: Option<String>,
    pub validation_summary: Option<String>,
    pub error: Option<String>,
}

/// Workflow settings loaded from a Markdown workflow file.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct MaximusWorkflow {
    #[serde(default)]
    pub target: MaximusTargetConfig,
    #[serde(default)]
    pub workspace: MaximusWorkspaceConfig,
    #[serde(default)]
    pub worker: MaximusWorkerConfig,
    #[serde(default)]
    pub codex: MaximusCodexConfig,
    #[serde(default)]
    pub prompt_template: String,
}

/// Target repository settings for worker execution.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct MaximusTargetConfig {
    pub repo: Option<String>,
    #[serde(default = "default_target_branch")]
    pub branch: String,
    #[serde(default = "default_validation_command")]
    pub validation: String,
    #[serde(default = "default_publish")]
    pub publish: String,
}

impl Default for MaximusTargetConfig {
    fn default() -> Self {
        Self {
            repo: None,
            branch: default_target_branch(),
            validation: default_validation_command(),
            publish: default_publish(),
        }
    }
}

/// Workspace settings for worker execution.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct MaximusWorkspaceConfig {
    #[serde(default = "default_workspace_root")]
    pub root: String,
}

impl Default for MaximusWorkspaceConfig {
    fn default() -> Self {
        Self {
            root: default_workspace_root(),
        }
    }
}

/// Worker branch settings.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct MaximusWorkerConfig {
    #[serde(default = "default_branch_pattern")]
    pub branch_pattern: String,
}

impl Default for MaximusWorkerConfig {
    fn default() -> Self {
        Self {
            branch_pattern: default_branch_pattern(),
        }
    }
}

/// Codex App Server settings.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct MaximusCodexConfig {
    #[serde(default = "default_codex_command")]
    pub command: String,
    #[serde(default = "default_codex_timeout_seconds")]
    pub timeout_seconds: u64,
}

impl Default for MaximusCodexConfig {
    fn default() -> Self {
        Self {
            command: default_codex_command(),
            timeout_seconds: default_codex_timeout_seconds(),
        }
    }
}

fn default_target_branch() -> String {
    "develop".to_string()
}

fn default_validation_command() -> String {
    "make test".to_string()
}

fn default_publish() -> String {
    "push-only".to_string()
}

fn default_workspace_root() -> String {
    std::env::temp_dir()
        .join("kanbus-maximus-workspaces")
        .to_string_lossy()
        .to_string()
}

fn default_branch_pattern() -> String {
    "experiment/kanbus-maximus-{{ issue.identifier }}".to_string()
}

fn default_codex_command() -> String {
    "codex app-server".to_string()
}

fn default_codex_timeout_seconds() -> u64 {
    3600
}

/// Claim the next eligible issue for a worker.
pub fn claim_next_issue(
    root: &Path,
    ready: bool,
    worker_id: &str,
) -> Result<IssueData, KanbusError> {
    let mut issues = if ready {
        list_ready_issues(root, false, false)?
    } else {
        crate::issue_listing::list_issues(
            root,
            Some("open"),
            None,
            None,
            None,
            Some("priority"),
            None,
            &[],
            false,
            false,
        )?
    };
    issues.retain(|issue| issue.status == "open");
    issues.sort_by(|left, right| {
        left.priority
            .cmp(&right.priority)
            .then(left.created_at.cmp(&right.created_at))
            .then(left.identifier.cmp(&right.identifier))
    });
    let issue = issues
        .into_iter()
        .next()
        .ok_or_else(|| KanbusError::IssueOperation("no claimable issues".to_string()))?;
    update_issue(
        root,
        &issue.identifier,
        None,
        None,
        None,
        Some(worker_id),
        None,
        true,
        true,
        &[],
        &[],
        None,
        None,
        None,
    )
}

/// Create a durable run record for an issue.
pub fn create_run_record(
    root: &Path,
    issue_id: &str,
    worker_id: &str,
) -> Result<MaximusRunRecord, KanbusError> {
    load_issue_from_project(root, issue_id)?;
    let now = Utc::now();
    let record = MaximusRunRecord {
        run_id: format!("kmx-{}", Uuid::new_v4()),
        issue_id: issue_id.to_string(),
        worker_id: worker_id.to_string(),
        status: MaximusRunStatus::Claimed,
        workspace_path: None,
        branch: None,
        started_at: now,
        updated_at: now,
        heartbeat_at: Some(now),
        last_event: Some("run created".to_string()),
        commit_sha: None,
        remote_branch: None,
        validation_summary: None,
        error: None,
    };
    write_run_record(root, &record)?;
    Ok(record)
}

/// List durable run records.
pub fn list_run_records(root: &Path) -> Result<Vec<MaximusRunRecord>, KanbusError> {
    let runs_dir = runs_directory(root)?;
    if !runs_dir.exists() {
        return Ok(Vec::new());
    }
    let mut records = Vec::new();
    for entry in fs::read_dir(&runs_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        records.push(read_run_record_from_path(&path)?);
    }
    records.sort_by(|left, right| left.started_at.cmp(&right.started_at));
    Ok(records)
}

/// Show one durable run record.
pub fn show_run_record(root: &Path, run_id: &str) -> Result<MaximusRunRecord, KanbusError> {
    let path = run_record_path(root, run_id)?;
    read_run_record_from_path(&path)
}

/// Mark one run as cancelled.
pub fn cancel_run_record(root: &Path, run_id: &str) -> Result<MaximusRunRecord, KanbusError> {
    let mut record = show_run_record(root, run_id)?;
    record.status = MaximusRunStatus::Cancelled;
    record.updated_at = Utc::now();
    record.last_event = Some("run cancelled".to_string());
    write_run_record(root, &record)?;
    Ok(record)
}

/// Load a Kanbus Maximus workflow from Markdown with YAML front matter.
pub fn load_workflow(path: &Path) -> Result<MaximusWorkflow, KanbusError> {
    let content = fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let (front_matter, prompt_template) = split_front_matter(&content)?;
    let mut workflow: MaximusWorkflow = if front_matter.trim().is_empty() {
        MaximusWorkflow {
            target: MaximusTargetConfig::default(),
            workspace: MaximusWorkspaceConfig::default(),
            worker: MaximusWorkerConfig::default(),
            codex: MaximusCodexConfig::default(),
            prompt_template: String::new(),
        }
    } else {
        serde_yaml::from_str(front_matter)
            .map_err(|error| KanbusError::Configuration(error.to_string()))?
    };
    workflow.prompt_template = prompt_template.trim().to_string();
    validate_workflow(&workflow)?;
    Ok(workflow)
}

/// Render the branch name for an issue.
pub fn render_branch_name(
    workflow: &MaximusWorkflow,
    issue: &IssueData,
) -> Result<String, KanbusError> {
    render_template(&workflow.worker.branch_pattern, issue)
}

/// Render the worker prompt for an issue.
pub fn render_worker_prompt(
    workflow: &MaximusWorkflow,
    issue: &IssueData,
) -> Result<String, KanbusError> {
    let template = if workflow.prompt_template.trim().is_empty() {
        "You are working on Kanbus issue {{ issue.identifier }}: {{ issue.title }}."
    } else {
        workflow.prompt_template.as_str()
    };
    render_template(template, issue)
}

/// Run a single worker for an issue.
pub fn run_worker(
    root: &Path,
    issue_id: &str,
    workflow_path: &Path,
    target_repo: Option<&str>,
    worker_id: &str,
) -> Result<MaximusRunRecord, KanbusError> {
    let workflow = load_workflow(workflow_path)?;
    let issue = load_issue_from_project(root, issue_id)?.issue;
    let mut record = create_run_record(root, issue_id, worker_id)?;
    let result = run_worker_inner(root, &workflow, &issue, target_repo, &mut record);
    match result {
        Ok(()) => {
            record.status = MaximusRunStatus::Completed;
            record.updated_at = Utc::now();
            record.last_event = Some("worker completed".to_string());
            write_run_record(root, &record)?;
            Ok(record)
        }
        Err(error) => {
            record.status = MaximusRunStatus::Failed;
            record.updated_at = Utc::now();
            record.error = Some(error.to_string());
            record.last_event = Some("worker failed".to_string());
            write_run_record(root, &record)?;
            Err(error)
        }
    }
}

/// Run one orchestrator dispatch cycle.
pub fn run_orchestrator_once(
    root: &Path,
    workflow_path: &Path,
    max_concurrent: usize,
    worker_id: &str,
) -> Result<MaximusRunRecord, KanbusError> {
    if max_concurrent == 0 {
        return Err(KanbusError::IssueOperation(
            "max-concurrent must be greater than zero".to_string(),
        ));
    }
    let workflow = load_workflow(workflow_path)?;
    let target_repo = workflow
        .target
        .repo
        .as_deref()
        .ok_or_else(|| KanbusError::Configuration("target.repo is required".to_string()))?;
    let issue = claim_next_issue(root, true, worker_id)?;
    run_worker(
        root,
        &issue.identifier,
        workflow_path,
        Some(target_repo),
        worker_id,
    )
}

fn run_worker_inner(
    root: &Path,
    workflow: &MaximusWorkflow,
    issue: &IssueData,
    target_repo: Option<&str>,
    record: &mut MaximusRunRecord,
) -> Result<(), KanbusError> {
    record.status = MaximusRunStatus::Running;
    record.updated_at = Utc::now();
    record.last_event = Some("worker running".to_string());
    let branch = render_branch_name(workflow, issue)?;
    let workspace = workspace_path(workflow, issue);
    record.workspace_path = Some(workspace.to_string_lossy().to_string());
    record.branch = Some(branch.clone());
    write_run_record(root, record)?;

    prepare_workspace(workflow, target_repo, &workspace, &branch)?;
    let prompt = render_worker_prompt(workflow, issue)?;
    let codex_event = run_codex_app_server(&workflow.codex.command, &workspace, &prompt)?;
    record.last_event = Some(codex_event);
    record.heartbeat_at = Some(Utc::now());
    write_run_record(root, record)?;

    let validation = run_shell_command(&workspace, &workflow.target.validation)?;
    record.validation_summary = Some(validation);
    let commit_sha = ensure_commit(&workspace, issue)?;
    record.commit_sha = Some(commit_sha);
    if workflow.target.publish != "push-only" {
        return Err(KanbusError::Configuration(
            "only publish: push-only is supported".to_string(),
        ));
    }
    run_git(&workspace, &["push", "-u", "origin", &branch])?;
    record.remote_branch = Some(branch);
    Ok(())
}

fn split_front_matter(content: &str) -> Result<(&str, &str), KanbusError> {
    if !content.starts_with("---") {
        return Ok(("", content));
    }
    let rest = &content[3..];
    let Some(end) = rest.find("\n---") else {
        return Err(KanbusError::Configuration(
            "workflow front matter is not closed".to_string(),
        ));
    };
    Ok((&rest[..end], &rest[(end + 4)..]))
}

fn validate_workflow(workflow: &MaximusWorkflow) -> Result<(), KanbusError> {
    if workflow.target.branch.trim().is_empty() {
        return Err(KanbusError::Configuration(
            "target.branch is required".to_string(),
        ));
    }
    if workflow.worker.branch_pattern.trim().is_empty() {
        return Err(KanbusError::Configuration(
            "worker.branch_pattern is required".to_string(),
        ));
    }
    if workflow.codex.command.trim().is_empty() {
        return Err(KanbusError::Configuration(
            "codex.command is required".to_string(),
        ));
    }
    Ok(())
}

fn render_template(template: &str, issue: &IssueData) -> Result<String, KanbusError> {
    let mut environment = Environment::new();
    environment
        .add_template("template", template)
        .map_err(|error| KanbusError::Configuration(error.to_string()))?;
    let template = environment
        .get_template("template")
        .map_err(|error| KanbusError::Configuration(error.to_string()))?;
    let mut issue_value =
        serde_json::to_value(issue).map_err(|error| KanbusError::Io(error.to_string()))?;
    if let Some(object) = issue_value.as_object_mut() {
        object.insert(
            "identifier".to_string(),
            Value::String(issue.identifier.clone()),
        );
    }
    template
        .render(json!({ "issue": issue_value }))
        .map_err(|error| KanbusError::Configuration(error.to_string()))
}

fn runs_directory(root: &Path) -> Result<PathBuf, KanbusError> {
    Ok(load_project_directory(root)?.join("runs"))
}

fn run_record_path(root: &Path, run_id: &str) -> Result<PathBuf, KanbusError> {
    Ok(runs_directory(root)?.join(format!("{run_id}.json")))
}

fn write_run_record(root: &Path, record: &MaximusRunRecord) -> Result<(), KanbusError> {
    let runs_dir = runs_directory(root)?;
    fs::create_dir_all(&runs_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let path = runs_dir.join(format!("{}.json", record.run_id));
    let payload =
        serde_json::to_string_pretty(record).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(path, payload).map_err(|error| KanbusError::Io(error.to_string()))
}

fn read_run_record_from_path(path: &Path) -> Result<MaximusRunRecord, KanbusError> {
    let payload = fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    serde_json::from_str(&payload).map_err(|error| KanbusError::Io(error.to_string()))
}

fn workspace_path(workflow: &MaximusWorkflow, issue: &IssueData) -> PathBuf {
    let root = expand_home(&workflow.workspace.root);
    PathBuf::from(root).join(sanitize_path_segment(&issue.identifier))
}

fn expand_home(path: &str) -> String {
    if path == "~" {
        return std::env::var("HOME").unwrap_or_else(|_| path.to_string());
    }
    if let Some(rest) = path.strip_prefix("~/") {
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home).join(rest).to_string_lossy().to_string();
        }
    }
    path.to_string()
}

fn sanitize_path_segment(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-') {
                character
            } else {
                '_'
            }
        })
        .collect()
}

fn prepare_workspace(
    workflow: &MaximusWorkflow,
    target_repo: Option<&str>,
    workspace: &Path,
    branch: &str,
) -> Result<(), KanbusError> {
    if !workspace.exists() {
        let repo = target_repo
            .or(workflow.target.repo.as_deref())
            .ok_or_else(|| KanbusError::Configuration("target.repo is required".to_string()))?;
        let parent = workspace.parent().ok_or_else(|| {
            KanbusError::Io(format!("workspace has no parent: {}", workspace.display()))
        })?;
        fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
        run_command(
            parent,
            Command::new("git").arg("clone").arg(repo).arg(workspace),
        )?;
    }
    run_git(workspace, &["fetch", "origin", &workflow.target.branch])?;
    let upstream = format!("origin/{}", workflow.target.branch);
    run_git(workspace, &["checkout", "-B", branch, &upstream])?;
    run_git(workspace, &["reset", "--hard", &upstream])?;
    run_git(workspace, &["clean", "-ffdx"])?;
    Ok(())
}

fn run_codex_app_server(
    command: &str,
    workspace: &Path,
    prompt: &str,
) -> Result<String, KanbusError> {
    let mut child = Command::new("sh")
        .arg("-lc")
        .arg(command)
        .current_dir(workspace)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| KanbusError::Io("failed to open app-server stdin".to_string()))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| KanbusError::Io("failed to open app-server stdout".to_string()))?;
    let mut reader = BufReader::new(stdout);

    send_json(
        &mut stdin,
        json!({
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "kanbus-maximus",
                    "version": env!("GIT_VERSION")
                }
            }
        }),
    )?;
    read_response(&mut reader, 1)?;

    send_json(
        &mut stdin,
        json!({
            "id": 2,
            "method": "thread/start",
            "params": {
                "cwd": workspace.to_string_lossy(),
                "approvalPolicy": "never",
                "sandbox": "workspace-write"
            }
        }),
    )?;
    let thread_response = read_response(&mut reader, 2)?;
    let thread_id = thread_response["result"]["thread"]["id"]
        .as_str()
        .ok_or_else(|| {
            KanbusError::ProtocolError("thread/start response missing thread.id".to_string())
        })?
        .to_string();

    send_json(
        &mut stdin,
        json!({
            "id": 3,
            "method": "turn/start",
            "params": {
                "threadId": thread_id,
                "input": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ],
                "cwd": workspace.to_string_lossy(),
                "sandboxPolicy": {
                    "type": "workspaceWrite"
                }
            }
        }),
    )?;
    read_response(&mut reader, 3)?;
    let last_event = read_until_turn_completed(&mut reader)?;
    let _ = child.kill();
    let _ = child.wait();
    Ok(last_event)
}

fn send_json(stdin: &mut impl Write, value: Value) -> Result<(), KanbusError> {
    let line = serde_json::to_string(&value).map_err(|error| KanbusError::Io(error.to_string()))?;
    writeln!(stdin, "{line}").map_err(|error| KanbusError::Io(error.to_string()))?;
    stdin
        .flush()
        .map_err(|error| KanbusError::Io(error.to_string()))
}

fn read_response(reader: &mut impl BufRead, expected_id: i64) -> Result<Value, KanbusError> {
    loop {
        let value = read_json_line(reader)?;
        if value.get("id").and_then(Value::as_i64) != Some(expected_id) {
            continue;
        }
        if let Some(error) = value.get("error") {
            return Err(KanbusError::ProtocolError(error.to_string()));
        }
        return Ok(value);
    }
}

fn read_until_turn_completed(reader: &mut impl BufRead) -> Result<String, KanbusError> {
    loop {
        let value = read_json_line(reader)?;
        let method = value.get("method").and_then(Value::as_str).unwrap_or("");
        if method == "error" {
            return Err(KanbusError::ProtocolError(value.to_string()));
        }
        if method == "turn/completed" {
            return Ok("turn/completed".to_string());
        }
    }
}

fn read_json_line(reader: &mut impl BufRead) -> Result<Value, KanbusError> {
    let mut line = String::new();
    let bytes = reader
        .read_line(&mut line)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if bytes == 0 {
        return Err(KanbusError::ProtocolError(
            "app-server closed stdout".to_string(),
        ));
    }
    serde_json::from_str(line.trim()).map_err(|error| KanbusError::ProtocolError(error.to_string()))
}

fn run_shell_command(workspace: &Path, command: &str) -> Result<String, KanbusError> {
    run_command(workspace, Command::new("sh").arg("-lc").arg(command))
}

fn run_git(workspace: &Path, args: &[&str]) -> Result<String, KanbusError> {
    let mut command = Command::new("git");
    command.args(args);
    run_command(workspace, &mut command)
}

fn run_command(workspace: &Path, command: &mut Command) -> Result<String, KanbusError> {
    let output = command
        .current_dir(workspace)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        let message = if stderr.is_empty() { stdout } else { stderr };
        return Err(KanbusError::IssueOperation(message));
    }
    Ok(stdout)
}

fn ensure_commit(workspace: &Path, issue: &IssueData) -> Result<String, KanbusError> {
    let status = run_git(workspace, &["status", "--porcelain"])?;
    if !status.trim().is_empty() {
        run_git(workspace, &["add", "."])?;
        let message = format!("Kanbus Maximus trial {}", issue.identifier);
        run_git(
            workspace,
            &[
                "-c",
                "user.name=Kanbus Maximus",
                "-c",
                "user.email=kanbus-maximus@example.invalid",
                "commit",
                "-m",
                &message,
            ],
        )?;
    }
    run_git(workspace, &["rev-parse", "HEAD"])
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn issue(identifier: &str) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: "Trial issue".to_string(),
            description: "Description".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap(),
            updated_at: Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap(),
            closed_at: None,
            custom: Default::default(),
        }
    }

    #[test]
    fn workflow_defaults_and_prompt_body_are_loaded() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("WORKFLOW.md");
        fs::write(
            &workflow_path,
            "---\ntarget:\n  repo: /tmp/repo\n---\nHello {{ issue.identifier }}",
        )
        .expect("write workflow");

        let workflow = load_workflow(&workflow_path).expect("load workflow");

        assert_eq!(workflow.target.repo.as_deref(), Some("/tmp/repo"));
        assert_eq!(workflow.target.branch, "develop");
        assert_eq!(workflow.target.validation, "make test");
        assert_eq!(workflow.prompt_template, "Hello {{ issue.identifier }}");
    }

    #[test]
    fn invalid_workflow_front_matter_is_rejected() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("WORKFLOW.md");
        fs::write(&workflow_path, "---\ntarget: [\n---\nBody").expect("write workflow");

        let error = load_workflow(&workflow_path).expect_err("workflow error");

        match error {
            KanbusError::Configuration(_) => {}
            other => panic!("expected configuration error, got {other:?}"),
        }
    }

    #[test]
    fn branch_names_are_rendered_from_issue_context() {
        let workflow = MaximusWorkflow {
            worker: MaximusWorkerConfig {
                branch_pattern: "experiment/{{ issue.identifier }}".to_string(),
            },
            ..MaximusWorkflow {
                target: MaximusTargetConfig::default(),
                workspace: MaximusWorkspaceConfig::default(),
                worker: MaximusWorkerConfig::default(),
                codex: MaximusCodexConfig::default(),
                prompt_template: String::new(),
            }
        };

        let branch = render_branch_name(&workflow, &issue("kanbus-123")).expect("branch");

        assert_eq!(branch, "experiment/kanbus-123");
    }

    #[test]
    fn app_server_client_accepts_fake_protocol() {
        let temp = tempfile::tempdir().expect("tempdir");
        let fake = temp.path().join("fake-app-server.sh");
        fs::write(
            &fake,
            r#"#!/bin/sh
while IFS= read -r line; do
  id=$(printf '%s' "$line" | sed -n 's/.*"id":\([0-9][0-9]*\).*/\1/p')
  method=$(printf '%s' "$line" | sed -n 's/.*"method":"\([^"]*\)".*/\1/p')
  if [ "$method" = "thread/start" ]; then
    printf '{"id":%s,"result":{"thread":{"id":"thread-1"}}}\n' "$id"
  elif [ "$method" = "turn/start" ]; then
    printf '{"id":%s,"result":{"turn":{"id":"turn-1"}}}\n' "$id"
    printf '{"method":"turn/completed","params":{"threadId":"thread-1","turn":{"id":"turn-1"}}}\n'
  else
    printf '{"id":%s,"result":{}}\n' "$id"
  fi
done
"#,
        )
        .expect("write fake");
        run_command(temp.path(), Command::new("chmod").arg("+x").arg(&fake)).expect("chmod");

        let event = run_codex_app_server(
            &fake.to_string_lossy(),
            temp.path(),
            "perform a harmless task",
        )
        .expect("run fake app server");

        assert_eq!(event, "turn/completed");
    }
}
