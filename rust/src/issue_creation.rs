//! Issue creation workflow.

use chrono::Utc;
use std::path::{Path, PathBuf};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::event_history::{
    events_dir_for_local, events_dir_for_project, issue_created_payload, now_timestamp,
    write_events_batch, EventRecord, EventType,
};
use crate::hierarchy::validate_parent_child_relationship;
use crate::ids::{generate_issue_identifier, issue_identifier_matches, IssueIdentifierRequest};
use crate::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use crate::models::{IssueData, ProjectConfiguration};
use crate::users::get_current_user;
use crate::workflows::validate_status_value;
use crate::{
    file_io::{
        ensure_project_local_directory, find_project_local_directory, get_configuration_path,
        load_project_directory,
    },
    models::DependencyLink,
};

/// Request payload for issue creation.
#[derive(Debug, Clone)]
pub struct IssueCreationRequest {
    pub root: PathBuf,
    pub title: String,
    pub issue_type: Option<String>,
    pub priority: Option<u8>,
    pub assignee: Option<String>,
    pub parent: Option<String>,
    pub labels: Vec<String>,
    pub description: Option<String>,
    pub local: bool,
    pub validate: bool,
}

/// Result payload for issue creation.
#[derive(Debug, Clone)]
pub struct IssueCreationResult {
    pub issue: IssueData,
    pub configuration: ProjectConfiguration,
}

/// Create a new issue and write it to disk.
///
/// # Arguments
/// * `request` - Issue creation request payload.
///
/// # Errors
/// Returns `KanbusError` if validation or file operations fail.
pub fn create_issue(request: &IssueCreationRequest) -> Result<IssueCreationResult, KanbusError> {
    let project_dir = load_project_directory(request.root.as_path())?;
    let mut issues_dir = project_dir.join("issues");
    let mut local_dir = find_project_local_directory(&project_dir);
    if request.local {
        local_dir = Some(ensure_project_local_directory(&project_dir)?);
        issues_dir = local_dir.as_ref().expect("local dir").join("issues");
    }
    let config_path = get_configuration_path(request.root.as_path())?;
    let configuration = load_project_configuration(&config_path)?;

    let resolved_type = request.issue_type.as_deref().unwrap_or("task");
    let resolved_priority = request.priority.unwrap_or(configuration.default_priority);
    // Resolve parent: accept full id or unique short id (projectkey-<prefix>).
    let mut resolved_parent = request.parent.clone();
    if let Some(parent_identifier) = resolved_parent.clone() {
        let full_id =
            resolve_issue_identifier(&issues_dir, &configuration.project_key, &parent_identifier)?;
        resolved_parent = Some(full_id);
    }
    if request.validate {
        validate_issue_type(&configuration, resolved_type)?;
        if !configuration.priorities.contains_key(&resolved_priority) {
            return Err(KanbusError::IssueOperation("invalid priority".to_string()));
        }

        if let Some(parent_identifier) = resolved_parent.as_deref() {
            let parent_path = issue_path_for_identifier(&issues_dir, parent_identifier);
            if !parent_path.exists() {
                return Err(KanbusError::IssueOperation("not found".to_string()));
            }
            let parent_issue = read_issue_from_file(&parent_path)?;
            validate_parent_child_relationship(
                &configuration,
                &parent_issue.issue_type,
                resolved_type,
            )?;
        }

        if let Some(duplicate_identifier) = find_duplicate_title(&issues_dir, &request.title)? {
            return Err(KanbusError::IssueOperation(format!(
                "duplicate title: \"{}\" already exists as {}",
                request.title, duplicate_identifier
            )));
        }

        validate_status_value(&configuration, resolved_type, &configuration.initial_status)?;
    }

    let mut existing_ids = list_issue_identifiers(&project_dir.join("issues"))?;
    if let Some(local_dir) = local_dir {
        let local_issues = local_dir.join("issues");
        if local_issues.exists() {
            existing_ids.extend(list_issue_identifiers(&local_issues)?);
        }
    }
    let created_at = Utc::now();
    let identifier_request = IssueIdentifierRequest {
        title: request.title.clone(),
        existing_ids,
        prefix: configuration.project_key.clone(),
    };
    let identifier = generate_issue_identifier(&identifier_request)?.identifier;
    let updated_at = created_at;

    let resolved_assignee = request
        .assignee
        .clone()
        .or_else(|| configuration.assignee.clone());

    let issue = IssueData {
        identifier,
        title: request.title.clone(),
        description: request.description.clone().unwrap_or_default(),
        issue_type: resolved_type.to_string(),
        status: configuration.initial_status.clone(),
        priority: resolved_priority as i32,
        assignee: resolved_assignee,
        creator: None,
        parent: resolved_parent.clone(),
        labels: request.labels.clone(),
        dependencies: Vec::<DependencyLink>::new(),
        comments: Vec::new(),
        created_at,
        updated_at,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };

    let policies_dir = project_dir.join("policies");
    if policies_dir.is_dir() {
        let policy_documents = crate::policy_loader::load_policies(&policies_dir)?;
        if !policy_documents.is_empty() {
            let all_issues = crate::issue_listing::load_issues_from_directory(&issues_dir)?;
            let context = crate::policy_context::PolicyContext {
                current_issue: None,
                proposed_issue: issue.clone(),
                transition: None,
                operation: crate::policy_context::PolicyOperation::Create,
                project_configuration: configuration.clone(),
                all_issues,
            };
            crate::policy_evaluator::evaluate_policies(&context, &policy_documents)?;
        }
    }

    let issue_path = issue_path_for_identifier(&issues_dir, &issue.identifier);
    write_issue_to_file(&issue, &issue_path)?;

    let occurred_at = now_timestamp();
    let actor_id = get_current_user();
    let event = EventRecord::new(
        issue.identifier.clone(),
        EventType::IssueCreated,
        actor_id,
        issue_created_payload(&issue),
        occurred_at,
    );
    let event_id = event.event_id.clone();
    let events_dir = if request.local {
        match events_dir_for_local(&project_dir) {
            Ok(path) => path,
            Err(error) => {
                std::fs::remove_file(&issue_path)
                    .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
                return Err(error);
            }
        }
    } else {
        events_dir_for_project(&project_dir)
    };
    match write_events_batch(&events_dir, &[event]) {
        Ok(_paths) => {}
        Err(error) => {
            std::fs::remove_file(&issue_path)
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Err(error);
        }
    }

    if !request.local {
        crate::gossip::publish_issue_mutation(
            request.root.as_path(),
            &project_dir,
            &issue,
            Some(event_id),
            "issue.mutated",
        );
    }

    Ok(IssueCreationResult {
        issue,
        configuration,
    })
}

fn validate_issue_type(
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(), KanbusError> {
    let is_known = configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
        .any(|entry| entry == issue_type);
    if !is_known {
        return Err(KanbusError::IssueOperation(
            "unknown issue type".to_string(),
        ));
    }
    Ok(())
}

fn find_duplicate_title(issues_dir: &Path, title: &str) -> Result<Option<String>, KanbusError> {
    let normalized_title = title.trim().to_lowercase();
    for entry in
        std::fs::read_dir(issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let issue = read_issue_from_file(&path)?;
        if issue.title.trim().to_lowercase() == normalized_title {
            return Ok(Some(issue.identifier));
        }
    }
    Ok(None)
}

/// Resolve an issue identifier from a user-provided value.
///
/// Accepts a full id, a unique short id (`{project_key}-{prefix}` up to 6 chars),
/// or a project-context short id (no project key).
pub fn resolve_issue_identifier(
    issues_dir: &Path,
    _project_key: &str,
    candidate: &str,
) -> Result<String, KanbusError> {
    // First, try exact match on filename.
    let exact_path = issue_path_for_identifier(issues_dir, candidate);
    if exact_path.exists() {
        return Ok(candidate.to_string());
    }

    // Otherwise, attempt a unique short-id match.
    let identifiers = list_issue_identifiers(issues_dir)?;
    let mut matches: Vec<String> = identifiers
        .into_iter()
        .filter(|full_id| issue_identifier_matches(candidate, full_id))
        .collect();

    match matches.len() {
        1 => Ok(matches.pop().expect("single match")),
        0 => Err(KanbusError::IssueOperation("not found".to_string())),
        _ => Err(KanbusError::IssueOperation(
            "ambiguous short id".to_string(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use crate::file_io::initialize_project;
    use chrono::Utc;
    use std::collections::BTreeMap;
    use std::path::Path;

    fn make_issue(id: &str, title: &str) -> IssueData {
        IssueData {
            identifier: id.to_string(),
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
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    fn minimal_config() -> ProjectConfiguration {
        default_project_configuration()
    }

    fn initialize_test_project(root: &Path) {
        initialize_project(root, true).expect("initialize project");
    }

    fn request(root: &Path, title: &str) -> IssueCreationRequest {
        IssueCreationRequest {
            root: root.to_path_buf(),
            title: title.to_string(),
            issue_type: None,
            priority: None,
            assignee: None,
            parent: None,
            labels: Vec::new(),
            description: None,
            local: false,
            validate: true,
        }
    }

    #[test]
    fn validate_issue_type_accepts_known_and_rejects_unknown() {
        let config = minimal_config();
        assert!(validate_issue_type(&config, "task").is_ok());
        assert!(validate_issue_type(&config, "bug").is_ok());
        let error = validate_issue_type(&config, "unknown-type").expect_err("should fail");
        match error {
            KanbusError::IssueOperation(message) => assert_eq!(message, "unknown issue type"),
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn find_duplicate_title_is_case_insensitive_and_skips_non_json() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("mkdir");
        write_issue_to_file(
            &make_issue("kanbus-abc12345", "Fix Login"),
            &issues_dir.join("kanbus-abc12345.json"),
        )
        .expect("write issue");
        std::fs::write(issues_dir.join("README.md"), "ignore").expect("write readme");

        let duplicate = find_duplicate_title(&issues_dir, "  fix login  ").expect("duplicate");
        assert_eq!(duplicate.as_deref(), Some("kanbus-abc12345"));
        let none = find_duplicate_title(&issues_dir, "different").expect("no duplicate");
        assert!(none.is_none());
    }

    #[test]
    fn find_duplicate_title_returns_error_for_invalid_json() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("mkdir");
        std::fs::write(issues_dir.join("broken.json"), "{not-json").expect("write broken");
        let error = find_duplicate_title(&issues_dir, "anything").expect_err("should fail");
        assert!(matches!(error, KanbusError::Io(_)));
    }

    #[test]
    fn resolve_issue_identifier_handles_exact_unique_ambiguous_and_missing() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("mkdir");
        write_issue_to_file(
            &make_issue("kanbus-abc12345", "A"),
            &issues_dir.join("kanbus-abc12345.json"),
        )
        .expect("write issue a");
        write_issue_to_file(
            &make_issue("kanbus-abc67890", "B"),
            &issues_dir.join("kanbus-abc67890.json"),
        )
        .expect("write issue b");

        let exact =
            resolve_issue_identifier(&issues_dir, "kanbus", "kanbus-abc12345").expect("exact");
        assert_eq!(exact, "kanbus-abc12345");

        let unique_short =
            resolve_issue_identifier(&issues_dir, "kanbus", "abc678").expect("short");
        assert_eq!(unique_short, "kanbus-abc67890");

        let ambiguous =
            resolve_issue_identifier(&issues_dir, "kanbus", "kanbus-abc").expect_err("ambiguous");
        match ambiguous {
            KanbusError::IssueOperation(message) => assert_eq!(message, "ambiguous short id"),
            other => panic!("unexpected error: {other:?}"),
        }

        let missing =
            resolve_issue_identifier(&issues_dir, "kanbus", "zzz999").expect_err("missing");
        match missing {
            KanbusError::IssueOperation(message) => assert_eq!(message, "not found"),
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn create_issue_rejects_unknown_type_when_validate_enabled() {
        let temp = tempfile::tempdir().expect("tempdir");
        initialize_test_project(temp.path());
        let mut req = request(temp.path(), "Unknown type");
        req.issue_type = Some("not-a-real-type".to_string());
        let error = create_issue(&req).expect_err("should fail");
        match error {
            KanbusError::IssueOperation(message) => assert_eq!(message, "unknown issue type"),
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn create_issue_rejects_invalid_priority_when_validate_enabled() {
        let temp = tempfile::tempdir().expect("tempdir");
        initialize_test_project(temp.path());
        let mut req = request(temp.path(), "Bad priority");
        req.priority = Some(250);
        let error = create_issue(&req).expect_err("should fail");
        match error {
            KanbusError::IssueOperation(message) => assert_eq!(message, "invalid priority"),
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn create_issue_rejects_missing_parent_when_validate_enabled() {
        let temp = tempfile::tempdir().expect("tempdir");
        initialize_test_project(temp.path());
        let mut req = request(temp.path(), "Missing parent");
        req.parent = Some("kanbus-unknown123".to_string());
        let error = create_issue(&req).expect_err("should fail");
        match error {
            KanbusError::IssueOperation(message) => assert_eq!(message, "not found"),
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn create_issue_rejects_duplicate_title_case_insensitively() {
        let temp = tempfile::tempdir().expect("tempdir");
        initialize_test_project(temp.path());
        let first = request(temp.path(), "Fix Login");
        create_issue(&first).expect("create first");

        let second = request(temp.path(), "  fix login  ");
        let error = create_issue(&second).expect_err("duplicate should fail");
        match error {
            KanbusError::IssueOperation(message) => {
                assert!(message.contains("duplicate title"));
                assert!(message.contains("kanbus-"));
            }
            other => panic!("unexpected error: {other:?}"),
        }
    }

    #[test]
    fn create_issue_validate_false_allows_unknown_type_and_priority() {
        let temp = tempfile::tempdir().expect("tempdir");
        initialize_test_project(temp.path());
        let mut req = request(temp.path(), "No validate");
        req.issue_type = Some("not-a-real-type".to_string());
        req.priority = Some(250);
        req.validate = false;
        let result = create_issue(&req).expect("creation should bypass validation");
        assert_eq!(result.issue.issue_type, "not-a-real-type");
        assert_eq!(result.issue.priority, 250);
    }
}
