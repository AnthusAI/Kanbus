//! Agent assignment resolution for console snapshots.

use std::path::Path;

use serde_json::{json, Value};

use crate::error::KanbusError;
use crate::file_io::get_configuration_path;

use crate::models::{IssueRouterConfiguration, IssueRouterProviderConfiguration};

/// Resolve agent assignment from issue labels and router configuration.
///
/// For an issue with exactly ONE label matching `agent-class:` or `agent-provider:`,
/// and a valid router configuration present, returns the assignment with safe
/// effective settings. Returns `None` if label is missing, invalid, ambiguous, or
/// if no router is configured.
///
/// # Arguments
/// * `issue_labels` - List of issue labels.
/// * `router` - Router configuration, when the project has one.
///
/// # Returns
/// Agent assignment JSON object or `None`.
pub fn resolve_agent_assignment(
    issue_labels: &[String],
    router: Option<&IssueRouterConfiguration>,
) -> Option<Value> {
    let router = router?;

    let routing_labels: Vec<&String> = issue_labels
        .iter()
        .filter(|label| label.starts_with("agent-class:") || label.starts_with("agent-provider:"))
        .collect();

    if routing_labels.len() != 1 {
        return None;
    }

    let routing_label = routing_labels[0];

    if let Some(class_name) = routing_label.strip_prefix("agent-class:") {
        if class_name.is_empty() {
            return None;
        }

        let agent_class = router.classes.get(class_name)?;
        if agent_class.providers.is_empty() {
            return None;
        }

        let provider_key = &agent_class.providers[0];
        let profile = router.providers.get(provider_key)?;

        return Some(json!({
            "kind": "class",
            "name": class_name,
            "provider_profile": provider_key,
            "effective": build_effective_settings(profile),
        }));
    }

    if let Some(provider_name) = routing_label.strip_prefix("agent-provider:") {
        if provider_name.is_empty() {
            return None;
        }

        let profile = router.providers.get(provider_name)?;

        return Some(json!({
            "kind": "provider",
            "name": provider_name,
            "provider_profile": provider_name,
            "effective": build_effective_settings(profile),
        }));
    }

    None
}

/// Build safe effective settings from a router profile.
///
/// Includes only platform, model (if set), and settings.service_tier (if set).
/// Excludes command, args, and env (secrets).
///
/// # Arguments
/// * `profile` - Router agent profile.
///
/// # Returns
/// Safe effective settings JSON object.
fn build_effective_settings(profile: &IssueRouterProviderConfiguration) -> Value {
    let mut effective = json!({"platform": profile.adapter});

    if let Some(model) = &profile.model {
        effective["model"] = Value::String(model.clone());
    }

    if let Some(service_tier) = &profile.service_tier {
        effective["settings"] = json!({"service_tier": service_tier});
    }

    effective
}

/// Redact router configuration secrets from a configuration struct.
///
/// Sets provider args to empty vec and replaces all env values with "[redacted]".
/// Modifies the struct in place.
///
/// # Arguments
/// * `config` - Mutable router configuration.
pub fn redact_router_config(config: &mut IssueRouterConfiguration) {
    for profile in config.providers.values_mut() {
        profile.args.clear();
        for value in profile.env.values_mut() {
            *value = "[redacted]".to_string();
        }
    }
}

const ROUTE_LABEL_PREFIXES: [&str; 2] = ["agent-class:", "agent-provider:"];

/// A routing assignment chosen by a person.
#[derive(Debug, Clone, Copy)]
pub struct AssignmentChoice<'a> {
    /// Either `class` or `provider`.
    pub kind: &'a str,
    /// Name of a configured router class or provider profile.
    pub name: &'a str,
}

fn assignment_label(
    router: &IssueRouterConfiguration,
    choice: &AssignmentChoice<'_>,
) -> Result<String, KanbusError> {
    match choice.kind {
        "class" if router.classes.contains_key(choice.name) => {
            Ok(format!("agent-class:{}", choice.name))
        }
        "class" => Err(KanbusError::IssueOperation(format!(
            "unknown agent class \"{}\"",
            choice.name
        ))),
        "provider" if router.providers.contains_key(choice.name) => {
            Ok(format!("agent-provider:{}", choice.name))
        }
        "provider" => Err(KanbusError::IssueOperation(format!(
            "unknown provider profile \"{}\"",
            choice.name
        ))),
        other => Err(KanbusError::IssueOperation(format!(
            "assignment kind must be class or provider, got \"{other}\""
        ))),
    }
}

/// Set, replace or clear an issue's routing assignment.
///
/// Exactly one `agent-class:` or `agent-provider:` label is kept, and every
/// other label is preserved. The issue's agent provenance is not touched. The
/// change is refused while the router is running the issue.
///
/// # Arguments
/// * `root` - Repository root.
/// * `identifier` - Full issue identifier.
/// * `choice` - The assignment to apply, or `None` to clear it.
///
/// # Errors
/// Returns an error when no router is configured, the class or provider is
/// not configured, the router is running the issue, or the write fails.
pub fn change_issue_assignment(
    root: &Path,
    identifier: &str,
    choice: Option<AssignmentChoice<'_>>,
) -> Result<(), KanbusError> {
    let configuration =
        crate::config_loader::load_project_configuration(&get_configuration_path(root)?)?;
    let router = configuration
        .router
        .as_ref()
        .ok_or_else(|| KanbusError::IssueOperation("router is not configured".to_string()))?;
    let desired = choice
        .map(|choice| assignment_label(router, &choice))
        .transpose()?;
    let issue = crate::issue_lookup::load_issue_from_project(root, identifier)?.issue;
    if crate::router::issue_is_running_in_router(root, &issue.identifier)? {
        return Err(KanbusError::IssueOperation(
            "the router is running this issue; change its assignment after the run ends"
                .to_string(),
        ));
    }
    let current: Vec<String> = issue
        .labels
        .iter()
        .filter(|label| {
            ROUTE_LABEL_PREFIXES
                .iter()
                .any(|prefix| label.starts_with(prefix))
        })
        .cloned()
        .collect();
    let remove: Vec<String> = current
        .iter()
        .filter(|label| Some(*label) != desired.as_ref())
        .cloned()
        .collect();
    let add: Vec<String> = desired
        .filter(|label| !current.contains(label))
        .into_iter()
        .collect();
    if add.is_empty() && remove.is_empty() {
        return Ok(());
    }
    crate::issue_update::update_issue(
        root,
        &issue.identifier,
        None,
        None,
        None,
        None,
        None,
        false,
        true,
        &add,
        &remove,
        None,
        None,
        None,
        None,
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{
        IssueRouterClassConfiguration, IssueRouterLimitsConfiguration,
        IssueRouterWorkflowConfiguration,
    };
    use std::collections::BTreeMap;

    fn profile(
        adapter: &str,
        model: Option<&str>,
        service_tier: Option<&str>,
    ) -> IssueRouterProviderConfiguration {
        IssueRouterProviderConfiguration {
            adapter: adapter.to_string(),
            command: None,
            args: vec!["--api-key".to_string(), "sk-secret".to_string()],
            model: model.map(str::to_string),
            env: BTreeMap::from([("OPENAI_API_KEY".to_string(), "sk-live-secret".to_string())]),
            service_tier: service_tier.map(str::to_string),
        }
    }

    fn router() -> IssueRouterConfiguration {
        IssueRouterConfiguration {
            enabled: true,
            workflow: IssueRouterWorkflowConfiguration {
                pending: "open".to_string(),
                active: "in_progress".to_string(),
                review: "review".to_string(),
                blocked: "blocked".to_string(),
                terminal: vec!["closed".to_string()],
            },
            limits: IssueRouterLimitsConfiguration {
                project_wip: 2,
                review_wip: 1,
                class_wip: BTreeMap::new(),
                provider_wip: BTreeMap::new(),
            },
            providers: BTreeMap::from([
                (
                    "codex-default".to_string(),
                    profile("codex", Some("gpt-5.6-luna"), None),
                ),
                (
                    "bedrock".to_string(),
                    profile(
                        "opencode",
                        Some("amazon-bedrock/openai.gpt-oss-20b-1:0"),
                        Some("flex"),
                    ),
                ),
                ("plain".to_string(), profile("codex", None, None)),
                ("a-profile".to_string(), profile("codex", None, None)),
                ("b-profile".to_string(), profile("codex", Some("m"), None)),
            ]),
            classes: BTreeMap::from([
                (
                    "implementation".to_string(),
                    IssueRouterClassConfiguration {
                        providers: vec!["codex-default".to_string()],
                    },
                ),
                (
                    "ordered".to_string(),
                    IssueRouterClassConfiguration {
                        providers: vec!["b-profile".to_string(), "a-profile".to_string()],
                    },
                ),
            ]),
            retries: Default::default(),
            watch_interval: "30s".to_string(),
            forge: None,
        }
    }

    fn labels(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    #[test]
    fn class_label_resolves_to_the_first_provider_with_safe_settings() {
        let router = router();
        let assignment =
            resolve_agent_assignment(&labels(&["agent-class:implementation"]), Some(&router))
                .expect("assignment");
        assert_eq!(
            assignment,
            json!({
                "kind": "class",
                "name": "implementation",
                "provider_profile": "codex-default",
                "effective": {"platform": "codex", "model": "gpt-5.6-luna"},
            })
        );
        let text = assignment.to_string();
        assert!(!text.contains("sk-secret") && !text.contains("sk-live-secret"));
    }

    #[test]
    fn provider_label_omits_absent_model_and_settings() {
        let router = router();
        let assignment =
            resolve_agent_assignment(&labels(&["agent-provider:plain"]), Some(&router))
                .expect("assignment");
        assert_eq!(assignment["effective"], json!({"platform": "codex"}));
        assert_eq!(assignment["kind"], "provider");
    }

    #[test]
    fn a_provider_with_a_service_tier_shows_it_under_settings() {
        let router = router();
        let assignment =
            resolve_agent_assignment(&labels(&["agent-provider:bedrock"]), Some(&router))
                .expect("assignment");
        assert_eq!(
            assignment["effective"]["settings"],
            json!({"service_tier": "flex"})
        );
    }

    #[test]
    fn class_resolution_uses_the_first_listed_provider() {
        let router = router();
        let assignment = resolve_agent_assignment(&labels(&["agent-class:ordered"]), Some(&router))
            .expect("assignment");
        assert_eq!(assignment["provider_profile"], "b-profile");
    }

    #[test]
    fn unresolvable_labels_yield_no_assignment() {
        let router = router();
        for case in [
            labels(&["agent-class:unknown"]),
            labels(&["agent-provider:unknown"]),
            labels(&["agent-class:"]),
            labels(&["agent-class:implementation", "agent-provider:plain"]),
            labels(&["bug"]),
            labels(&[]),
        ] {
            assert!(
                resolve_agent_assignment(&case, Some(&router)).is_none(),
                "{case:?}"
            );
        }
        assert!(resolve_agent_assignment(&labels(&["agent-class:implementation"]), None).is_none());
    }

    #[test]
    fn redaction_clears_args_and_masks_env_values_but_keeps_keys() {
        let mut router = router();
        redact_router_config(&mut router);
        for profile in router.providers.values() {
            assert!(profile.args.is_empty());
            assert_eq!(
                profile.env,
                BTreeMap::from([("OPENAI_API_KEY".to_string(), "[redacted]".to_string())])
            );
        }
    }

    fn project_with_router(
        labels: &[&str],
        status: &str,
        with_router: bool,
    ) -> (tempfile::TempDir, std::path::PathBuf) {
        let temp = tempfile::tempdir().expect("tempdir");
        let root = temp.path().canonicalize().expect("canonical root");
        std::fs::create_dir_all(root.join("project").join("issues")).expect("issues dir");
        std::fs::create_dir_all(root.join("project").join("events")).expect("events dir");
        let git_init = std::process::Command::new("git")
            .args(["init", "-q"])
            .current_dir(&root)
            .status()
            .expect("git init");
        assert!(git_init.success());
        let mut configuration = crate::config::default_project_configuration();
        if with_router {
            configuration
                .statuses
                .push(crate::models::StatusDefinition {
                    key: "review".to_string(),
                    name: "Review".to_string(),
                    category: "In progress".to_string(),
                    semantic_category: "in_progress".to_string(),
                    color: None,
                    collapsed: false,
                });
            let workflow = configuration
                .workflows
                .get_mut("default")
                .expect("workflow");
            workflow
                .get_mut("in_progress")
                .expect("in_progress")
                .push("review".to_string());
            workflow.insert(
                "review".to_string(),
                vec![
                    "in_progress".to_string(),
                    "blocked".to_string(),
                    "closed".to_string(),
                ],
            );
            let labels_by_status = configuration
                .transition_labels
                .get_mut("default")
                .expect("labels");
            labels_by_status
                .get_mut("in_progress")
                .expect("in_progress labels")
                .insert("review".to_string(), "Review".to_string());
            labels_by_status.insert(
                "review".to_string(),
                BTreeMap::from([
                    ("in_progress".to_string(), "Resume".to_string()),
                    ("blocked".to_string(), "Block".to_string()),
                    ("closed".to_string(), "Complete".to_string()),
                ]),
            );
            configuration.router = Some(router());
        }
        std::fs::write(
            root.join(".kanbus.yml"),
            serde_yaml::to_string(&configuration).expect("serialize configuration"),
        )
        .expect("write configuration");
        let now = chrono::Utc::now();
        let issue = crate::models::IssueData {
            identifier: "kbs-edit".to_string(),
            title: "Editable".to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: status.to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: labels.iter().map(|label| label.to_string()).collect(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now,
            updated_at: now,
            closed_at: None,
            agent: Some(crate::models::AgentMetadata {
                platform: "codex".to_string(),
                model: "gpt-5".to_string(),
                name: None,
                settings: BTreeMap::new(),
            }),
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        };
        crate::issue_files::write_issue_to_file(
            &issue,
            &root.join("project").join("issues").join("kbs-edit.json"),
        )
        .expect("write issue");
        (temp, root)
    }

    fn stored_issue(root: &std::path::Path) -> crate::models::IssueData {
        crate::issue_files::read_issue_from_file(
            &root.join("project").join("issues").join("kbs-edit.json"),
        )
        .expect("read issue")
    }

    fn choice<'a>(kind: &'a str, name: &'a str) -> Option<AssignmentChoice<'a>> {
        Some(AssignmentChoice { kind, name })
    }

    #[test]
    fn choosing_a_class_keeps_the_other_labels() {
        let (_temp, root) = project_with_router(&["bug", "ui"], "open", true);
        change_issue_assignment(&root, "kbs-edit", choice("class", "implementation"))
            .expect("assign");
        let mut labels = stored_issue(&root).labels;
        labels.sort();
        assert_eq!(labels, ["agent-class:implementation", "bug", "ui"]);
    }

    #[test]
    fn choosing_replaces_any_existing_route_and_never_leaves_two() {
        let (_temp, root) = project_with_router(
            &["bug", "agent-provider:plain", "agent-class:implementation"],
            "open",
            true,
        );
        change_issue_assignment(&root, "kbs-edit", choice("provider", "codex-default"))
            .expect("assign");
        let mut labels = stored_issue(&root).labels;
        labels.sort();
        assert_eq!(labels, ["agent-provider:codex-default", "bug"]);
    }

    #[test]
    fn clearing_removes_only_the_route_labels() {
        let (_temp, root) =
            project_with_router(&["bug", "agent-class:implementation"], "open", true);
        change_issue_assignment(&root, "kbs-edit", None).expect("clear");
        assert_eq!(stored_issue(&root).labels, ["bug"]);
    }

    #[test]
    fn choosing_the_current_assignment_changes_nothing() {
        let (_temp, root) = project_with_router(&["agent-class:implementation"], "open", true);
        let before = stored_issue(&root).updated_at;
        change_issue_assignment(&root, "kbs-edit", choice("class", "implementation"))
            .expect("assign");
        assert_eq!(stored_issue(&root).updated_at, before);
    }

    #[test]
    fn the_agent_provenance_is_never_modified() {
        let (_temp, root) = project_with_router(&[], "open", true);
        let before = stored_issue(&root).agent;
        change_issue_assignment(&root, "kbs-edit", choice("class", "implementation"))
            .expect("assign");
        assert_eq!(stored_issue(&root).agent, before);
    }

    #[test]
    fn unknown_names_and_kinds_are_rejected_without_writing() {
        let (_temp, root) = project_with_router(&["bug"], "open", true);
        for (kind, name, expected) in [
            ("class", "missing", "unknown agent class"),
            ("provider", "missing", "unknown provider profile"),
            ("team", "implementation", "must be class or provider"),
        ] {
            let error = change_issue_assignment(&root, "kbs-edit", choice(kind, name))
                .expect_err("rejected")
                .to_string();
            assert!(error.contains(expected), "{error}");
        }
        assert_eq!(stored_issue(&root).labels, ["bug"]);
    }

    #[test]
    fn a_project_without_a_router_cannot_be_assigned() {
        let (_temp, root) = project_with_router(&[], "open", false);
        let error = change_issue_assignment(&root, "kbs-edit", choice("class", "implementation"))
            .expect_err("rejected")
            .to_string();
        assert!(error.contains("router is not configured"), "{error}");
    }

    #[test]
    fn an_issue_the_router_is_running_cannot_be_reassigned() {
        let (_temp, root) =
            project_with_router(&["agent-class:implementation"], "in_progress", true);
        let error = change_issue_assignment(&root, "kbs-edit", choice("provider", "plain"))
            .expect_err("rejected")
            .to_string();
        assert!(error.contains("router is running this issue"), "{error}");
        assert_eq!(stored_issue(&root).labels, ["agent-class:implementation"]);
    }
}
