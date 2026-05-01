//! Kanbus-native orchestration primitives.

use std::fs;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use chrono::{DateTime, Utc};
use minijinja::Environment;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::config_loader::load_project_configuration;
use crate::dependencies::list_ready_issues;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_comment::add_comment;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_update::update_issue;
use crate::models::IssueData;
use crate::project::load_project_directory;

/// Durable status for an orchestration run.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OrchestrationRunStatus {
    Claimed,
    Running,
    Completed,
    Failed,
    Cancelled,
}

/// Durable run metadata managed by Kanbus commands.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationRunRecord {
    pub run_id: String,
    pub issue_id: String,
    pub worker_id: String,
    pub status: OrchestrationRunStatus,
    pub workspace_path: Option<String>,
    pub branch: Option<String>,
    pub started_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub heartbeat_at: Option<DateTime<Utc>>,
    pub last_event: Option<String>,
    pub commit_sha: Option<String>,
    pub remote_branch: Option<String>,
    pub pull_request_url: Option<String>,
    pub validation_summary: Option<String>,
    pub error: Option<String>,
}

/// Workflow settings loaded from Markdown or repository configuration.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationWorkflow {
    #[serde(default)]
    pub target: OrchestrationTargetConfig,
    #[serde(default)]
    pub workspace: OrchestrationWorkspaceConfig,
    #[serde(default)]
    pub worker: OrchestrationWorkerConfig,
    #[serde(default)]
    pub codex: OrchestrationCodexConfig,
    #[serde(default)]
    pub procedures: OrchestrationProceduresConfig,
    #[serde(default)]
    pub prompt_template: String,
}

/// Optional bounded procedure hooks used by orchestration.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct OrchestrationProceduresConfig {
    #[serde(default)]
    pub pr_draft: Option<OrchestrationProcedureConfig>,
}

/// One configured procedure invocation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationProcedureConfig {
    #[serde(default = "default_procedure_runtime")]
    pub runtime: String,
    pub file: Option<String>,
    pub source: Option<String>,
    pub command: Option<String>,
    #[serde(default = "default_procedure_timeout_seconds")]
    pub timeout_seconds: u64,
}

fn default_procedure_runtime() -> String {
    "command".to_string()
}

fn default_procedure_timeout_seconds() -> u64 {
    120
}

/// Target repository settings for worker execution.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationTargetConfig {
    pub repo: Option<String>,
    #[serde(default = "default_target_branch")]
    pub branch: String,
    #[serde(default = "default_validation_command")]
    pub validation: String,
    #[serde(default = "default_publish")]
    pub publish: String,
    #[serde(default)]
    pub commit_message: Option<String>,
    #[serde(default)]
    pub pr_title: Option<String>,
    #[serde(default)]
    pub pr_body: Option<String>,
    #[serde(default)]
    pub allowed_paths: Vec<String>,
}

impl Default for OrchestrationTargetConfig {
    fn default() -> Self {
        Self {
            repo: None,
            branch: default_target_branch(),
            validation: default_validation_command(),
            publish: default_publish(),
            commit_message: None,
            pr_title: None,
            pr_body: None,
            allowed_paths: Vec::new(),
        }
    }
}

/// Workspace settings for worker execution.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationWorkspaceConfig {
    #[serde(default = "default_workspace_root")]
    pub root: String,
}

impl Default for OrchestrationWorkspaceConfig {
    fn default() -> Self {
        Self {
            root: default_workspace_root(),
        }
    }
}

/// Worker branch settings.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationWorkerConfig {
    #[serde(default = "default_branch_pattern")]
    pub branch_pattern: String,
    #[serde(default = "default_worker_runtime")]
    pub runtime: String,
    #[serde(default)]
    pub procedure: Option<OrchestrationProcedureConfig>,
}

impl Default for OrchestrationWorkerConfig {
    fn default() -> Self {
        Self {
            branch_pattern: default_branch_pattern(),
            runtime: default_worker_runtime(),
            procedure: None,
        }
    }
}

/// Codex App Server settings.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OrchestrationCodexConfig {
    #[serde(default = "default_codex_command")]
    pub command: String,
    #[serde(default = "default_codex_timeout_seconds")]
    pub timeout_seconds: u64,
}

impl Default for OrchestrationCodexConfig {
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
    "git diff --check".to_string()
}

fn default_publish() -> String {
    "push-only".to_string()
}

fn default_workspace_root() -> String {
    "~/.kanbus/orchestration-workspaces".to_string()
}

fn default_branch_pattern() -> String {
    "agent/{{ issue.identifier }}/{{ run.short_id }}".to_string()
}

fn default_worker_runtime() -> String {
    "codex-app-server".to_string()
}

fn default_codex_command() -> String {
    "codex app-server".to_string()
}

fn default_codex_timeout_seconds() -> u64 {
    3600
}

const DISPATCH_LOCK_FILENAME: &str = ".orchestration-dispatch.lock";
const DISPATCH_LOCK_TIMEOUT_SECONDS: u64 = 10;
const DISPATCH_LOCK_POLL_MS: u64 = 50;
const APP_SERVER_POLL_MS: u64 = 250;

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

/// Claim one explicit ready issue for a worker.
pub fn claim_issue(root: &Path, issue_id: &str, worker_id: &str) -> Result<IssueData, KanbusError> {
    let issue = load_issue_from_project(root, issue_id)?.issue;
    if issue.status != "open" {
        return Err(KanbusError::IssueOperation(
            "explicit issue is not open".to_string(),
        ));
    }
    let ready_issues = list_ready_issues(root, false, false)?;
    if !ready_issues
        .iter()
        .any(|ready_issue| ready_issue.identifier == issue.identifier)
    {
        return Err(KanbusError::IssueOperation(
            "explicit issue is not ready".to_string(),
        ));
    }
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
) -> Result<OrchestrationRunRecord, KanbusError> {
    load_issue_from_project(root, issue_id)?;
    let now = Utc::now();
    let project_key = project_key(root)?;
    let record = OrchestrationRunRecord {
        run_id: format!("{}-run-{}", project_key, Uuid::new_v4()),
        issue_id: issue_id.to_string(),
        worker_id: worker_id.to_string(),
        status: OrchestrationRunStatus::Claimed,
        workspace_path: None,
        branch: None,
        started_at: now,
        updated_at: now,
        heartbeat_at: Some(now),
        last_event: Some("run created".to_string()),
        commit_sha: None,
        remote_branch: None,
        pull_request_url: None,
        validation_summary: None,
        error: None,
    };
    write_run_record(root, &record)?;
    Ok(record)
}

/// List durable run records.
pub fn list_run_records(root: &Path) -> Result<Vec<OrchestrationRunRecord>, KanbusError> {
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
    records.sort_by_key(|record| record.started_at);
    Ok(records)
}

/// Show one durable run record.
pub fn show_run_record(root: &Path, run_id: &str) -> Result<OrchestrationRunRecord, KanbusError> {
    let path = run_record_path(root, run_id)?;
    read_run_record_from_path(&path)
}

/// Mark one run as cancelled.
pub fn cancel_run_record(root: &Path, run_id: &str) -> Result<OrchestrationRunRecord, KanbusError> {
    let mut record = show_run_record(root, run_id)?;
    record.status = OrchestrationRunStatus::Cancelled;
    record.updated_at = Utc::now();
    record.last_event = Some("run cancelled".to_string());
    write_run_record(root, &record)?;
    Ok(record)
}

/// Load an orchestration workflow from Markdown with YAML front matter.
pub fn load_workflow(path: &Path) -> Result<OrchestrationWorkflow, KanbusError> {
    let content = fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let (front_matter, prompt_template) = split_front_matter(&content)?;
    let mut workflow: OrchestrationWorkflow = if front_matter.trim().is_empty() {
        OrchestrationWorkflow {
            target: OrchestrationTargetConfig::default(),
            workspace: OrchestrationWorkspaceConfig::default(),
            worker: OrchestrationWorkerConfig::default(),
            codex: OrchestrationCodexConfig::default(),
            procedures: OrchestrationProceduresConfig::default(),
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

fn load_workflow_or_default(
    root: &Path,
    workflow_path: Option<&Path>,
) -> Result<OrchestrationWorkflow, KanbusError> {
    if let Some(workflow_path) = workflow_path {
        let workflow_path = resolve_workflow_path(root, workflow_path)?;
        return load_workflow(&workflow_path);
    }
    if let Some(workflow) = load_repository_orchestration_workflow(root)? {
        return Ok(workflow);
    }
    let default_path = root.join("workflows").join("default.md");
    if default_path.is_file() {
        return load_workflow(&default_path);
    }
    Ok(default_orchestration_workflow())
}

fn load_repository_orchestration_workflow(
    root: &Path,
) -> Result<Option<OrchestrationWorkflow>, KanbusError> {
    let config_path = match get_configuration_path(root) {
        Ok(config_path) => config_path,
        Err(_) => return Ok(None),
    };
    let configuration = load_project_configuration(&config_path)?;
    let Some(orchestration) = configuration.orchestration else {
        return Ok(None);
    };
    let mut base = serde_yaml::to_value(default_orchestration_workflow())
        .map_err(|error| KanbusError::Configuration(error.to_string()))?;
    merge_yaml_value(&mut base, orchestration);
    let workflow: OrchestrationWorkflow = serde_yaml::from_value(base)
        .map_err(|error| KanbusError::Configuration(error.to_string()))?;
    validate_workflow(&workflow)?;
    Ok(Some(workflow))
}

fn merge_yaml_value(base: &mut serde_yaml::Value, overlay: serde_yaml::Value) {
    match (base, overlay) {
        (serde_yaml::Value::Mapping(base_map), serde_yaml::Value::Mapping(overlay_map)) => {
            for (key, overlay_value) in overlay_map {
                match base_map.get_mut(&key) {
                    Some(base_value) => merge_yaml_value(base_value, overlay_value),
                    None => {
                        base_map.insert(key, overlay_value);
                    }
                }
            }
        }
        (base_value, overlay_value) => {
            *base_value = overlay_value;
        }
    }
}

fn default_orchestration_workflow() -> OrchestrationWorkflow {
    OrchestrationWorkflow {
        target: OrchestrationTargetConfig {
            publish: "pull-request".to_string(),
            ..OrchestrationTargetConfig::default()
        },
        workspace: OrchestrationWorkspaceConfig::default(),
        worker: OrchestrationWorkerConfig::default(),
        codex: OrchestrationCodexConfig::default(),
        procedures: OrchestrationProceduresConfig {
            pr_draft: Some(default_pr_draft_procedure()),
        },
        prompt_template: default_prompt_template(),
    }
}

fn default_pr_draft_procedure() -> OrchestrationProcedureConfig {
    OrchestrationProcedureConfig {
        runtime: "tactus".to_string(),
        file: None,
        source: Some(default_pr_draft_tactus_source()),
        command: None,
        timeout_seconds: 120,
    }
}

fn default_pr_draft_tactus_source() -> String {
    r#"Procedure {
    input = {
        evidence = field.object{required = true}
    },
    output = {
        title = field.string{required = true},
        body = field.string{required = true}
    },
    function(input)
        local evidence = input.evidence
        local issue = evidence.issue
        local run = evidence.run
        local git = evidence.git

        local title = run.commit_subject or issue.title
        if not string.match(title, "^[a-z]+%(.+%): ") and not string.match(title, "^[a-z]+: ") then
            title = "chore: " .. string.lower(string.sub(issue.title, 1, 1)) .. string.sub(issue.title, 2)
        end

        local changed_files = {}
        if git.changed_files ~= nil and git.changed_files ~= "" then
            for line in string.gmatch(git.changed_files, "[^\n]+") do
                table.insert(changed_files, "- `" .. line .. "`")
            end
        end
        if #changed_files == 0 then
            table.insert(changed_files, "- No changed files were reported.")
        end

        local validation_result = run.validation_summary
        if validation_result == nil or validation_result == "" then
            validation_result = "Completed without output."
        end

        local description = issue.description or "Implements the assigned Kanbus issue."
        if description == "" then
            description = "Implements the assigned Kanbus issue."
        end

        local body = table.concat({
            "**Summary**",
            "- " .. issue.title,
            table.concat(changed_files, "\n"),
            "",
            "**Why**",
            "- " .. description,
            "",
            "**Validation**",
            "- `" .. run.validation_command .. "`",
            "- Result: " .. validation_result,
            "",
            "**Expected Outcome**",
            "- The requested change is available on `" .. run.branch .. "` targeting `" .. run.target_branch .. "`.",
            "",
            "**Kanbus / Task Tracking**",
            "- Issue: `" .. issue.id .. "`",
            "- Run: `" .. run.id .. "`",
            "- Worker: `" .. run.worker_id .. "`",
            "- Commit: `" .. (run.commit_sha or "not recorded") .. "`"
        }, "\n")

        return {
            title = title,
            body = body
        }
    end
}
"#
    .to_string()
}

fn default_prompt_template() -> String {
    r#"You are working in an isolated workspace for the assigned Kanbus issue.

Issue:
- Identifier: {{ issue.identifier }}
- Run: {{ run.id }}
- Title: {{ issue.title }}
- Type: {{ issue.issue_type }}
- Description:
{{ issue.description }}

Rules:
- Use the issue title and description as the source of truth for the task.
- Work only in the isolated workspace supplied by Kanbus orchestration.
- The assigned Kanbus issue is supplied by the orchestrator. Do not create, update, or close Kanbus issues from inside the target workspace.
- You may comment only on the assigned Kanbus issue when useful.
- Do not modify files under project/issues, project/events, or project/runs.
- Do not run git add, git commit, git push, gh pr create, or merge. Kanbus orchestration handles publication after validation.
- Use only non-interactive commands. Do not start shell sessions or commands that require stdin.
- Keep changes scoped to the assigned issue.
- Run the validation that is appropriate for the change before finishing.
"#
    .to_string()
}

/// Resolve a workflow file path or repository-owned workflow preset name.
pub fn resolve_workflow_path(root: &Path, workflow: &Path) -> Result<PathBuf, KanbusError> {
    let explicit_path = if workflow.is_absolute() {
        workflow.to_path_buf()
    } else {
        root.join(workflow)
    };
    if explicit_path.is_file() {
        return Ok(explicit_path);
    }
    if workflow.is_absolute() || has_parent_component(workflow) {
        return Err(KanbusError::Configuration(format!(
            "workflow file not found: {}",
            workflow.display()
        )));
    }

    let mut preset_path = root.join("workflows").join(workflow);
    if preset_path.extension().is_none() {
        preset_path.set_extension("md");
    }
    if preset_path.is_file() {
        return Ok(preset_path);
    }
    Err(KanbusError::Configuration(format!(
        "workflow preset not found: {}",
        workflow.display()
    )))
}

/// Render the branch name for an issue.
pub fn render_branch_name(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    run: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    render_template(&workflow.worker.branch_pattern, issue, Some(run))
}

/// Render the worker prompt for an issue.
pub fn render_worker_prompt(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    run: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    let template = if workflow.prompt_template.trim().is_empty() {
        "You are working on Kanbus issue {{ issue.identifier }}: {{ issue.title }}."
    } else {
        workflow.prompt_template.as_str()
    };
    render_template(template, issue, Some(run))
}

/// Run a single worker for an issue.
pub fn run_worker(
    root: &Path,
    issue_id: &str,
    workflow_path: Option<&Path>,
    target_repo: Option<&str>,
    worker_id: &str,
) -> Result<OrchestrationRunRecord, KanbusError> {
    let workflow = load_workflow_or_default(root, workflow_path)?;
    validate_workspace_root(root, &workflow)?;
    let issue = load_issue_from_project(root, issue_id)?.issue;
    ensure_worker_owns_issue(&issue, worker_id)?;
    let mut record = create_run_record(root, issue_id, worker_id)?;
    let resolved_target_repo = resolve_target_repo(root, &workflow, target_repo);
    let result = run_worker_inner(
        root,
        &workflow,
        &issue,
        Some(resolved_target_repo.as_str()),
        &mut record,
    );
    match result {
        Ok(()) => {
            if run_is_cancelled(root, &record.run_id)? {
                return Err(KanbusError::IssueOperation("run cancelled".to_string()));
            }
            record.status = OrchestrationRunStatus::Completed;
            record.updated_at = Utc::now();
            record.last_event = Some("worker completed".to_string());
            write_run_record(root, &record)?;
            Ok(record)
        }
        Err(error) => {
            if run_is_cancelled(root, &record.run_id)? {
                return Err(KanbusError::IssueOperation("run cancelled".to_string()));
            }
            record.status = OrchestrationRunStatus::Failed;
            record.updated_at = Utc::now();
            record.error = Some(compact_error_message(&error.to_string()));
            record.last_event = Some("worker failed".to_string());
            write_run_record(root, &record)?;
            Err(error)
        }
    }
}

/// Run one orchestrator dispatch cycle.
pub fn run_orchestrator_once(
    root: &Path,
    workflow_path: Option<&Path>,
    max_concurrent: usize,
    issue_id: Option<&str>,
    worker_id: &str,
) -> Result<OrchestrationRunRecord, KanbusError> {
    if max_concurrent == 0 {
        return Err(KanbusError::IssueOperation(
            "max-concurrent must be greater than zero".to_string(),
        ));
    }
    let workflow = load_workflow_or_default(root, workflow_path)?;
    validate_workspace_root(root, &workflow)?;
    let (issue, mut record) = claim_and_create_run_record(root, issue_id, worker_id)?;
    let resolved_target_repo = resolve_target_repo(root, &workflow, None);
    let result = run_worker_inner(
        root,
        &workflow,
        &issue,
        Some(resolved_target_repo.as_str()),
        &mut record,
    );
    match result {
        Ok(()) => {
            if run_is_cancelled(root, &record.run_id)? {
                return Err(KanbusError::IssueOperation("run cancelled".to_string()));
            }
            record.status = OrchestrationRunStatus::Completed;
            record.updated_at = Utc::now();
            record.last_event = Some("worker completed".to_string());
            write_run_record(root, &record)?;
            Ok(record)
        }
        Err(error) => {
            if run_is_cancelled(root, &record.run_id)? {
                return Err(KanbusError::IssueOperation("run cancelled".to_string()));
            }
            record.status = OrchestrationRunStatus::Failed;
            record.updated_at = Utc::now();
            record.error = Some(compact_error_message(&error.to_string()));
            record.last_event = Some("worker failed".to_string());
            write_run_record(root, &record)?;
            Err(error)
        }
    }
}

fn resolve_target_repo<'a>(
    root: &'a Path,
    workflow: &'a OrchestrationWorkflow,
    target_repo: Option<&'a str>,
) -> String {
    let default_target_repo = root.to_string_lossy().to_string();
    target_repo
        .or(workflow.target.repo.as_deref())
        .unwrap_or(default_target_repo.as_str())
        .to_string()
}

fn ensure_worker_owns_issue(issue: &IssueData, worker_id: &str) -> Result<(), KanbusError> {
    if issue.status != "in_progress" {
        return Err(KanbusError::IssueOperation(
            "worker run requires issue status in_progress".to_string(),
        ));
    }
    if issue.assignee.as_deref() != Some(worker_id) {
        return Err(KanbusError::IssueOperation(format!(
            "worker run requires assignee {worker_id}"
        )));
    }
    Ok(())
}

fn run_is_cancelled(root: &Path, run_id: &str) -> Result<bool, KanbusError> {
    let record = show_run_record(root, run_id)?;
    Ok(record.status == OrchestrationRunStatus::Cancelled)
}

fn claim_and_create_run_record(
    root: &Path,
    issue_id: Option<&str>,
    worker_id: &str,
) -> Result<(IssueData, OrchestrationRunRecord), KanbusError> {
    let _lock = DispatchLock::acquire(root)?;
    let issue = if let Some(issue_id) = issue_id {
        claim_issue(root, issue_id, worker_id)?
    } else {
        claim_next_issue(root, true, worker_id)?
    };
    match create_run_record(root, &issue.identifier, worker_id) {
        Ok(record) => Ok((issue, record)),
        Err(error) => {
            let rollback = update_issue(
                root,
                &issue.identifier,
                None,
                None,
                Some("open"),
                Some(""),
                None,
                false,
                true,
                &[],
                &[],
                None,
                None,
                None,
            );
            match rollback {
                Ok(_) => Err(error),
                Err(rollback_error) => Err(KanbusError::IssueOperation(format!(
                    "failed to create run record after claim: {error}; rollback failed: {rollback_error}"
                ))),
            }
        }
    }
}

struct DispatchLock {
    path: PathBuf,
}

impl DispatchLock {
    fn acquire(root: &Path) -> Result<Self, KanbusError> {
        let lock_path = dispatch_lock_path(root)?;
        if let Some(parent) = lock_path.parent() {
            fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
        }
        let deadline = Instant::now() + Duration::from_secs(DISPATCH_LOCK_TIMEOUT_SECONDS);
        loop {
            match OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&lock_path)
            {
                Ok(mut file) => {
                    let _ = writeln!(file, "pid={} time={}", std::process::id(), Utc::now());
                    return Ok(Self { path: lock_path });
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    if Instant::now() >= deadline {
                        return Err(KanbusError::IssueOperation(
                            "orchestration dispatch is busy; retry after the active dispatch finishes".to_string(),
                        ));
                    }
                    std::thread::sleep(Duration::from_millis(DISPATCH_LOCK_POLL_MS));
                }
                Err(error) => {
                    return Err(KanbusError::Io(error.to_string()));
                }
            }
        }
    }
}

impl Drop for DispatchLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn dispatch_lock_path(root: &Path) -> Result<PathBuf, KanbusError> {
    Ok(load_project_directory(root)?.join(DISPATCH_LOCK_FILENAME))
}

fn has_parent_component(path: &Path) -> bool {
    path.components()
        .any(|component| matches!(component, Component::ParentDir))
}

fn run_worker_inner(
    root: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    target_repo: Option<&str>,
    record: &mut OrchestrationRunRecord,
) -> Result<(), KanbusError> {
    assert_run_not_cancelled(root, &record.run_id)?;
    record.status = OrchestrationRunStatus::Running;
    record.updated_at = Utc::now();
    record.last_event = Some("worker running".to_string());
    let branch = render_branch_name(workflow, issue, record)?;
    validate_worker_branch(&branch, &workflow.target.branch)?;
    let workspace = workspace_path(workflow, issue, record);
    record.workspace_path = Some(workspace.to_string_lossy().to_string());
    record.branch = Some(branch.clone());
    write_run_record(root, record)?;

    prepare_workspace(workflow, target_repo, &workspace, &branch)?;
    let capability = prepare_worker_capability_bridge(&workspace, issue, record)?;
    let worker_result =
        run_configured_worker(root, workflow, issue, record, &workspace, &capability);
    assert_run_not_cancelled(root, &record.run_id)?;
    apply_worker_comments(root, issue, record, &capability.comments_dir)?;
    record.last_event = Some(worker_result?);
    record.heartbeat_at = Some(Utc::now());
    write_run_record(root, record)?;

    assert_run_not_cancelled(root, &record.run_id)?;
    reject_project_management_artifact_changes(&workspace)?;
    reject_unallowed_publish_changes(&workspace, workflow)?;
    let validation = run_shell_command_with_env(
        &workspace,
        &workflow.target.validation,
        &orchestration_command_env(&capability),
    )?;
    record.validation_summary = Some(validation);
    reject_project_management_artifact_changes(&workspace)?;
    reject_unallowed_publish_changes(&workspace, workflow)?;
    let commit_sha = ensure_commit(&workspace, workflow, issue, record)?;
    record.commit_sha = Some(commit_sha);
    publish_run(&workspace, workflow, issue, record, &branch)?;
    Ok(())
}

fn assert_run_not_cancelled(root: &Path, run_id: &str) -> Result<(), KanbusError> {
    if run_is_cancelled(root, run_id)? {
        return Err(KanbusError::IssueOperation("run cancelled".to_string()));
    }
    Ok(())
}

fn run_configured_worker(
    root: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    workspace: &Path,
    capability: &WorkerCapabilityBridge,
) -> Result<String, KanbusError> {
    let prompt = render_worker_prompt(workflow, issue, record)?;
    let cancellation_probe = RunCancellationProbe::new(root, &record.run_id);
    match workflow.worker.runtime.trim() {
        "codex-app-server" | "codex" => run_codex_app_server(
            &workflow.codex.command,
            workspace,
            &prompt,
            &capability.bin_dir,
            workflow.codex.timeout_seconds,
            Some(&cancellation_probe),
        ),
        "tactus" => run_tactus_worker(root, workflow, issue, record, workspace, capability, &prompt),
        other => Err(KanbusError::Configuration(format!(
            "unsupported worker runtime {other:?}: supported runtimes are codex-app-server and tactus"
        ))),
    }
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

fn validate_workflow(workflow: &OrchestrationWorkflow) -> Result<(), KanbusError> {
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
    let runtime = workflow.worker.runtime.trim();
    if runtime != "codex-app-server" && runtime != "codex" && runtime != "tactus" {
        return Err(KanbusError::Configuration(format!(
            "unsupported worker runtime {:?}: supported runtimes are codex-app-server and tactus",
            workflow.worker.runtime
        )));
    }
    if runtime == "tactus" && workflow.worker.procedure.is_none() {
        return Err(KanbusError::Configuration(
            "worker.procedure is required when worker.runtime is tactus".to_string(),
        ));
    }
    if workflow.codex.command.trim().is_empty() {
        return Err(KanbusError::Configuration(
            "codex.command is required".to_string(),
        ));
    }
    let publish = workflow.target.publish.trim();
    if publish != "push-only" && publish != "pull-request" {
        return Err(KanbusError::Configuration(format!(
            "unsupported publish mode {:?}: supported modes are push-only and pull-request",
            workflow.target.publish
        )));
    }
    Ok(())
}

fn validate_workspace_root(
    kanbus_root: &Path,
    workflow: &OrchestrationWorkflow,
) -> Result<(), KanbusError> {
    let kanbus_root = normalize_absolute_path(kanbus_root, kanbus_root)?;
    let workspace_root = normalize_absolute_path(
        Path::new(&expand_home(&workflow.workspace.root)),
        kanbus_root.as_path(),
    )?;
    if workspace_root == kanbus_root || workspace_root.starts_with(&kanbus_root) {
        return Err(KanbusError::Configuration(
            "workspace root must be outside the Kanbus repository".to_string(),
        ));
    }
    Ok(())
}

fn validate_worker_branch(branch: &str, target_branch: &str) -> Result<(), KanbusError> {
    let branch = branch.trim();
    if !branch.starts_with("agent/") {
        return Err(KanbusError::Configuration(
            "worker branch must be under agent/".to_string(),
        ));
    }
    if branch == target_branch || matches!(branch, "develop" | "main" | "master") {
        return Err(KanbusError::Configuration(
            "worker branch must not target a protected branch".to_string(),
        ));
    }
    let ref_name = format!("refs/heads/{branch}");
    let output = Command::new("git")
        .args(["check-ref-format", &ref_name])
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !output.status.success() {
        return Err(KanbusError::Configuration(format!(
            "worker branch is not a valid git ref: {branch}"
        )));
    }
    Ok(())
}

fn normalize_absolute_path(path: &Path, base: &Path) -> Result<PathBuf, KanbusError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    };
    if absolute.exists() {
        return fs::canonicalize(&absolute).map_err(|error| KanbusError::Io(error.to_string()));
    }
    if let Some(parent) = absolute.parent() {
        if parent.exists() {
            let mut canonical =
                fs::canonicalize(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
            if let Some(name) = absolute.file_name() {
                canonical.push(name);
            }
            return Ok(canonical);
        }
    }
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    Ok(normalized)
}

fn render_template(
    template: &str,
    issue: &IssueData,
    run: Option<&OrchestrationRunRecord>,
) -> Result<String, KanbusError> {
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
    let run_value = run.map(|record| {
        json!({
            "id": record.run_id,
            "short_id": run_short_id(&record.run_id),
            "worker_id": record.worker_id
        })
    });
    template
        .render(json!({ "issue": issue_value, "run": run_value }))
        .map_err(|error| KanbusError::Configuration(error.to_string()))
}

fn project_key(root: &Path) -> Result<String, KanbusError> {
    let config_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&config_path)?;
    Ok(sanitize_identifier_segment(&configuration.project_key))
}

fn run_short_id(run_id: &str) -> String {
    let unique = run_id
        .split_once("-run-")
        .map(|(_, suffix)| suffix)
        .unwrap_or(run_id);
    unique.chars().take(8).collect()
}

fn runs_directory(root: &Path) -> Result<PathBuf, KanbusError> {
    Ok(load_project_directory(root)?.join("runs"))
}

fn run_record_path(root: &Path, run_id: &str) -> Result<PathBuf, KanbusError> {
    Ok(runs_directory(root)?.join(format!("{run_id}.json")))
}

fn write_run_record(root: &Path, record: &OrchestrationRunRecord) -> Result<(), KanbusError> {
    let runs_dir = runs_directory(root)?;
    fs::create_dir_all(&runs_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let path = runs_dir.join(format!("{}.json", record.run_id));
    let payload =
        serde_json::to_string_pretty(record).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(path, payload).map_err(|error| KanbusError::Io(error.to_string()))
}

fn read_run_record_from_path(path: &Path) -> Result<OrchestrationRunRecord, KanbusError> {
    let payload = fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    serde_json::from_str(&payload).map_err(|error| KanbusError::Io(error.to_string()))
}

fn workspace_path(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    run: &OrchestrationRunRecord,
) -> PathBuf {
    let root = expand_home(&workflow.workspace.root);
    PathBuf::from(root)
        .join(sanitize_path_segment(&issue.identifier))
        .join(sanitize_path_segment(&run.run_id))
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

fn sanitize_identifier_segment(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '-' {
                character.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

struct WorkerCapabilityBridge {
    bin_dir: PathBuf,
    comments_dir: PathBuf,
    env_dir: PathBuf,
    tactus_dir: PathBuf,
}

fn prepare_worker_capability_bridge(
    workspace: &Path,
    issue: &IssueData,
    run: &OrchestrationRunRecord,
) -> Result<WorkerCapabilityBridge, KanbusError> {
    let bridge_dir = workspace.with_extension("kanbus-capabilities");
    let bin_dir = bridge_dir.join("bin");
    let comments_dir = bridge_dir.join("comments");
    let env_dir = bridge_dir.join("env");
    let tactus_dir = bridge_dir.join("tactus");
    fs::create_dir_all(&bin_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::create_dir_all(&comments_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::create_dir_all(&env_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::create_dir_all(&tactus_dir).map_err(|error| KanbusError::Io(error.to_string()))?;

    let issue_json_path = bridge_dir.join("issue.json");
    let issue_text_path = bridge_dir.join("issue.txt");
    fs::write(
        &issue_json_path,
        serde_json::to_string_pretty(issue).map_err(|error| KanbusError::Io(error.to_string()))?,
    )
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(&issue_text_path, render_capability_issue_text(issue, run))
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    let wrapper =
        render_restricted_kanbus_wrapper(issue, &issue_json_path, &issue_text_path, &comments_dir);
    let kbs_path = bin_dir.join("kbs");
    let kanbus_path = bin_dir.join("kanbus");
    fs::write(&kbs_path, &wrapper).map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(&kanbus_path, &wrapper).map_err(|error| KanbusError::Io(error.to_string()))?;
    run_command(workspace, Command::new("chmod").arg("+x").arg(&kbs_path))?;
    run_command(workspace, Command::new("chmod").arg("+x").arg(&kanbus_path))?;
    install_worker_git_hooks(workspace)?;

    Ok(WorkerCapabilityBridge {
        bin_dir,
        comments_dir,
        env_dir,
        tactus_dir,
    })
}

fn orchestration_command_env(capability: &WorkerCapabilityBridge) -> Vec<(String, String)> {
    let env_dir = &capability.env_dir;
    vec![
        (
            "POETRY_VIRTUALENVS_IN_PROJECT".to_string(),
            "false".to_string(),
        ),
        (
            "POETRY_VIRTUALENVS_PATH".to_string(),
            env_dir.join("poetry-venvs").to_string_lossy().to_string(),
        ),
        (
            "POETRY_CACHE_DIR".to_string(),
            env_dir.join("poetry-cache").to_string_lossy().to_string(),
        ),
        (
            "PIP_CACHE_DIR".to_string(),
            env_dir.join("pip-cache").to_string_lossy().to_string(),
        ),
        (
            "UV_CACHE_DIR".to_string(),
            env_dir.join("uv-cache").to_string_lossy().to_string(),
        ),
    ]
}

fn render_capability_issue_text(issue: &IssueData, run: &OrchestrationRunRecord) -> String {
    format!(
        "ID: {}\nTitle: {}\nType: {}\nStatus: {}\nPriority: P{}\nAssignee: {}\nRun: {}\n\nDescription:\n{}\n",
        issue.identifier,
        issue.title,
        issue.issue_type,
        issue.status,
        issue.priority,
        issue.assignee.as_deref().unwrap_or("-"),
        run.run_id,
        issue.description
    )
}

fn render_restricted_kanbus_wrapper(
    issue: &IssueData,
    issue_json_path: &Path,
    issue_text_path: &Path,
    comments_dir: &Path,
) -> String {
    let issue_id = shell_quote(&issue.identifier);
    let short_id = shell_quote(&short_issue_identifier(&issue.identifier));
    let issue_json = shell_quote(&issue_json_path.to_string_lossy());
    let issue_text = shell_quote(&issue_text_path.to_string_lossy());
    let comments_dir = shell_quote(&comments_dir.to_string_lossy());
    format!(
        r#"#!/bin/sh
set -eu
assigned_issue={issue_id}
assigned_short={short_id}
issue_json={issue_json}
issue_text={issue_text}
comments_dir={comments_dir}

matches_issue() {{
  [ "${{1:-}}" = "$assigned_issue" ] || [ "${{1:-}}" = "$assigned_short" ]
}}

case "${{1:-}}" in
  show)
    shift
    json=0
    if [ "${{1:-}}" = "--json" ]; then
      json=1
      shift
    fi
    target="${{1:-$assigned_issue}}"
    if ! matches_issue "$target"; then
      echo "restricted Kanbus bridge can only show $assigned_issue" >&2
      exit 2
    fi
    if [ "$json" = "1" ]; then
      cat "$issue_json"
    else
      cat "$issue_text"
    fi
    ;;
  comment)
    shift
    target="${{1:-}}"
    if ! matches_issue "$target"; then
      echo "restricted Kanbus bridge can only comment on $assigned_issue" >&2
      exit 2
    fi
    shift
    if [ "${{1:-}}" = "--body-file" ]; then
      body_file="${{2:-}}"
      if [ -z "$body_file" ]; then
        echo "comment body file is required" >&2
        exit 2
      fi
      text="$(cat "$body_file")"
    else
      text="$*"
    fi
    if [ -z "$text" ]; then
      echo "comment text is required" >&2
      exit 2
    fi
    umask 077
    file="$comments_dir/$(date +%s)-$$.txt"
    printf '%s\n' "$text" > "$file"
    echo "queued comment for $assigned_issue"
    ;;
  help|--help|-h)
    echo "Restricted Kanbus bridge. Allowed: show $assigned_issue, comment $assigned_issue <text>."
    ;;
  *)
    echo "restricted Kanbus bridge allows only show/comment for $assigned_issue" >&2
    exit 2
    ;;
esac
"#
    )
}

fn short_issue_identifier(identifier: &str) -> String {
    let Some((prefix, rest)) = identifier.split_once('-') else {
        return identifier.to_string();
    };
    let short: String = rest.chars().take(6).collect();
    format!("{prefix}-{short}")
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn install_worker_git_hooks(workspace: &Path) -> Result<(), KanbusError> {
    let hooks_dir = workspace.join(".git").join("hooks");
    fs::create_dir_all(&hooks_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let hook_path = hooks_dir.join("pre-commit");
    fs::write(
        &hook_path,
        r#"#!/bin/sh
blocked="$(git diff --cached --name-only -- project/issues project/events project/runs)"
if [ -n "$blocked" ]; then
  echo "orchestrated workers must not commit Kanbus project artifacts:" >&2
  echo "$blocked" >&2
  exit 1
fi
"#,
    )
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    run_command(workspace, Command::new("chmod").arg("+x").arg(&hook_path))?;
    Ok(())
}

fn apply_worker_comments(
    root: &Path,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    comments_dir: &Path,
) -> Result<(), KanbusError> {
    if !comments_dir.exists() {
        return Ok(());
    }
    let mut entries = fs::read_dir(comments_dir)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    entries.sort_by_key(|entry| entry.path());
    for entry in entries {
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("txt") {
            continue;
        }
        let text = fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let text = text.trim();
        if text.is_empty() {
            continue;
        }
        add_comment(root, &issue.identifier, &record.worker_id, text)?;
    }
    Ok(())
}

fn prepare_workspace(
    workflow: &OrchestrationWorkflow,
    target_repo: Option<&str>,
    workspace: &Path,
    branch: &str,
) -> Result<(), KanbusError> {
    if !workspace.exists() {
        let repo = target_repo
            .or(workflow.target.repo.as_deref())
            .ok_or_else(|| KanbusError::Configuration("target.repo is required".to_string()))?;
        let source_origin = source_origin_url(repo);
        let parent = workspace.parent().ok_or_else(|| {
            KanbusError::Io(format!("workspace has no parent: {}", workspace.display()))
        })?;
        fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
        run_command(
            parent,
            Command::new("git").arg("clone").arg(repo).arg(workspace),
        )?;
        if let Some(origin_url) = source_origin {
            run_git(workspace, &["remote", "set-url", "origin", &origin_url])?;
        }
    }
    run_git(workspace, &["fetch", "origin", &workflow.target.branch])?;
    let upstream = format!("origin/{}", workflow.target.branch);
    run_git(workspace, &["checkout", "-B", branch, &upstream])?;
    run_git(workspace, &["reset", "--hard", &upstream])?;
    run_git(workspace, &["clean", "-ffdx"])?;
    Ok(())
}

fn source_origin_url(repo: &str) -> Option<String> {
    let repo_path = Path::new(repo);
    if !repo_path.exists() {
        return None;
    }
    let output = Command::new("git")
        .arg("-C")
        .arg(repo_path)
        .arg("remote")
        .arg("get-url")
        .arg("origin")
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let origin = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if origin.is_empty() {
        None
    } else {
        Some(origin)
    }
}

fn run_codex_app_server(
    command: &str,
    workspace: &Path,
    prompt: &str,
    path_prefix: &Path,
    timeout_seconds: u64,
    cancellation_probe: Option<&RunCancellationProbe>,
) -> Result<String, KanbusError> {
    let existing_path = std::env::var("PATH").unwrap_or_default();
    let worker_path = format!("{}:{existing_path}", path_prefix.to_string_lossy());
    let mut child = Command::new("sh")
        .arg("-lc")
        .arg(command)
        .current_dir(workspace)
        .env("PATH", worker_path)
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
    let (sender, receiver) = mpsc::channel();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        loop {
            match read_json_line(&mut reader) {
                Ok(value) => {
                    if sender.send(Ok(value)).is_err() {
                        break;
                    }
                }
                Err(error) => {
                    let _ = sender.send(Err(error));
                    break;
                }
            }
        }
    });
    let timeout = Duration::from_secs(timeout_seconds.max(1));
    let deadline = Instant::now() + timeout;

    send_json(
        &mut stdin,
        json!({
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "kanbus-orchestration",
                    "version": env!("GIT_VERSION")
                }
            }
        }),
    )?;
    read_response(&receiver, 1, deadline, &mut child, cancellation_probe)?;

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
    let thread_response = read_response(&receiver, 2, deadline, &mut child, cancellation_probe)?;
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
    read_response(&receiver, 3, deadline, &mut child, cancellation_probe)?;
    let last_event =
        read_until_turn_completed(&receiver, deadline, &mut child, cancellation_probe)?;
    let _ = child.kill();
    let _ = child.wait();
    Ok(last_event)
}

#[derive(Debug, Deserialize)]
struct TactusWorkerEvidence {
    status: String,
    #[serde(default)]
    summary: Option<String>,
    #[serde(default)]
    changed_files: Vec<String>,
    #[serde(default)]
    notes: Vec<String>,
}

fn run_tactus_worker(
    root: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    workspace: &Path,
    capability: &WorkerCapabilityBridge,
    prompt: &str,
) -> Result<String, KanbusError> {
    let procedure = workflow.worker.procedure.as_ref().ok_or_else(|| {
        KanbusError::Configuration(
            "worker.procedure is required when worker.runtime is tactus".to_string(),
        )
    })?;
    let (source, source_file_path) = load_worker_procedure_source(root, procedure)?;
    let storage_dir = capability
        .tactus_dir
        .join("worker")
        .to_string_lossy()
        .to_string();
    let worker_input = worker_procedure_input(workflow, issue, record, workspace, prompt)?;
    let command_env: serde_json::Map<String, Value> = orchestration_command_env(capability)
        .into_iter()
        .map(|(key, value)| (key, Value::String(value)))
        .collect();
    let python = procedure.command.as_deref().unwrap_or("python");
    let script = tactus_worker_python_runner();
    let input = json!({
        "source": source,
        "source_file_path": source_file_path,
        "storage_dir": storage_dir,
        "command_env": command_env,
        "worker_input": worker_input,
        "workspace": workspace.to_string_lossy(),
        "comments_dir": capability.comments_dir.to_string_lossy(),
        "path_prefix": capability.bin_dir.to_string_lossy(),
    });
    let input_json =
        serde_json::to_string(&input).map_err(|error| KanbusError::Io(error.to_string()))?;
    let command = format!("{} -c '{}'", python, shell_single_quote(&script));
    let output =
        run_shell_command_with_stdin(workspace, &command, &input_json, procedure.timeout_seconds)?;
    let evidence = parse_tactus_worker_evidence(&output)?;
    if evidence.status.trim() != "completed" && evidence.status.trim() != "success" {
        return Err(KanbusError::IssueOperation(format!(
            "Tactus worker did not complete successfully: {}",
            evidence.status
        )));
    }
    let summary = evidence
        .summary
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("Tactus worker completed");
    Ok(format!(
        "tactus/completed: {summary}; changed_files={}; notes={}",
        evidence.changed_files.len(),
        evidence.notes.len()
    ))
}

fn load_worker_procedure_source(
    root: &Path,
    procedure: &OrchestrationProcedureConfig,
) -> Result<(String, Option<String>), KanbusError> {
    if let Some(source) = procedure.source.as_deref() {
        return Ok((source.to_string(), procedure.file.clone()));
    }
    let file = procedure.file.as_deref().ok_or_else(|| {
        KanbusError::Configuration("worker.procedure.file is required".to_string())
    })?;
    let file_path = if Path::new(file).is_absolute() {
        PathBuf::from(file)
    } else {
        root.join(file)
    };
    let source = fs::read_to_string(&file_path).map_err(|error| {
        KanbusError::Io(format!("failed to read worker procedure file: {error}"))
    })?;
    Ok((source, Some(file_path.to_string_lossy().to_string())))
}

fn worker_procedure_input(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    workspace: &Path,
    prompt: &str,
) -> Result<Value, KanbusError> {
    Ok(json!({
        "issue": serde_json::to_value(issue).map_err(|error| KanbusError::Io(error.to_string()))?,
        "repo_policy": {
            "target_branch": workflow.target.branch,
            "validation": workflow.target.validation,
            "publish": workflow.target.publish,
            "allowed_paths": workflow.target.allowed_paths,
        },
        "workspace": {
            "path": workspace.to_string_lossy(),
        },
        "run": {
            "id": record.run_id,
            "worker_id": record.worker_id,
            "branch": record.branch,
        },
        "prompt": prompt,
    }))
}

fn parse_tactus_worker_evidence(output: &str) -> Result<TactusWorkerEvidence, KanbusError> {
    let value: Value = serde_json::from_str(output.trim()).map_err(|error| {
        KanbusError::IssueOperation(format!("Tactus worker returned invalid JSON: {error}"))
    })?;
    serde_json::from_value(value).map_err(|error| {
        KanbusError::IssueOperation(format!("Tactus worker returned invalid evidence: {error}"))
    })
}

fn tactus_worker_python_runner() -> String {
    r#"
import asyncio
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from tactus.adapters.file_storage import FileStorage
from tactus.core.runtime import TactusRuntime
from tactus.protocols.result import TactusResult

payload = json.load(sys.stdin)
workspace = Path(payload["workspace"]).resolve()
comments_dir = Path(payload["comments_dir"]).resolve()
path_prefix = payload["path_prefix"]
command_env = {str(key): str(value) for key, value in payload.get("command_env", {}).items()}

def guarded_path(path):
    if path is None:
        raise ValueError("path is required")
    raw = str(path)
    if raw.startswith("/") or raw.startswith("~"):
        raise ValueError("paths must be repository-relative")
    resolved = (workspace / raw).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError("path escapes workspace")
    relative = resolved.relative_to(workspace).as_posix()
    if relative == ".git" or relative.startswith(".git/"):
        raise ValueError(".git is not writable by worker tools")
    if relative == ".kanbus" or relative.startswith(".kanbus/"):
        raise ValueError(".kanbus runtime state is not writable by worker tools")
    if (
        relative == "project/issues"
        or relative.startswith("project/issues/")
        or relative == "project/events"
        or relative.startswith("project/events/")
        or relative == "project/runs"
        or relative.startswith("project/runs/")
    ):
        raise ValueError("Kanbus project artifacts are not writable by worker tools")
    return resolved

def check_command(command):
    parts = shlex.split(command)
    if not parts:
        raise ValueError("command is required")
    executable = Path(parts[0]).name
    subcommand = parts[1] if len(parts) > 1 else ""
    if executable == "git" and subcommand in {
        "add", "commit", "push", "reset", "checkout", "clean", "merge",
        "rebase", "tag", "branch", "rm", "mv", "switch", "restore",
    }:
        raise ValueError(f"git {subcommand} is reserved for Kanbus orchestration")
    if executable == "gh":
        raise ValueError("GitHub publication is reserved for Kanbus orchestration")
    if executable in {"kbs", "kanbus"} and subcommand not in {"show", "comment", "help", "--help", "-h"}:
        raise ValueError("Kanbus mutation is reserved for Kanbus orchestration")

class KanbusHost:
    def read_file(self, path):
        return guarded_path(path).read_text()

    def create_file(self, path, content):
        target = guarded_path(path)
        if target.exists():
            raise ValueError("create_file cannot overwrite an existing file")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content))
        return {"ok": True, "path": str(path)}

    def append_text(self, path, text):
        target = guarded_path(path)
        if not target.is_file():
            raise ValueError("append_text requires an existing file")
        with target.open("a") as handle:
            handle.write(str(text))
        return {"ok": True, "path": str(path)}

    def replace_text(self, path, old_text, new_text):
        target = guarded_path(path)
        if not target.is_file():
            raise ValueError("replace_text requires an existing file")
        old_text = str(old_text)
        if old_text == "":
            raise ValueError("old_text is required")
        content = target.read_text()
        count = content.count(old_text)
        if count != 1:
            raise ValueError(f"old_text must appear exactly once; found {count}")
        target.write_text(content.replace(old_text, str(new_text), 1))
        return {"ok": True, "path": str(path)}

    def list_files(self, path=""):
        root = guarded_path(path or ".")
        if root.is_file():
            return [root.relative_to(workspace).as_posix()]
        results = []
        for candidate in sorted(root.rglob("*")):
            if candidate.is_file():
                relative = candidate.relative_to(workspace).as_posix()
                if not relative.startswith(".git/") and not relative.startswith(".kanbus/"):
                    results.append(relative)
        return results

    def run_command(self, command, timeout_seconds=120):
        check_command(str(command))
        env = os.environ.copy()
        env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
        env.update(command_env)
        completed = subprocess.run(
            str(command),
            cwd=workspace,
            shell=True,
            text=True,
            capture_output=True,
            timeout=int(timeout_seconds or 120),
            env=env,
        )
        return {
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "success": completed.returncode == 0,
        }

    def comment(self, text):
        comments_dir.mkdir(parents=True, exist_ok=True)
        comment_path = comments_dir / f"tactus-{len(list(comments_dir.glob('*.txt'))) + 1}.txt"
        comment_path.write_text(str(text).strip() + "\n")
        return {"ok": True}

storage = FileStorage(storage_dir=payload["storage_dir"])
run_id = payload["worker_input"]["run"]["id"]
runtime = TactusRuntime(
    procedure_id=f"kanbus-worker-{run_id}",
    storage_backend=storage,
    run_id=run_id,
    source_file_path=payload.get("source_file_path"),
)
runtime.register_python_module("kanbus", KanbusHost())
result = asyncio.run(runtime.execute(
    payload["source"],
    payload["worker_input"],
    format="lua",
))
if not result.get("success"):
    raise SystemExit(result.get("error") or "Tactus worker procedure failed")
output = result.get("result")
if isinstance(output, TactusResult):
    output = output.output
print(json.dumps(output))
"#
    .to_string()
}

fn send_json(stdin: &mut impl Write, value: Value) -> Result<(), KanbusError> {
    let line = serde_json::to_string(&value).map_err(|error| KanbusError::Io(error.to_string()))?;
    writeln!(stdin, "{line}").map_err(|error| KanbusError::Io(error.to_string()))?;
    stdin
        .flush()
        .map_err(|error| KanbusError::Io(error.to_string()))
}

fn read_response(
    receiver: &mpsc::Receiver<Result<Value, KanbusError>>,
    expected_id: i64,
    deadline: Instant,
    child: &mut std::process::Child,
    cancellation_probe: Option<&RunCancellationProbe>,
) -> Result<Value, KanbusError> {
    loop {
        let value = receive_app_server_value(receiver, deadline, child, cancellation_probe)?;
        if value.get("id").and_then(Value::as_i64) != Some(expected_id) {
            continue;
        }
        if let Some(error) = value.get("error") {
            return Err(KanbusError::ProtocolError(error.to_string()));
        }
        return Ok(value);
    }
}

fn read_until_turn_completed(
    receiver: &mpsc::Receiver<Result<Value, KanbusError>>,
    deadline: Instant,
    child: &mut std::process::Child,
    cancellation_probe: Option<&RunCancellationProbe>,
) -> Result<String, KanbusError> {
    loop {
        let value = receive_app_server_value(receiver, deadline, child, cancellation_probe)?;
        let method = value.get("method").and_then(Value::as_str).unwrap_or("");
        if method == "error" {
            return Err(KanbusError::ProtocolError(value.to_string()));
        }
        if method == "turn/completed" {
            return Ok("turn/completed".to_string());
        }
    }
}

fn receive_app_server_value(
    receiver: &mpsc::Receiver<Result<Value, KanbusError>>,
    deadline: Instant,
    child: &mut std::process::Child,
    cancellation_probe: Option<&RunCancellationProbe>,
) -> Result<Value, KanbusError> {
    loop {
        let Some(remaining) = deadline.checked_duration_since(Instant::now()) else {
            let _ = child.kill();
            let _ = child.wait();
            return Err(KanbusError::ProtocolError(
                "codex app-server turn timed out".to_string(),
            ));
        };
        let wait = remaining.min(Duration::from_millis(APP_SERVER_POLL_MS));
        match receiver.recv_timeout(wait) {
            Ok(result) => return result,
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if let Some(probe) = cancellation_probe {
                    if probe.is_cancelled()? {
                        let _ = child.kill();
                        let _ = child.wait();
                        return Err(KanbusError::IssueOperation("run cancelled".to_string()));
                    }
                }
                continue;
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                let _ = child.wait();
                return Err(KanbusError::ProtocolError(
                    "app-server closed stdout".to_string(),
                ));
            }
        }
    }
}

struct RunCancellationProbe {
    root: PathBuf,
    run_id: String,
}

impl RunCancellationProbe {
    fn new(root: &Path, run_id: &str) -> Self {
        Self {
            root: root.to_path_buf(),
            run_id: run_id.to_string(),
        }
    }

    fn is_cancelled(&self) -> Result<bool, KanbusError> {
        run_is_cancelled(&self.root, &self.run_id)
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

fn run_shell_command_with_env(
    workspace: &Path,
    command: &str,
    env: &[(String, String)],
) -> Result<String, KanbusError> {
    let mut shell = Command::new("sh");
    shell.arg("-lc").arg(command);
    for (key, value) in env {
        shell.env(key, value);
    }
    run_command(workspace, &mut shell)
}

fn run_shell_command_with_stdin(
    workspace: &Path,
    command: &str,
    stdin_text: &str,
    timeout_seconds: u64,
) -> Result<String, KanbusError> {
    let mut child = Command::new("sh")
        .arg("-lc")
        .arg(command)
        .current_dir(workspace)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(stdin_text.as_bytes())
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let deadline = Instant::now() + Duration::from_secs(timeout_seconds);
    loop {
        if child
            .try_wait()
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .is_some()
        {
            let output = child
                .wait_with_output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            if !output.status.success() {
                return Err(KanbusError::IssueOperation(command_failure_message(
                    &stdout, &stderr,
                )));
            }
            return Ok(stdout);
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(KanbusError::IssueOperation(format!(
                "procedure command timed out after {timeout_seconds} seconds"
            )));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
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
        return Err(KanbusError::IssueOperation(command_failure_message(
            &stdout, &stderr,
        )));
    }
    Ok(stdout)
}

fn command_failure_message(stdout: &str, stderr: &str) -> String {
    let stdout = compact_output_stream(stdout);
    let stderr = compact_output_stream(stderr);
    match (stdout.is_empty(), stderr.is_empty()) {
        (true, true) => "command failed without output".to_string(),
        (false, true) => stdout,
        (true, false) => stderr,
        (false, false) => format!("stdout:\n{stdout}\nstderr:\n{stderr}"),
    }
}

fn compact_output_stream(output: &str) -> String {
    const MAX_STREAM_CHARS: usize = 800;
    let mut compact = output
        .lines()
        .filter(|line| !line.trim().is_empty())
        .rev()
        .take(20)
        .collect::<Vec<_>>();
    compact.reverse();
    let compact = compact.join("\n");
    if compact.chars().count() <= MAX_STREAM_CHARS {
        return compact;
    }
    let tail = compact
        .chars()
        .rev()
        .take(MAX_STREAM_CHARS)
        .collect::<String>()
        .chars()
        .rev()
        .collect::<String>();
    format!("...{tail}")
}

fn compact_error_message(message: &str) -> String {
    const MAX_ERROR_CHARS: usize = 2000;
    let mut compact = message
        .lines()
        .filter(|line| !line.trim().is_empty())
        .rev()
        .take(40)
        .collect::<Vec<_>>();
    compact.reverse();
    let compact = compact.join("\n");
    if compact.chars().count() <= MAX_ERROR_CHARS {
        return compact;
    }
    let mut truncated = compact
        .chars()
        .rev()
        .take(MAX_ERROR_CHARS)
        .collect::<Vec<_>>();
    truncated.reverse();
    format!("...{}", truncated.into_iter().collect::<String>())
}

fn ensure_commit(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    let status = run_git(workspace, &["status", "--porcelain"])?;
    if !status.trim().is_empty() {
        run_git(workspace, &["add", "."])?;
        let message = commit_message(workflow, issue, record)?;
        run_git(
            workspace,
            &[
                "-c",
                "user.name=Kanbus Orchestration",
                "-c",
                "user.email=kanbus-orchestration@example.invalid",
                "commit",
                "-m",
                &message,
            ],
        )?;
    }
    run_git(workspace, &["rev-parse", "HEAD"])
}

fn publish_run(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &mut OrchestrationRunRecord,
    branch: &str,
) -> Result<(), KanbusError> {
    run_git(workspace, &["push", "-u", "origin", branch])?;
    record.remote_branch = Some(branch.to_string());
    if workflow.target.publish.trim() == "pull-request" {
        record.pull_request_url = Some(create_pull_request(
            workspace, workflow, issue, record, branch,
        )?);
    }
    Ok(())
}

fn create_pull_request(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    branch: &str,
) -> Result<String, KanbusError> {
    let draft = pull_request_draft(workspace, workflow, issue, record, branch)?;
    run_gh(
        workspace,
        &[
            "pr",
            "create",
            "--base",
            &workflow.target.branch,
            "--head",
            branch,
            "--title",
            &draft.title,
            "--body",
            &draft.body,
        ],
    )
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct PullRequestDraft {
    title: String,
    body: String,
}

fn pull_request_draft(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    branch: &str,
) -> Result<PullRequestDraft, KanbusError> {
    let draft = if let Some(procedure) = workflow.procedures.pr_draft.as_ref() {
        run_pr_draft_procedure(workspace, workflow, issue, record, branch, procedure)?
    } else {
        PullRequestDraft {
            title: pull_request_title(workflow, issue, record)?,
            body: pull_request_body(workflow, issue, record)?,
        }
    };
    validate_pull_request_draft(workspace, workflow, issue, record, &draft)?;
    Ok(draft)
}

fn commit_message(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    render_publication_template(
        workflow.target.commit_message.as_deref(),
        &conventional_issue_subject(issue),
        issue,
        record,
    )
}

fn pull_request_title(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    render_publication_template(
        workflow.target.pr_title.as_deref(),
        &conventional_issue_subject(issue),
        issue,
        record,
    )
}

fn pull_request_body(
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    let default_body = format!(
        "**Summary**\n- {}\n\n**Why**\n- Implements the assigned Kanbus issue.\n\n**Validation**\n- `{}`\n\n**Expected Outcome**\n- The requested change is available from the published branch.\n\n**Kanbus / Task Tracking**\n- Issue: `{}`\n- Run: `{}`\n- Worker: `{}`",
        issue.description.trim(),
        workflow.target.validation,
        issue.identifier,
        record.run_id,
        record.worker_id
    );
    render_publication_template(
        workflow.target.pr_body.as_deref(),
        &default_body,
        issue,
        record,
    )
}

fn render_publication_template(
    template: Option<&str>,
    default_value: &str,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
) -> Result<String, KanbusError> {
    let value = template.unwrap_or(default_value);
    render_template(value, issue, Some(record))
}

fn conventional_issue_subject(issue: &IssueData) -> String {
    if looks_like_conventional_commit(&issue.title) {
        return issue.title.clone();
    }
    let prefix = match issue.issue_type.as_str() {
        "bug" => "fix",
        "story" | "feature" | "epic" => "feat",
        _ => "chore",
    };
    format!("{}: {}", prefix, sentence_case_title(&issue.title))
}

fn looks_like_conventional_commit(title: &str) -> bool {
    let Some((prefix, _)) = title.split_once(':') else {
        return false;
    };
    let base = prefix
        .split_once('(')
        .map(|(base, _)| base)
        .unwrap_or(prefix);
    matches!(
        base,
        "feat"
            | "fix"
            | "docs"
            | "style"
            | "refactor"
            | "perf"
            | "test"
            | "build"
            | "ci"
            | "chore"
            | "revert"
    )
}

fn sentence_case_title(title: &str) -> String {
    let mut chars = title.chars();
    let Some(first) = chars.next() else {
        return String::new();
    };
    first.to_lowercase().chain(chars).collect()
}

fn run_pr_draft_procedure(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    branch: &str,
    procedure: &OrchestrationProcedureConfig,
) -> Result<PullRequestDraft, KanbusError> {
    let evidence = pr_evidence(workspace, workflow, issue, record, branch)?;
    let evidence_json =
        serde_json::to_string(&evidence).map_err(|error| KanbusError::Io(error.to_string()))?;
    let output = match procedure.runtime.trim() {
        "command" => run_pr_draft_command(workspace, procedure, &evidence_json)?,
        "tactus" => run_tactus_pr_draft(workspace, procedure, &evidence_json)?,
        other => {
            return Err(KanbusError::Configuration(format!(
                "unsupported pr_draft procedure runtime: {other}"
            )));
        }
    };
    parse_pull_request_draft(&output)
}

fn pr_evidence(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    branch: &str,
) -> Result<Value, KanbusError> {
    let base_ref = format!("origin/{}", workflow.target.branch);
    let changed_files = run_git(workspace, &["diff", "--name-status", &base_ref, "HEAD"])?;
    let diff_stat = run_git(workspace, &["diff", "--stat", &base_ref, "HEAD"])?;
    let commit_subject = run_git(workspace, &["log", "-1", "--pretty=%s"])?;
    Ok(json!({
        "issue": {
            "id": issue.identifier,
            "short_id": short_issue_identifier(&issue.identifier),
            "title": issue.title,
            "description": issue.description,
            "type": issue.issue_type,
            "status": issue.status,
        },
        "run": {
            "id": record.run_id,
            "worker_id": record.worker_id,
            "commit_sha": record.commit_sha,
            "branch": branch,
            "target_branch": workflow.target.branch,
            "validation_command": workflow.target.validation,
            "validation_summary": record.validation_summary,
            "commit_subject": commit_subject,
        },
        "git": {
            "changed_files": changed_files,
            "diff_stat": diff_stat,
        },
        "required_sections": [
            "**Summary**",
            "**Why**",
            "**Validation**",
            "**Expected Outcome**",
            "**Kanbus / Task Tracking**"
        ],
        "policy": {
            "title": "Use Conventional Commit style.",
            "body": "Use only repository-relative paths. Do not invent validation. Include the issue id and run id."
        }
    }))
}

fn run_pr_draft_command(
    workspace: &Path,
    procedure: &OrchestrationProcedureConfig,
    evidence_json: &str,
) -> Result<String, KanbusError> {
    let command = procedure.command.as_deref().ok_or_else(|| {
        KanbusError::Configuration("procedures.pr_draft.command is required".to_string())
    })?;
    run_shell_command_with_stdin(workspace, command, evidence_json, procedure.timeout_seconds)
}

fn run_tactus_pr_draft(
    workspace: &Path,
    procedure: &OrchestrationProcedureConfig,
    evidence_json: &str,
) -> Result<String, KanbusError> {
    let (source, source_file_path) = if let Some(source) = procedure.source.as_deref() {
        (source.to_string(), procedure.file.clone())
    } else {
        let file = procedure.file.as_deref().ok_or_else(|| {
            KanbusError::Configuration("procedures.pr_draft.file is required".to_string())
        })?;
        let file_path = if Path::new(file).is_absolute() {
            PathBuf::from(file)
        } else {
            workspace.join(file)
        };
        let source = fs::read_to_string(&file_path).map_err(|error| {
            KanbusError::Io(format!("failed to read pr_draft procedure file: {error}"))
        })?;
        (source, Some(file_path.to_string_lossy().to_string()))
    };
    let storage_dir = workspace
        .with_extension("kanbus-capabilities")
        .join("tactus")
        .join("pr-draft")
        .to_string_lossy()
        .to_string();
    let python = procedure.command.as_deref().unwrap_or("python");
    let script = r#"
import asyncio
import json
import sys
from tactus.adapters.file_storage import FileStorage
from tactus.core.runtime import TactusRuntime
from tactus.protocols.result import TactusResult

payload = json.load(sys.stdin)
source = payload["source"]
source_file_path = payload.get("source_file_path")
evidence = payload["evidence"]
run_id = evidence["run"]["id"]
storage = FileStorage(storage_dir=payload["storage_dir"])
runtime = TactusRuntime(
    procedure_id=f"kanbus-pr-draft-{run_id}",
    storage_backend=storage,
    run_id=run_id,
    source_file_path=source_file_path,
)
result = asyncio.run(runtime.execute(
    source,
    {"evidence": evidence},
    format="lua",
))
if not result.get("success"):
    raise SystemExit(result.get("error") or "Tactus procedure failed")
output = result.get("result")
if isinstance(output, TactusResult):
    output = output.output
print(json.dumps(output))
"#;
    let input = json!({
        "source": source,
        "source_file_path": source_file_path,
        "storage_dir": storage_dir,
        "evidence": serde_json::from_str::<Value>(evidence_json)
            .map_err(|error| KanbusError::Io(error.to_string()))?
    });
    let input_json =
        serde_json::to_string(&input).map_err(|error| KanbusError::Io(error.to_string()))?;
    let command = format!("{} -c '{}'", python, shell_single_quote(script));
    run_shell_command_with_stdin(workspace, &command, &input_json, procedure.timeout_seconds)
}

fn parse_pull_request_draft(output: &str) -> Result<PullRequestDraft, KanbusError> {
    let value: Value = serde_json::from_str(output.trim()).map_err(|error| {
        KanbusError::IssueOperation(format!("pr_draft procedure returned invalid JSON: {error}"))
    })?;
    serde_json::from_value(value).map_err(|error| {
        KanbusError::IssueOperation(format!(
            "pr_draft procedure returned invalid draft: {error}"
        ))
    })
}

fn validate_pull_request_draft(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
    issue: &IssueData,
    record: &OrchestrationRunRecord,
    draft: &PullRequestDraft,
) -> Result<(), KanbusError> {
    let title = draft.title.trim();
    if title.is_empty() || title.contains('\n') {
        return Err(KanbusError::IssueOperation(
            "PR title must be one non-empty line".to_string(),
        ));
    }
    if !looks_like_conventional_commit(title) {
        return Err(KanbusError::IssueOperation(
            "PR title must use Conventional Commit style".to_string(),
        ));
    }
    let required_sections = [
        "**Summary**",
        "**Why**",
        "**Validation**",
        "**Expected Outcome**",
        "**Kanbus / Task Tracking**",
    ];
    for section in required_sections {
        if !draft.body.contains(section) {
            return Err(KanbusError::IssueOperation(format!(
                "PR body missing required section {section}"
            )));
        }
    }
    if !draft.body.contains(&issue.identifier) || !draft.body.contains(&record.run_id) {
        return Err(KanbusError::IssueOperation(
            "PR body must include the Kanbus issue id and run id".to_string(),
        ));
    }
    if !draft.body.contains(&workflow.target.validation) {
        return Err(KanbusError::IssueOperation(
            "PR body must include the validation command Kanbus ran".to_string(),
        ));
    }
    let workspace_text = workspace.to_string_lossy();
    if draft.body.contains("/Users/")
        || draft.body.contains("C:\\")
        || (!workspace_text.is_empty() && draft.body.contains(workspace_text.as_ref()))
    {
        return Err(KanbusError::IssueOperation(
            "PR body must not contain absolute local paths".to_string(),
        ));
    }
    Ok(())
}

fn shell_single_quote(value: &str) -> String {
    value.replace('\'', "'\"'\"'")
}

fn run_gh(workspace: &Path, args: &[&str]) -> Result<String, KanbusError> {
    let mut command = Command::new("gh");
    command.args(args);
    run_command(workspace, &mut command)
}

fn reject_project_management_artifact_changes(workspace: &Path) -> Result<(), KanbusError> {
    let status = run_git(
        workspace,
        &["status", "--porcelain", "--untracked-files=all"],
    )?;
    let forbidden_paths: Vec<String> = status
        .lines()
        .filter_map(project_management_artifact_path)
        .collect();
    if forbidden_paths.is_empty() {
        return Ok(());
    }
    Err(KanbusError::IssueOperation(format!(
        "orchestrated workers must not modify Kanbus artifacts: {}",
        forbidden_paths.join(", ")
    )))
}

fn project_management_artifact_path(status_line: &str) -> Option<String> {
    let path = porcelain_status_path(status_line)?;
    let path = path.split(" -> ").last().unwrap_or(path);
    if path.starts_with("project/issues/")
        || path.starts_with("project/events/")
        || path.starts_with("project/runs/")
        || path == ".kanbus"
        || path.starts_with(".kanbus/")
    {
        Some(path.to_string())
    } else {
        None
    }
}

fn reject_unallowed_publish_changes(
    workspace: &Path,
    workflow: &OrchestrationWorkflow,
) -> Result<(), KanbusError> {
    if workflow.target.allowed_paths.is_empty() {
        return Ok(());
    }
    let status = run_git(
        workspace,
        &["status", "--porcelain", "--untracked-files=all"],
    )?;
    let changed_paths: Vec<String> = status.lines().filter_map(git_status_path).collect();
    let unallowed_paths: Vec<String> = changed_paths
        .into_iter()
        .filter(|path| !is_allowed_publish_path(path, &workflow.target.allowed_paths))
        .collect();
    if unallowed_paths.is_empty() {
        return Ok(());
    }
    Err(KanbusError::IssueOperation(format!(
        "orchestrated worker changed files outside allowed publish paths: {}",
        unallowed_paths.join(", ")
    )))
}

fn git_status_path(status_line: &str) -> Option<String> {
    let path = porcelain_status_path(status_line)?;
    Some(path.split(" -> ").last().unwrap_or(path).to_string())
}

fn porcelain_status_path(status_line: &str) -> Option<&str> {
    status_line
        .get(2..)
        .map(|path| path.trim().trim_matches('"'))
}

fn is_allowed_publish_path(path: &str, allowed_paths: &[String]) -> bool {
    allowed_paths.iter().any(|allowed_path| {
        let allowed_path = allowed_path.trim().trim_matches('/');
        path == allowed_path || path.starts_with(&format!("{allowed_path}/"))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn create_test_issue(root: &Path, title: &str, status: &str) -> IssueData {
        let request = crate::issue_creation::IssueCreationRequest {
            root: root.to_path_buf(),
            title: title.to_string(),
            issue_type: Some("task".to_string()),
            priority: Some(0),
            assignee: None,
            parent: None,
            labels: Vec::new(),
            description: Some("Description".to_string()),
            local: false,
            validate: true,
        };
        let issue = crate::issue_creation::create_issue(&request)
            .expect("create issue")
            .issue;
        if status == "open" {
            return issue;
        }
        update_issue(
            root,
            &issue.identifier,
            None,
            None,
            Some(status),
            None,
            None,
            false,
            true,
            &[],
            &[],
            None,
            None,
            None,
        )
        .expect("update issue status")
    }

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

    fn run_record(run_id: &str) -> OrchestrationRunRecord {
        OrchestrationRunRecord {
            run_id: run_id.to_string(),
            issue_id: "kanbus-123".to_string(),
            worker_id: "worker-one".to_string(),
            status: OrchestrationRunStatus::Claimed,
            workspace_path: None,
            branch: None,
            started_at: Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap(),
            updated_at: Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap(),
            heartbeat_at: None,
            last_event: None,
            commit_sha: None,
            remote_branch: None,
            pull_request_url: None,
            validation_summary: None,
            error: None,
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
        assert_eq!(workflow.target.validation, "git diff --check");
        assert_eq!(workflow.prompt_template, "Hello {{ issue.identifier }}");
    }

    #[test]
    fn missing_workflow_uses_builtin_generic_workflow() {
        let temp = tempfile::tempdir().expect("tempdir");

        let workflow = load_workflow_or_default(temp.path(), None).expect("default workflow");

        assert_eq!(workflow.target.repo, None);
        assert_eq!(workflow.target.publish, "pull-request");
        assert_eq!(
            workflow
                .procedures
                .pr_draft
                .as_ref()
                .expect("pr draft")
                .runtime,
            "tactus"
        );
        let source = workflow
            .procedures
            .pr_draft
            .as_ref()
            .expect("pr draft")
            .source
            .as_deref()
            .expect("source");
        assert!(source.contains("local evidence = input.evidence"));
        assert!(source.contains("local changed_files = {}"));
        assert!(source.contains("Completed without output."));
        assert!(!source.contains("Agent {"));
        assert!(workflow.prompt_template.contains("{{ issue.description }}"));
    }

    #[test]
    fn repository_orchestration_config_overlays_builtin_workflow() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("initialize project");
        let config_path = temp.path().join(".kanbus.yml");
        let mut configuration =
            load_project_configuration(&config_path).expect("load default configuration");
        configuration.orchestration = Some(
            serde_yaml::from_str(
                r#"
target:
  validation: poetry check --lock
worker:
  branch_pattern: agent/{{ issue.identifier }}/repo-config
"#,
            )
            .expect("orchestration value"),
        );
        fs::write(
            &config_path,
            serde_yaml::to_string(&configuration).expect("serialize config"),
        )
        .expect("write config");

        let workflow = load_workflow_or_default(temp.path(), None).expect("repo workflow");

        assert_eq!(workflow.target.validation, "poetry check --lock");
        assert_eq!(
            workflow.worker.branch_pattern,
            "agent/{{ issue.identifier }}/repo-config"
        );
        assert_eq!(workflow.target.publish, "pull-request");
        assert_eq!(
            workflow
                .procedures
                .pr_draft
                .as_ref()
                .expect("default pr draft procedure")
                .runtime,
            "tactus"
        );
        assert!(workflow.prompt_template.contains("{{ issue.description }}"));
    }

    #[test]
    fn tactus_worker_runtime_requires_procedure_config() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("workflow.md");
        fs::write(
            &workflow_path,
            "---\nworker:\n  runtime: tactus\n---\nUse Tactus.",
        )
        .expect("write workflow");

        let error = load_workflow(&workflow_path).expect_err("workflow error");

        assert!(error.to_string().contains("worker.procedure is required"));
    }

    #[test]
    fn unsupported_worker_runtime_is_rejected() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("workflow.md");
        fs::write(
            &workflow_path,
            "---\nworker:\n  runtime: shell-agent\n---\nUse agent.",
        )
        .expect("write workflow");

        let error = load_workflow(&workflow_path).expect_err("workflow error");

        assert!(error.to_string().contains("unsupported worker runtime"));
    }

    #[test]
    fn tactus_worker_receives_structured_input_and_isolated_storage() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workspace = temp.path().join("workspace");
        fs::create_dir_all(&workspace).expect("workspace");
        let comments_dir = temp.path().join("comments");
        let bin_dir = temp.path().join("bin");
        let env_dir = temp
            .path()
            .join("workspace.kanbus-capabilities")
            .join("env");
        let tactus_dir = temp
            .path()
            .join("workspace.kanbus-capabilities")
            .join("tactus");
        fs::create_dir_all(&comments_dir).expect("comments");
        fs::create_dir_all(&bin_dir).expect("bin");
        fs::create_dir_all(&env_dir).expect("env");
        fs::create_dir_all(&tactus_dir).expect("tactus");
        let fake_python = temp.path().join("fake-python");
        fs::write(
            &fake_python,
            r#"#!/bin/sh
if [ "$1" != "-c" ]; then
  echo "expected -c" >&2
  exit 1
fi
script="$2"
payload=$(cat)
case "$script" in
  *"runtime.register_python_module(\"kanbus\", KanbusHost())"*) ;;
  *) echo "missing Kanbus host module" >&2; exit 2 ;;
esac
case "$payload" in
  *"\"storage_dir\":\""*".kanbus-capabilities/tactus/worker\""*) ;;
  *) echo "missing isolated worker storage" >&2; exit 3 ;;
esac
case "$payload" in
  *"\"POETRY_VIRTUALENVS_IN_PROJECT\":\"false\""*) ;;
  *) echo "missing external poetry venv policy" >&2; exit 31 ;;
esac
case "$payload" in
  *"\"POETRY_VIRTUALENVS_PATH\":\""*".kanbus-capabilities/env/poetry-venvs\""*) ;;
  *) echo "missing external poetry venv path" >&2; exit 32 ;;
esac
case "$payload" in
  *"\"id\":\"ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554\""*) ;;
  *) echo "missing issue id" >&2; exit 4 ;;
esac
case "$payload" in
  *"\"validation\":\"make test\""*) ;;
  *) echo "missing validation policy" >&2; exit 5 ;;
esac
case "$payload" in
  *"\"path_prefix\":\""*"/bin\""*) ;;
  *) echo "missing bridge path prefix" >&2; exit 6 ;;
esac
printf '{"status":"completed","summary":"fake tactus worker","changed_files":["README.md"],"notes":[]}\n'
"#,
        )
        .expect("write fake python");
        run_command(
            temp.path(),
            Command::new("chmod").arg("+x").arg(&fake_python),
        )
        .expect("chmod");
        let workflow = OrchestrationWorkflow {
            target: OrchestrationTargetConfig {
                validation: "make test".to_string(),
                ..OrchestrationTargetConfig::default()
            },
            worker: OrchestrationWorkerConfig {
                runtime: "tactus".to_string(),
                procedure: Some(OrchestrationProcedureConfig {
                    runtime: "tactus".to_string(),
                    file: None,
                    source: Some("Procedure {}".to_string()),
                    command: Some(fake_python.to_string_lossy().to_string()),
                    timeout_seconds: 5,
                }),
                ..OrchestrationWorkerConfig::default()
            },
            ..default_orchestration_workflow()
        };
        let issue = issue("ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554");
        let mut record = run_record("ccpy-run-12345678");
        record.branch = Some("agent/ccpy-d2fd1d/12345678".to_string());
        let capability = WorkerCapabilityBridge {
            bin_dir,
            comments_dir,
            env_dir,
            tactus_dir,
        };

        let event = run_tactus_worker(
            temp.path(),
            &workflow,
            &issue,
            &record,
            &workspace,
            &capability,
            "worker prompt",
        )
        .expect("run fake Tactus worker");

        assert!(event.contains("tactus/completed"));
        assert!(event.contains("fake tactus worker"));
    }

    #[test]
    fn generic_tactus_worker_uses_constrained_edit_tools() {
        let repo_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("repo root");
        let source = fs::read_to_string(repo_root.join("workflows/kanbus-worker.tac"))
            .expect("read worker procedure");

        assert!(source.contains("append_text = Tool"));
        assert!(source.contains("replace_text = Tool"));
        assert!(source.contains("create_file = Tool"));
        assert!(source.contains(
            "tools = {read_file, append_text, replace_text, create_file, list_files, run_command, comment_on_task, done}"
        ));
        assert!(!source.contains("tools = {read_file, write_file"));
    }

    #[test]
    fn explicit_workflow_file_overrides_repository_orchestration_config() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("initialize project");
        let config_path = temp.path().join(".kanbus.yml");
        let mut configuration =
            load_project_configuration(&config_path).expect("load default configuration");
        configuration.orchestration = Some(
            serde_yaml::from_str(
                r#"
target:
  validation: poetry check --lock
"#,
            )
            .expect("orchestration value"),
        );
        fs::write(
            &config_path,
            serde_yaml::to_string(&configuration).expect("serialize config"),
        )
        .expect("write config");
        let workflow_path = temp.path().join("workflow.md");
        fs::write(
            &workflow_path,
            "---\ntarget:\n  validation: cargo test\n---\nUse file workflow.",
        )
        .expect("write workflow");

        let workflow = load_workflow_or_default(temp.path(), Some(Path::new("workflow.md")))
            .expect("workflow");

        assert_eq!(workflow.target.validation, "cargo test");
        assert_eq!(workflow.prompt_template, "Use file workflow.");
    }

    #[test]
    fn invalid_repository_orchestration_config_fails_clearly() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("initialize project");
        let config_path = temp.path().join(".kanbus.yml");
        let mut configuration =
            load_project_configuration(&config_path).expect("load default configuration");
        configuration.orchestration = Some(
            serde_yaml::from_str(
                r#"
target:
  publish: merge-direct
"#,
            )
            .expect("orchestration value"),
        );
        fs::write(
            &config_path,
            serde_yaml::to_string(&configuration).expect("serialize config"),
        )
        .expect("write config");

        let error = load_workflow_or_default(temp.path(), None).expect_err("invalid workflow");

        assert!(error.to_string().contains("unsupported publish mode"));
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
    fn explicit_issue_claims_only_requested_issue() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("init");
        let untouched_issue = create_test_issue(temp.path(), "Trial issue one", "open");
        let requested_issue = create_test_issue(temp.path(), "Trial issue two", "open");

        let claimed = claim_issue(temp.path(), &requested_issue.identifier, "worker-one")
            .expect("claim issue");

        assert_eq!(claimed.identifier, requested_issue.identifier);
        assert_eq!(claimed.status, "in_progress");
        assert_eq!(claimed.assignee.as_deref(), Some("worker-one"));
        let untouched = load_issue_from_project(temp.path(), &untouched_issue.identifier)
            .expect("load untouched")
            .issue;
        assert_eq!(untouched.status, "open");
        assert_eq!(untouched.assignee, None);
    }

    #[test]
    fn explicit_issue_rejects_non_open_issue() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("init");
        let issue = create_test_issue(temp.path(), "Trial issue", "in_progress");

        let error =
            claim_issue(temp.path(), &issue.identifier, "worker-one").expect_err("claim error");

        assert_eq!(error.to_string(), "explicit issue is not open");
    }

    #[test]
    fn worker_run_requires_issue_owned_by_worker() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("init");
        let issue = create_test_issue(temp.path(), "Trial issue", "open");

        let error =
            run_worker(temp.path(), &issue.identifier, None, None, "worker-one").expect_err("run");

        assert_eq!(
            error.to_string(),
            "worker run requires issue status in_progress"
        );
    }

    #[test]
    fn run_creation_failure_rolls_back_claimed_issue() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("init");
        let issue = create_test_issue(temp.path(), "Trial issue", "open");

        let project_dir = load_project_directory(temp.path()).expect("project dir");
        let runs_path = project_dir.join("runs");
        if runs_path.exists() {
            if runs_path.is_dir() {
                fs::remove_dir_all(&runs_path).expect("remove runs dir");
            } else {
                fs::remove_file(&runs_path).expect("remove runs file");
            }
        }
        fs::write(&runs_path, "blocked").expect("write runs blocker file");

        let error = run_orchestrator_once(
            temp.path(),
            None,
            1,
            Some(issue.identifier.as_str()),
            "worker-one",
        )
        .expect_err("orchestrator failure");

        let message = error.to_string();
        assert!(
            message.contains("Not a directory") || message.contains("File exists"),
            "unexpected error: {error}"
        );
        let rolled_back = load_issue_from_project(temp.path(), &issue.identifier)
            .expect("load issue")
            .issue;
        assert_eq!(rolled_back.status, "open");
        assert_eq!(rolled_back.assignee.as_deref(), Some(""));
    }

    #[test]
    fn project_management_artifact_status_lines_are_detected() {
        assert_eq!(
            project_management_artifact_path("?? project/events/event.json").as_deref(),
            Some("project/events/event.json")
        );
        assert_eq!(
            project_management_artifact_path(" M project/issues/issue.json").as_deref(),
            Some("project/issues/issue.json")
        );
        assert_eq!(
            project_management_artifact_path("R  old.json -> project/runs/run.json").as_deref(),
            Some("project/runs/run.json")
        );
        assert_eq!(
            project_management_artifact_path("?? .kanbus/tactus/worker/state.json").as_deref(),
            Some(".kanbus/tactus/worker/state.json")
        );
        assert_eq!(
            git_status_path("AM poetry.lock").as_deref(),
            Some("poetry.lock")
        );
        assert_eq!(project_management_artifact_path(" M pyproject.toml"), None);
    }

    #[test]
    fn publish_allowed_paths_match_exact_files_and_directories() {
        let allowed_paths = vec!["pyproject.toml".to_string(), "docs".to_string()];

        assert!(is_allowed_publish_path("pyproject.toml", &allowed_paths));
        assert!(is_allowed_publish_path("docs/guide.md", &allowed_paths));
        assert!(!is_allowed_publish_path("poetry.lock", &allowed_paths));
        assert!(!is_allowed_publish_path(
            "docs-other/file.md",
            &allowed_paths
        ));
    }

    #[test]
    fn orchestration_command_environment_keeps_dependency_state_outside_checkout() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workspace = temp.path().join("workspace");
        let capability = WorkerCapabilityBridge {
            bin_dir: temp.path().join("workspace.kanbus-capabilities/bin"),
            comments_dir: temp.path().join("workspace.kanbus-capabilities/comments"),
            env_dir: temp.path().join("workspace.kanbus-capabilities/env"),
            tactus_dir: temp.path().join("workspace.kanbus-capabilities/tactus"),
        };

        let env = orchestration_command_env(&capability);

        assert!(env
            .iter()
            .any(|(key, value)| key == "POETRY_VIRTUALENVS_IN_PROJECT" && value == "false"));
        for (key, value) in env {
            if key.ends_with("_DIR") || key == "POETRY_VIRTUALENVS_PATH" {
                assert!(
                    !Path::new(&value).starts_with(&workspace),
                    "{key} should not be inside worker checkout"
                );
            }
        }
    }

    #[test]
    fn command_failure_message_preserves_stdout_and_stderr() {
        let message = command_failure_message("test failure", "installer warning");

        assert!(message.contains("stdout:\ntest failure"));
        assert!(message.contains("stderr:\ninstaller warning"));
    }

    #[test]
    fn command_failure_message_keeps_stdout_when_stderr_is_verbose() {
        let stderr = (0..200)
            .map(|index| format!("installer warning {index}"))
            .collect::<Vec<_>>()
            .join("\n");

        let message = command_failure_message("real validation failure", &stderr);

        assert!(message.contains("stdout:\nreal validation failure"));
        assert!(message.contains("installer warning 199"));
        assert!(!message.contains("installer warning 0"));
    }

    #[test]
    fn short_issue_identifiers_use_project_prefix_and_six_id_chars() {
        assert_eq!(
            short_issue_identifier("ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554"),
            "ccpy-d2fd1d"
        );
    }

    #[test]
    fn worker_comments_are_applied_to_assigned_issue() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("init");
        let issue = create_test_issue(temp.path(), "Trial issue", "open");
        let record = OrchestrationRunRecord {
            issue_id: issue.identifier.clone(),
            worker_id: "worker-one".to_string(),
            ..run_record("kanbus-run-12345678")
        };
        let comments_dir = temp.path().join("comments");
        fs::create_dir_all(&comments_dir).expect("comments dir");
        fs::write(comments_dir.join("1.txt"), "progress note").expect("comment");

        apply_worker_comments(temp.path(), &issue, &record, &comments_dir).expect("apply comments");

        let updated = load_issue_from_project(temp.path(), &issue.identifier)
            .expect("load issue")
            .issue;
        assert_eq!(updated.comments.len(), 1);
        assert_eq!(updated.comments[0].author, "worker-one");
        assert_eq!(updated.comments[0].text, "progress note");
    }

    #[test]
    fn named_workflow_presets_resolve_from_repository_workflows() {
        let temp = tempfile::tempdir().expect("tempdir");
        let preset_path = temp.path().join("workflows").join("default.md");
        fs::create_dir_all(preset_path.parent().expect("parent")).expect("create preset parent");
        fs::write(&preset_path, "---\n---\nBody").expect("write preset");

        let resolved =
            resolve_workflow_path(temp.path(), Path::new("default")).expect("resolve preset");

        assert_eq!(resolved, preset_path);
    }

    #[test]
    fn missing_named_workflow_presets_fail_clearly() {
        let temp = tempfile::tempdir().expect("tempdir");

        let error =
            resolve_workflow_path(temp.path(), Path::new("missing/workflow")).expect_err("error");

        assert_eq!(
            error.to_string(),
            "workflow preset not found: missing/workflow"
        );
    }

    #[test]
    fn explicit_relative_workflow_paths_are_resolved_from_repo_root() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("workflow.md");
        fs::write(&workflow_path, "---\n---\nBody").expect("write workflow");

        let resolved =
            resolve_workflow_path(temp.path(), Path::new("workflow.md")).expect("resolve workflow");

        assert_eq!(resolved, workflow_path);
    }

    #[test]
    fn pull_request_publish_mode_is_supported() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("WORKFLOW.md");
        fs::write(
            &workflow_path,
            "---\ntarget:\n  publish: pull-request\n---\nBody",
        )
        .expect("write workflow");

        let workflow = load_workflow(&workflow_path).expect("load workflow");

        assert_eq!(workflow.target.publish, "pull-request");
    }

    #[test]
    fn pull_request_metadata_is_rendered_from_issue_and_run() {
        let issue = issue("ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554");
        let record = run_record("ccpy-run-12345678");
        let workflow = OrchestrationWorkflow {
            procedures: OrchestrationProceduresConfig::default(),
            ..default_orchestration_workflow()
        };

        assert_eq!(
            commit_message(&workflow, &issue, &record).expect("commit message"),
            "chore: trial issue"
        );
        assert_eq!(
            pull_request_title(&workflow, &issue, &record).expect("pr title"),
            "chore: trial issue"
        );
        assert!(pull_request_body(&workflow, &issue, &record)
            .expect("pr body")
            .contains("ccpy-run-12345678"));
        assert!(pull_request_body(&workflow, &issue, &record)
            .expect("pr body")
            .contains("worker-one"));
    }

    #[test]
    fn conventional_commit_titles_are_preserved() {
        let mut issue = issue("ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554");
        issue.title = "fix(parser): handle missing values".to_string();

        assert_eq!(
            conventional_issue_subject(&issue),
            "fix(parser): handle missing values"
        );
    }

    #[test]
    fn pr_drafts_require_policy_sections_and_tracking() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issue = issue("ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554");
        let record = run_record("ccpy-run-12345678");
        let workflow = OrchestrationWorkflow {
            procedures: OrchestrationProceduresConfig::default(),
            ..default_orchestration_workflow()
        };
        let draft = PullRequestDraft {
            title: "chore: generated title".to_string(),
            body: format!(
                "**Summary**\n- Done\n\n**Why**\n- Needed\n\n**Validation**\n- `{}`\n\n**Expected Outcome**\n- Works\n\n**Kanbus / Task Tracking**\n- `{}`\n- `{}`",
                workflow.target.validation, issue.identifier, record.run_id
            ),
        };

        validate_pull_request_draft(temp.path(), &workflow, &issue, &record, &draft)
            .expect("valid draft");

        let invalid = PullRequestDraft {
            title: "Generated title".to_string(),
            body: draft.body,
        };
        let error = validate_pull_request_draft(temp.path(), &workflow, &issue, &record, &invalid)
            .expect_err("invalid title");

        assert!(error.to_string().contains("Conventional Commit"));
    }

    #[test]
    fn pr_drafts_reject_absolute_local_paths() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issue = issue("ccpy-d2fd1dff-b73c-48cc-809e-f8b84408a554");
        let record = run_record("ccpy-run-12345678");
        let workflow = OrchestrationWorkflow {
            procedures: OrchestrationProceduresConfig::default(),
            ..default_orchestration_workflow()
        };
        let draft = PullRequestDraft {
            title: "chore: generated title".to_string(),
            body: format!(
                "**Summary**\n- Changed /Users/derek/project/file.rs\n\n**Why**\n- Needed\n\n**Validation**\n- `{}`\n\n**Expected Outcome**\n- Works\n\n**Kanbus / Task Tracking**\n- `{}`\n- `{}`",
                workflow.target.validation, issue.identifier, record.run_id
            ),
        };

        let error = validate_pull_request_draft(temp.path(), &workflow, &issue, &record, &draft)
            .expect_err("absolute path");

        assert!(error.to_string().contains("absolute local paths"));
    }

    #[test]
    fn tactus_pr_draft_receives_isolated_storage() {
        let temp = tempfile::tempdir().expect("tempdir");
        let fake_python = temp.path().join("fake-python");
        fs::write(
            &fake_python,
            r#"#!/bin/sh
if [ "$1" != "-c" ]; then
  echo "expected -c" >&2
  exit 1
fi
script="$2"
payload=$(cat)
case "$script" in
  *"from tactus.adapters.file_storage import FileStorage"*) ;;
  *) echo "missing FileStorage import" >&2; exit 2 ;;
esac
case "$script" in
  *"storage_backend=storage"*) ;;
  *) echo "missing storage backend" >&2; exit 3 ;;
esac
case "$script" in
  *"run_id=run_id"*) ;;
  *) echo "missing run id" >&2; exit 4 ;;
esac
case "$payload" in
  *"\"storage_dir\":\""*".kanbus-capabilities/tactus/pr-draft\""*) ;;
  *) echo "missing isolated storage dir" >&2; exit 5 ;;
esac
case "$payload" in
  *"\"id\":\"ccpy-run-12345678\""*) ;;
  *) echo "missing evidence run id" >&2; exit 6 ;;
esac
printf '{"title":"chore: generated title","body":"body"}\n'
"#,
        )
        .expect("write fake python");
        run_command(
            temp.path(),
            Command::new("chmod").arg("+x").arg(&fake_python),
        )
        .expect("chmod");

        let procedure = OrchestrationProcedureConfig {
            runtime: "tactus".to_string(),
            file: None,
            source: Some("Procedure {}".to_string()),
            command: Some(fake_python.to_string_lossy().to_string()),
            timeout_seconds: 5,
        };
        let evidence = json!({
            "run": {
                "id": "ccpy-run-12345678"
            }
        })
        .to_string();

        let output = run_tactus_pr_draft(temp.path(), &procedure, &evidence)
            .expect("run fake Tactus procedure");

        assert!(output.contains("chore: generated title"));
    }

    #[test]
    fn local_source_origin_url_is_preserved_when_available() {
        let temp = tempfile::tempdir().expect("tempdir");
        let repo = temp.path().join("repo");
        fs::create_dir_all(&repo).expect("repo dir");
        run_command(&repo, Command::new("git").arg("init")).expect("git init");
        run_command(
            &repo,
            Command::new("git")
                .arg("remote")
                .arg("add")
                .arg("origin")
                .arg("https://github.com/AnthusAI/Call-Criteria-Python.git"),
        )
        .expect("add origin");

        assert_eq!(
            source_origin_url(repo.to_str().expect("repo path")).as_deref(),
            Some("https://github.com/AnthusAI/Call-Criteria-Python.git")
        );
        assert_eq!(
            source_origin_url("https://github.com/AnthusAI/Call-Criteria-Python.git"),
            None
        );
    }

    #[test]
    fn run_errors_are_compacted_to_recent_context() {
        let verbose = (0..200)
            .map(|index| format!("line {index}"))
            .collect::<Vec<_>>()
            .join("\n");

        let compact = compact_error_message(&verbose);

        assert!(!compact.contains("line 0"));
        assert!(compact.contains("line 199"));
        assert!(compact.chars().count() <= 2003);
    }

    #[test]
    fn unsupported_publish_mode_is_rejected() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow_path = temp.path().join("WORKFLOW.md");
        fs::write(
            &workflow_path,
            "---\ntarget:\n  publish: merge-direct\n---\nBody",
        )
        .expect("write workflow");

        let error = load_workflow(&workflow_path).expect_err("workflow error");

        assert!(error.to_string().contains("unsupported publish mode"));
    }

    #[test]
    fn workspace_root_inside_kanbus_repository_is_rejected() {
        let temp = tempfile::tempdir().expect("tempdir");
        let workflow = OrchestrationWorkflow {
            workspace: OrchestrationWorkspaceConfig {
                root: temp
                    .path()
                    .join("unsafe-workspaces")
                    .to_string_lossy()
                    .to_string(),
            },
            ..OrchestrationWorkflow {
                target: OrchestrationTargetConfig::default(),
                workspace: OrchestrationWorkspaceConfig::default(),
                worker: OrchestrationWorkerConfig::default(),
                codex: OrchestrationCodexConfig::default(),
                procedures: OrchestrationProceduresConfig::default(),
                prompt_template: String::new(),
            }
        };

        let error = validate_workspace_root(temp.path(), &workflow).expect_err("workspace error");

        assert_eq!(
            error.to_string(),
            "workspace root must be outside the Kanbus repository"
        );
    }

    #[test]
    fn worker_branch_must_use_agent_namespace() {
        let error = validate_worker_branch("feature/work", "develop").expect_err("branch error");

        assert_eq!(error.to_string(), "worker branch must be under agent/");
    }

    #[test]
    fn worker_branch_must_not_target_protected_branch() {
        let error = validate_worker_branch("agent/run", "agent/run").expect_err("branch error");

        assert_eq!(
            error.to_string(),
            "worker branch must not target a protected branch"
        );
    }

    #[test]
    fn branch_names_are_rendered_from_issue_context() {
        let workflow = OrchestrationWorkflow {
            worker: OrchestrationWorkerConfig {
                branch_pattern: "agent/{{ issue.identifier }}/{{ run.short_id }}".to_string(),
                ..OrchestrationWorkerConfig::default()
            },
            ..OrchestrationWorkflow {
                target: OrchestrationTargetConfig::default(),
                workspace: OrchestrationWorkspaceConfig::default(),
                worker: OrchestrationWorkerConfig::default(),
                codex: OrchestrationCodexConfig::default(),
                procedures: OrchestrationProceduresConfig::default(),
                prompt_template: String::new(),
            }
        };

        let branch = render_branch_name(
            &workflow,
            &issue("kanbus-123"),
            &run_record("kanbus-run-12345678-90ab-cdef-1234-567890abcdef"),
        )
        .expect("branch");

        assert_eq!(branch, "agent/kanbus-123/12345678");
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
            temp.path(),
            5,
            None,
        )
        .expect("run fake app server");

        assert_eq!(event, "turn/completed");
    }

    #[test]
    fn app_server_client_stops_when_run_is_cancelled() {
        let temp = tempfile::tempdir().expect("tempdir");
        crate::file_io::initialize_project(temp.path(), false).expect("init");
        let issue = create_test_issue(temp.path(), "Trial issue", "open");
        let mut record =
            create_run_record(temp.path(), &issue.identifier, "worker-one").expect("run record");
        record.status = OrchestrationRunStatus::Running;
        write_run_record(temp.path(), &record).expect("write running run");

        let fake = temp.path().join("fake-app-server-slow.sh");
        fs::write(
            &fake,
            r#"#!/bin/sh
sleep 30
"#,
        )
        .expect("write fake");
        run_command(temp.path(), Command::new("chmod").arg("+x").arg(&fake)).expect("chmod");

        let root = temp.path().to_path_buf();
        let run_id = record.run_id.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(300));
            cancel_run_record(&root, &run_id).expect("cancel run");
        });

        let probe = RunCancellationProbe::new(temp.path(), &record.run_id);
        let started = Instant::now();
        let error = run_codex_app_server(
            &fake.to_string_lossy(),
            temp.path(),
            "perform a harmless task",
            temp.path(),
            20,
            Some(&probe),
        )
        .expect_err("run cancelled");

        assert_eq!(error.to_string(), "run cancelled");
        assert!(started.elapsed() < Duration::from_secs(5));
    }
}
