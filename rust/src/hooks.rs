//! Lifecycle hook runtime and built-in providers.

use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use chrono::{SecondsFormat, Utc};
use serde_json::{json, Value};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::models::{HookDefinition, HooksConfiguration, IssueData};
use crate::rich_text_signals::emit_stderr_line;
use crate::users::get_current_user;

const HOOK_SCHEMA_VERSION: &str = "kanbus.hooks.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum HookPhase {
    Before,
    After,
}

impl HookPhase {
    fn as_str(self) -> &'static str {
        match self {
            HookPhase::Before => "before",
            HookPhase::After => "after",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum HookEvent {
    IssueCreate,
    IssueUpdate,
    IssueClose,
    IssueDelete,
    IssueComment,
    IssueDependency,
    IssuePromote,
    IssueLocalize,
    IssueShow,
    IssueList,
    IssueReady,
}

impl HookEvent {
    pub fn as_str(self) -> &'static str {
        match self {
            HookEvent::IssueCreate => "issue.create",
            HookEvent::IssueUpdate => "issue.update",
            HookEvent::IssueClose => "issue.close",
            HookEvent::IssueDelete => "issue.delete",
            HookEvent::IssueComment => "issue.comment",
            HookEvent::IssueDependency => "issue.dependency",
            HookEvent::IssuePromote => "issue.promote",
            HookEvent::IssueLocalize => "issue.localize",
            HookEvent::IssueShow => "issue.show",
            HookEvent::IssueList => "issue.list",
            HookEvent::IssueReady => "issue.ready",
        }
    }

    fn parse(value: &str) -> Option<Self> {
        match value {
            "issue.create" => Some(HookEvent::IssueCreate),
            "issue.update" => Some(HookEvent::IssueUpdate),
            "issue.close" => Some(HookEvent::IssueClose),
            "issue.delete" => Some(HookEvent::IssueDelete),
            "issue.comment" => Some(HookEvent::IssueComment),
            "issue.dependency" => Some(HookEvent::IssueDependency),
            "issue.promote" => Some(HookEvent::IssuePromote),
            "issue.localize" => Some(HookEvent::IssueLocalize),
            "issue.show" => Some(HookEvent::IssueShow),
            "issue.list" => Some(HookEvent::IssueList),
            "issue.ready" => Some(HookEvent::IssueReady),
            _ => None,
        }
    }

    fn is_mutating(self) -> bool {
        matches!(
            self,
            HookEvent::IssueCreate
                | HookEvent::IssueUpdate
                | HookEvent::IssueClose
                | HookEvent::IssueDelete
                | HookEvent::IssueComment
                | HookEvent::IssueDependency
                | HookEvent::IssuePromote
                | HookEvent::IssueLocalize
        )
    }
}

#[derive(Debug, Clone, Copy)]
pub struct HookExecutionOptions {
    pub beads_mode: bool,
    pub no_hooks: bool,
    pub no_guidance: bool,
}

#[derive(Debug, Clone)]
struct HookResult {
    succeeded: bool,
    timed_out: bool,
    exit_code: Option<i32>,
    duration_ms: u64,
    message: String,
}

#[derive(Debug, Clone)]
pub struct HookListRow {
    pub source: String,
    pub phase: String,
    pub event: String,
    pub id: String,
    pub command: String,
    pub blocking: bool,
    pub timeout_ms: Option<u64>,
}

pub fn hooks_globally_disabled(no_hooks: bool) -> bool {
    if no_hooks {
        return true;
    }
    let raw = std::env::var("KANBUS_NO_HOOKS")
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    matches!(raw.as_str(), "1" | "true" | "yes" | "on")
}

pub fn serialize_issue(issue: &IssueData) -> Value {
    serde_json::to_value(issue).unwrap_or(Value::Null)
}

pub fn list_hooks(root: &Path) -> Vec<HookListRow> {
    let (hooks_config, _) = resolve_hook_configuration(root);
    let mut rows = Vec::new();

    for (phase, map) in [
        (HookPhase::Before, &hooks_config.before),
        (HookPhase::After, &hooks_config.after),
    ] {
        for (event_name, hooks) in map {
            let event = HookEvent::parse(event_name.as_str());
            for hook in hooks {
                let timeout_ms = hook.timeout_ms.or(Some(hooks_config.default_timeout_ms));
                rows.push(HookListRow {
                    source: "external".to_string(),
                    phase: phase.as_str().to_string(),
                    event: event_name.clone(),
                    id: hook.id.clone(),
                    command: hook.command.join(" "),
                    blocking: effective_blocking(phase, event, hook),
                    timeout_ms,
                });
            }
        }
    }

    for event in policy_event_map().keys() {
        rows.push(HookListRow {
            source: "built-in".to_string(),
            phase: HookPhase::After.as_str().to_string(),
            event: event.as_str().to_string(),
            id: "policy-guidance".to_string(),
            command: "<built-in>".to_string(),
            blocking: false,
            timeout_ms: None,
        });
    }

    rows
}

pub fn validate_hooks(root: &Path) -> Vec<String> {
    let (hooks_config, project_root) = resolve_hook_configuration(root);
    let mut issues = Vec::new();

    for (phase_name, event_map) in [
        (HookPhase::Before.as_str(), &hooks_config.before),
        (HookPhase::After.as_str(), &hooks_config.after),
    ] {
        for (event_name, hooks) in event_map {
            let event = HookEvent::parse(event_name.as_str());
            if event.is_none() {
                issues.push(format!("hooks.{phase_name}.{event_name}: unknown event"));
                continue;
            }
            if hooks.is_empty() {
                issues.push(format!("hooks.{phase_name}.{event_name}: empty hook list"));
                continue;
            }

            let mut seen = HashSet::new();
            for hook in hooks {
                if !seen.insert(hook.id.clone()) {
                    issues.push(format!(
                        "hooks.{phase_name}.{event_name}: duplicate hook id '{}'",
                        hook.id
                    ));
                }

                let Some(executable) = hook.command.first() else {
                    issues.push(format!(
                        "hooks.{phase_name}.{event_name}.{}: command is empty",
                        hook.id
                    ));
                    continue;
                };

                if looks_like_path(executable) {
                    let candidate = Path::new(executable);
                    let resolved = if candidate.is_absolute() {
                        candidate.to_path_buf()
                    } else {
                        project_root.join(candidate)
                    };
                    if !resolved.exists() {
                        issues.push(format!(
                            "hooks.{phase_name}.{event_name}.{}: command not found at {}",
                            hook.id,
                            resolved.display()
                        ));
                    }
                } else if !command_on_path(executable) {
                    issues.push(format!(
                        "hooks.{phase_name}.{event_name}.{}: command '{}' is not on PATH",
                        hook.id, executable
                    ));
                }

                if let Some(cwd) = hook.cwd.as_ref() {
                    let cwd_path = Path::new(cwd);
                    let resolved = if cwd_path.is_absolute() {
                        cwd_path.to_path_buf()
                    } else {
                        project_root.join(cwd_path)
                    };
                    if !resolved.exists() || !resolved.is_dir() {
                        issues.push(format!(
                            "hooks.{phase_name}.{event_name}.{}: cwd '{}' does not exist",
                            hook.id,
                            resolved.display()
                        ));
                    }
                }
            }
        }
    }

    issues
}

pub fn run_lifecycle_hooks(
    root: &Path,
    phase: HookPhase,
    event: HookEvent,
    operation: Value,
    issues_for_policy: &[IssueData],
    options: HookExecutionOptions,
) -> Result<(), KanbusError> {
    if hooks_globally_disabled(options.no_hooks) {
        return Ok(());
    }

    let (hooks_config, project_root) = resolve_hook_configuration(root);
    if !hooks_config.enabled {
        return Ok(());
    }
    if options.beads_mode && !hooks_config.run_in_beads_mode {
        return Ok(());
    }

    let actor = get_current_user();
    let invocation = json!({
        "schema_version": HOOK_SCHEMA_VERSION,
        "phase": phase.as_str(),
        "event": event.as_str(),
        "timestamp": now_utc_iso(),
        "actor": actor,
        "mode": {
            "beads_mode": options.beads_mode,
            "project_root": project_root.display().to_string(),
            "working_directory": std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")).display().to_string(),
            "runtime": "rust",
        },
        "operation": operation,
    });

    let hooks = hooks_for_event(&hooks_config, phase, event);
    for hook in hooks {
        let timeout_ms = hook
            .timeout_ms
            .unwrap_or(hooks_config.default_timeout_ms)
            .max(1);
        let result = run_external_hook(&hook, &project_root, &invocation, timeout_ms);
        let blocking = effective_blocking(phase, Some(event), &hook);
        if result.succeeded {
            continue;
        }
        if phase == HookPhase::Before && blocking {
            return Err(KanbusError::IssueOperation(format!(
                "blocking hook '{}' failed for {}: {}",
                hook.id,
                event.as_str(),
                result.message
            )));
        }
        emit_stderr_line(&format!(
            "Hook warning ({}/{}/{}): {} (timeout={}, exit_code={:?}, duration_ms={})",
            event.as_str(),
            phase.as_str(),
            hook.id,
            result.message,
            result.timed_out,
            result.exit_code,
            result.duration_ms
        ));
    }

    if phase == HookPhase::After {
        run_policy_provider(
            &project_root,
            event,
            issues_for_policy,
            options.beads_mode,
            options.no_guidance,
        );
    }

    Ok(())
}

fn run_policy_provider(
    root: &Path,
    event: HookEvent,
    issues_for_policy: &[IssueData],
    beads_mode: bool,
    no_guidance: bool,
) {
    if beads_mode || issues_for_policy.is_empty() {
        return;
    }
    let policy_map = policy_event_map();
    let Some(operation) = policy_map.get(&event) else {
        return;
    };
    crate::policy_guidance::emit_guidance_for_issues(
        root,
        issues_for_policy,
        operation.clone(),
        no_guidance,
    );
}

fn policy_event_map() -> HashMap<HookEvent, crate::policy_context::PolicyOperation> {
    use crate::policy_context::PolicyOperation;
    HashMap::from([
        (HookEvent::IssueCreate, PolicyOperation::Create),
        (HookEvent::IssueUpdate, PolicyOperation::Update),
        (HookEvent::IssueClose, PolicyOperation::Close),
        (HookEvent::IssueDelete, PolicyOperation::Delete),
        (HookEvent::IssueShow, PolicyOperation::View),
        (HookEvent::IssueList, PolicyOperation::List),
        (HookEvent::IssueReady, PolicyOperation::Ready),
    ])
}

fn resolve_hook_configuration(root: &Path) -> (HooksConfiguration, PathBuf) {
    let config_path = match get_configuration_path(root) {
        Ok(path) => path,
        Err(_) => return (HooksConfiguration::default(), root.to_path_buf()),
    };
    let project_root = config_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| root.to_path_buf());

    match load_project_configuration(&config_path) {
        Ok(configuration) => (configuration.hooks, project_root),
        Err(_) => (HooksConfiguration::default(), project_root),
    }
}

fn hooks_for_event(
    hooks_config: &HooksConfiguration,
    phase: HookPhase,
    event: HookEvent,
) -> Vec<HookDefinition> {
    let map = if phase == HookPhase::Before {
        &hooks_config.before
    } else {
        &hooks_config.after
    };
    map.get(event.as_str()).cloned().unwrap_or_default()
}

fn effective_blocking(phase: HookPhase, event: Option<HookEvent>, hook: &HookDefinition) -> bool {
    if phase == HookPhase::After {
        return false;
    }
    if let Some(blocking) = hook.blocking {
        return blocking;
    }
    event.map(HookEvent::is_mutating).unwrap_or(false)
}

fn run_external_hook(
    hook: &HookDefinition,
    project_root: &Path,
    invocation: &Value,
    timeout_ms: u64,
) -> HookResult {
    if hook.command.is_empty() {
        return HookResult {
            succeeded: false,
            timed_out: false,
            exit_code: None,
            duration_ms: 0,
            message: "command is empty".to_string(),
        };
    }

    let mut command = Command::new(&hook.command[0]);
    if hook.command.len() > 1 {
        command.args(&hook.command[1..]);
    }

    let cwd = hook
        .cwd
        .as_ref()
        .map(PathBuf::from)
        .map(|cwd| {
            if cwd.is_absolute() {
                cwd
            } else {
                project_root.join(cwd)
            }
        })
        .unwrap_or_else(|| project_root.to_path_buf());

    command
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .current_dir(cwd)
        .envs(std::env::vars());

    for (key, value) in &hook.env {
        command.env(key, value);
    }

    let started = Instant::now();
    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            return HookResult {
                succeeded: false,
                timed_out: false,
                exit_code: None,
                duration_ms: started.elapsed().as_millis() as u64,
                message: error.to_string(),
            }
        }
    };

    if let Some(mut stdin) = child.stdin.take() {
        let payload = serde_json::to_string(invocation).unwrap_or_else(|_| "{}".to_string());
        if let Err(error) = stdin.write_all(payload.as_bytes()) {
            return HookResult {
                succeeded: false,
                timed_out: false,
                exit_code: None,
                duration_ms: started.elapsed().as_millis() as u64,
                message: error.to_string(),
            };
        }
    }

    let timeout = Duration::from_millis(timeout_ms.max(1));
    let mut timed_out = false;
    let exit_code: Option<i32>;

    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                exit_code = status.code();
                break;
            }
            Ok(None) => {
                if started.elapsed() >= timeout {
                    timed_out = true;
                    let _ = child.kill();
                    let _ = child.wait();
                    exit_code = None;
                    break;
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            Err(error) => {
                return HookResult {
                    succeeded: false,
                    timed_out: false,
                    exit_code: None,
                    duration_ms: started.elapsed().as_millis() as u64,
                    message: error.to_string(),
                }
            }
        }
    }

    let mut stderr = String::new();
    if let Some(mut stderr_pipe) = child.stderr.take() {
        let _ = stderr_pipe.read_to_string(&mut stderr);
    }

    let duration_ms = started.elapsed().as_millis() as u64;
    let succeeded = !timed_out && exit_code == Some(0);
    let message = if timed_out {
        format!("timed out after {timeout_ms}ms")
    } else if succeeded {
        "ok".to_string()
    } else if !stderr.trim().is_empty() {
        stderr.trim().to_string()
    } else {
        format!("exit code {:?}", exit_code)
    };

    HookResult {
        succeeded,
        timed_out,
        exit_code,
        duration_ms,
        message,
    }
}

fn looks_like_path(command: &str) -> bool {
    command.starts_with('.') || command.contains('/') || command.contains('\\')
}

fn command_on_path(command: &str) -> bool {
    let Some(path) = std::env::var_os("PATH") else {
        return false;
    };
    for entry in std::env::split_paths(&path) {
        let candidate = entry.join(command);
        if candidate.exists() {
            return true;
        }
    }
    false
}

fn now_utc_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}
