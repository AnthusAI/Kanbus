//! Agent assignment resolution for console snapshots.

use serde_json::{json, Value};

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{
        IssueRouterClassConfiguration, IssueRouterLimitsConfiguration,
        IssueRouterWorkflowConfiguration,
    };
    use std::collections::BTreeMap;

    fn profile(
        model: Option<&str>,
        service_tier: Option<&str>,
    ) -> IssueRouterProviderConfiguration {
        IssueRouterProviderConfiguration {
            adapter: "codex".to_string(),
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
                    profile(Some("gpt-5.6-luna"), Some("flex")),
                ),
                ("plain".to_string(), profile(None, None)),
                ("a-profile".to_string(), profile(None, None)),
                ("b-profile".to_string(), profile(Some("m"), None)),
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
                "effective": {"platform": "codex", "model": "gpt-5.6-luna", "settings": {"service_tier": "flex"}},
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
}
