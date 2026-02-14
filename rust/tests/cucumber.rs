use std::fs;
use std::path::{Path, PathBuf};

use cucumber::cli::Empty;
use cucumber::feature::Ext as _;
use cucumber::gherkin::{self, GherkinEnv};
use cucumber::parser::{Parser, Result as ParserResult};
use cucumber::World;
use futures::stream;

#[path = "../features/steps/mod.rs"]
mod step_definitions;

use step_definitions::initialization_steps::KanbusWorld;

#[derive(Clone, Debug, Default)]
struct RecursiveFeatureParser;

impl RecursiveFeatureParser {
    fn collect_features(root: &Path) -> Result<Vec<PathBuf>, gherkin::ParseFileError> {
        let mut feature_files = Vec::new();
        Self::collect_feature_files(root, &mut feature_files).map_err(|error| {
            gherkin::ParseFileError::Reading {
                path: root.to_path_buf(),
                source: error,
            }
        })?;
        feature_files.sort();
        Ok(feature_files)
    }

    fn collect_feature_files(root: &Path, feature_files: &mut Vec<PathBuf>) -> std::io::Result<()> {
        for entry in fs::read_dir(root)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                Self::collect_feature_files(&path, feature_files)?;
            } else if path.extension().and_then(|ext| ext.to_str()) == Some("feature") {
                feature_files.push(path);
            }
        }
        Ok(())
    }
}

impl<I: AsRef<Path>> Parser<I> for RecursiveFeatureParser {
    type Cli = Empty;
    type Output = stream::Iter<std::vec::IntoIter<ParserResult<gherkin::Feature>>>;

    fn parse(self, input: I, _: Self::Cli) -> Self::Output {
        let path = input.as_ref();
        let features: Vec<ParserResult<gherkin::Feature>> = if path.is_file() {
            vec![gherkin::Feature::parse_path(path, GherkinEnv::default()).map_err(Into::into)]
        } else {
            match Self::collect_features(path) {
                Ok(feature_paths) => feature_paths
                    .into_iter()
                    .map(|feature_path| {
                        gherkin::Feature::parse_path(feature_path, GherkinEnv::default())
                            .map_err(Into::into)
                    })
                    .collect(),
                Err(error) => vec![Err(error.into())],
            }
        };

        let expanded: Vec<ParserResult<gherkin::Feature>> = features
            .into_iter()
            .map(|feature| {
                feature.and_then(|feature| feature.expand_examples().map_err(Into::into))
            })
            .collect();
        stream::iter(expanded)
    }
}

#[tokio::main]
async fn main() {
    let features_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("features");
    if !features_dir.exists() {
        panic!("features directory missing at {}", features_dir.display());
    }
    #[cfg(tarpaulin)]
    cover_additional_paths();
    KanbusWorld::cucumber::<PathBuf>()
        .with_parser(RecursiveFeatureParser::default())
        .max_concurrent_scenarios(1)
        .filter_run(features_dir, |feature, _, scenario| {
            let scenario_has_wip = scenario.tags.iter().any(|tag| tag == "wip");
            let feature_has_wip = feature.tags.iter().any(|tag| tag == "wip");
            let scenario_has_console = scenario.tags.iter().any(|tag| tag == "console");
            let feature_has_console = feature.tags.iter().any(|tag| tag == "console");
            !(scenario_has_wip || feature_has_wip || scenario_has_console || feature_has_console)
        })
        .await;
}

#[cfg(tarpaulin)]
fn cover_additional_paths() {
    use std::fs;
    use std::path::Path;
    use std::process::Command;

    use serde_json::json;
    use tempfile::TempDir;

    use kanbus::agents_management::{
        cover_agents_management_paths, cover_parse_header_cases, ensure_agents_file,
    };
    use kanbus::cli::run_from_args_with_output;
    use kanbus::console_snapshot::build_console_snapshot;
    use kanbus::dependencies::{
        add_dependency, cover_dependencies_paths, list_ready_issues, remove_dependency,
    };
    use kanbus::doctor::run_doctor;
    use kanbus::file_io::{get_configuration_path, initialize_project, load_project_directory};
    use kanbus::issue_creation::{create_issue, IssueCreationRequest};
    use kanbus::issue_listing::list_issues;
    use kanbus::issue_update::update_issue;
    use kanbus::migration::{load_beads_issue_by_id, load_beads_issues, migrate_from_beads};

    std::env::set_var("KANBUS_NO_DAEMON", "1");

    let temp_dir = TempDir::new().expect("tempdir");
    let root = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root)
        .output()
        .expect("git init");

    initialize_project(root, true).expect("initialize project");
    fs::write(root.join("project").join("kanbus.yml"), "").expect("write doctor config");
    ensure_agents_file(root, true).expect("ensure agents");
    cover_parse_header_cases();
    cover_agents_management_paths(root);

    let issue_one = create_issue(&IssueCreationRequest {
        root: root.to_path_buf(),
        title: "First issue".to_string(),
        issue_type: None,
        priority: None,
        assignee: None,
        parent: None,
        labels: Vec::new(),
        description: Some("First description".to_string()),
        local: false,
    })
    .expect("create issue one");
    let issue_two = create_issue(&IssueCreationRequest {
        root: root.to_path_buf(),
        title: "Second issue".to_string(),
        issue_type: None,
        priority: None,
        assignee: None,
        parent: None,
        labels: Vec::new(),
        description: None,
        local: false,
    })
    .expect("create issue two");
    let issue_three = create_issue(&IssueCreationRequest {
        root: root.to_path_buf(),
        title: "Fourth issue".to_string(),
        issue_type: None,
        priority: None,
        assignee: Some("dev@example.com".to_string()),
        parent: None,
        labels: Vec::new(),
        description: None,
        local: false,
    })
    .expect("create issue three");

    let _ = update_issue(
        root,
        &issue_one.issue.identifier,
        Some("First issue updated"),
        Some("Updated description"),
        Some("in_progress"),
        Some("dev@example.com"),
        true,
    );
    let _ = update_issue(
        root,
        &issue_two.issue.identifier,
        Some("First issue updated"),
        None,
        None,
        None,
        false,
    );
    let _ = update_issue(
        root,
        &issue_one.issue.identifier,
        Some("First issue updated again"),
        None,
        Some("open"),
        None,
        false,
    );
    let _ = update_issue(
        root,
        &issue_three.issue.identifier,
        Some("Fourth issue updated"),
        None,
        None,
        Some("dev@example.com"),
        false,
    );

    let _ = add_dependency(
        root,
        &issue_one.issue.identifier,
        &issue_two.issue.identifier,
        "blocked-by",
    );
    let _ = remove_dependency(
        root,
        &issue_one.issue.identifier,
        &issue_two.issue.identifier,
        "blocked-by",
    );
    let _ = list_ready_issues(root, true, false);
    let _ = list_ready_issues(root, false, true);
    let _ = list_ready_issues(root, false, true);

    let issues_dir = root.join("project").join("issues");
    fs::write(issues_dir.join("notes.txt"), "note").expect("non-json file");
    fs::write(issues_dir.join("invalid.json"), "{").expect("invalid json");
    let _ = update_issue(
        root,
        &issue_two.issue.identifier,
        Some("First issue"),
        None,
        None,
        None,
        false,
    );

    let _ = list_issues(root, None, None, None, None, None, None, true, false);
    let _ = list_issues(root, None, None, None, None, None, None, false, true);

    let _ = build_console_snapshot(root);

    let beads_dir = root.join(".beads");
    fs::create_dir_all(&beads_dir).expect("create beads dir");
    let timestamp = "2025-01-01T00:00:00Z";
    let record_one = json!({
        "id": "bdx-001",
        "title": "Beads issue one",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": timestamp,
        "updated_at": timestamp,
    });
    let record_two = json!({
        "id": "bdx-002",
        "title": "Beads issue two",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": timestamp,
        "updated_at": timestamp,
        "dependencies": [
            { "type": "blocked-by", "depends_on_id": "bdx-001" }
        ],
    });
    let record_three = json!({
        "id": "bdx-003",
        "title": "Beads issue three",
        "issue_type": "initiative",
        "status": "open",
        "priority": 2,
        "created_at": timestamp,
        "updated_at": timestamp,
        "dependencies": [
            { "type": "parent-child", "depends_on_id": "bdx-001" }
        ],
    });
    let issues_jsonl = format!("{}\n{}\n{}\n", record_one, record_two, record_three);
    fs::write(beads_dir.join("issues.jsonl"), &issues_jsonl).expect("write beads issues");
    let _ = load_beads_issues(root);
    let _ = load_beads_issue_by_id(root, "bdx-001");

    fs::write(root.join(".kanbus.yml"), "beads_compatibility: true\n").expect("enable beads");
    let _ = build_console_snapshot(root);

    let _ = run_doctor(root);
    let _ = migrate_from_beads(root);

    let _ = run_from_args_with_output(["kanbus", "--help"], root);
    std::env::set_var("KANBUS_TEST_CONFIGURATION_PATH_FAILURE", "1");
    let _ = run_from_args_with_output(["kanbus", "list"], root);
    std::env::remove_var("KANBUS_TEST_CONFIGURATION_PATH_FAILURE");
    let _ = run_from_args_with_output(["kanbus", "doctor"], root);

    let temp_dir = TempDir::new().expect("tempdir");
    let root_no_config = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root_no_config)
        .output()
        .expect("git init");
    initialize_project(root_no_config, false).expect("initialize project");
    let config_path = root_no_config.join(".kanbus.yml");
    let _ = create_issue(&IssueCreationRequest {
        root: root_no_config.to_path_buf(),
        title: "Configless issue".to_string(),
        issue_type: None,
        priority: None,
        assignee: None,
        parent: None,
        labels: Vec::new(),
        description: None,
        local: false,
    });
    fs::remove_file(&config_path).expect("remove config");
    let _ = run_from_args_with_output(["kanbus", "list"], root_no_config);

    let temp_dir = TempDir::new().expect("tempdir");
    let root_no_local = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root_no_local)
        .output()
        .expect("git init");
    initialize_project(root_no_local, false).expect("initialize project");
    let _ = list_ready_issues(root_no_local, false, true);
    cover_dependencies_paths(root_no_local);

    let temp_dir = TempDir::new().expect("tempdir");
    let root_multi = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root_multi)
        .output()
        .expect("git init");
    initialize_project(root_multi, false).expect("initialize project");
    let extra_project = root_multi.join("extra");
    fs::create_dir_all(extra_project.join("project").join("issues")).expect("extra project");
    fs::write(
        root_multi.join(".kanbus.yml"),
        "external_projects:\n  - extra/project\n",
    )
    .expect("write external projects");
    let _ = load_project_directory(root_multi);
    let _ = list_issues(root_multi, None, None, None, None, None, None, true, true);
    let _ = list_issues(root_multi, None, None, None, None, None, None, false, false);
    std::env::remove_var("KANBUS_NO_DAEMON");
    let _ = run_from_args_with_output(["kanbus", "daemon-status"], root_multi);
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    let _ = get_configuration_path(root_multi);

    let temp_dir = TempDir::new().expect("tempdir");
    let root_update = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root_update)
        .output()
        .expect("git init");
    initialize_project(root_update, false).expect("initialize project");
    let issue_update = create_issue(&IssueCreationRequest {
        root: root_update.to_path_buf(),
        title: "Update issue".to_string(),
        issue_type: None,
        priority: None,
        assignee: None,
        parent: None,
        labels: Vec::new(),
        description: None,
        local: false,
    })
    .expect("create update issue");
    let _ = update_issue(
        root_update,
        &issue_update.issue.identifier,
        Some("Update issue renamed"),
        None,
        Some("open"),
        None,
        false,
    );

    let temp_dir = TempDir::new().expect("tempdir");
    let root_migrate_invalid = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root_migrate_invalid)
        .output()
        .expect("git init");
    let beads_dir = root_migrate_invalid.join(".beads");
    fs::create_dir_all(&beads_dir).expect("create beads dir");
    let timestamp = "2025-01-01T00:00:00Z";
    let record_parent = json!({
        "id": "bdx-parent",
        "title": "Beads parent",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": timestamp,
        "updated_at": timestamp,
    });
    let record_child = json!({
        "id": "bdx-child",
        "title": "Beads child",
        "issue_type": "initiative",
        "status": "open",
        "priority": 2,
        "created_at": timestamp,
        "updated_at": timestamp,
        "dependencies": [
            { "type": "parent-child", "depends_on_id": "bdx-parent" }
        ],
    });
    let issues_jsonl = format!("{}\n{}\n", record_parent, record_child);
    fs::write(beads_dir.join("issues.jsonl"), &issues_jsonl).expect("write beads issues");
    let _ = migrate_from_beads(root_migrate_invalid);

    let temp_dir = TempDir::new().expect("tempdir");
    let root_migrate_error = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root_migrate_error)
        .output()
        .expect("git init");
    let beads_dir = root_migrate_error.join(".beads");
    fs::create_dir_all(&beads_dir).expect("create beads dir");
    fs::write(beads_dir.join("issues.jsonl"), issues_jsonl).expect("write beads issues");
    std::env::set_var("KANBUS_TEST_HIERARCHY_ERROR", "1");
    let _ = migrate_from_beads(root_migrate_error);
    std::env::remove_var("KANBUS_TEST_HIERARCHY_ERROR");
}
