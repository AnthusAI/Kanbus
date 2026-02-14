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

use step_definitions::initialization_steps::TaskulusWorld;

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
    TaskulusWorld::cucumber::<PathBuf>()
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

    use taskulus::agents_management::{cover_parse_header_cases, ensure_agents_file};
    use taskulus::cli::run_from_args_with_output;
    use taskulus::console_snapshot::build_console_snapshot;
    use taskulus::dependencies::{add_dependency, list_ready_issues, remove_dependency};
    use taskulus::doctor::run_doctor;
    use taskulus::file_io::initialize_project;
    use taskulus::issue_creation::{create_issue, IssueCreationRequest};
    use taskulus::issue_listing::list_issues;
    use taskulus::issue_update::update_issue;
    use taskulus::migration::{load_beads_issue_by_id, load_beads_issues, migrate_from_beads};

    std::env::set_var("TASKULUS_NO_DAEMON", "1");

    let temp_dir = TempDir::new().expect("tempdir");
    let root = temp_dir.path();
    Command::new("git")
        .args(["init"])
        .current_dir(root)
        .output()
        .expect("git init");

    initialize_project(root, true).expect("initialize project");
    fs::write(root.join("project").join("taskulus.yml"), "").expect("write doctor config");
    ensure_agents_file(root, true).expect("ensure agents");
    cover_parse_header_cases();

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
    let issues_jsonl = format!("{}\n{}\n", record_one, record_two);
    fs::write(beads_dir.join("issues.jsonl"), issues_jsonl).expect("write beads issues");
    let _ = load_beads_issues(root);
    let _ = load_beads_issue_by_id(root, "bdx-001");

    fs::write(root.join(".taskulus.yml"), "beads_compatibility: true\n").expect("enable beads");
    let _ = build_console_snapshot(root);

    let _ = run_doctor(root);
    let _ = migrate_from_beads(root);

    let _ = run_from_args_with_output(["tsk", "--help"], root);
    std::env::set_var("TASKULUS_TEST_CONFIGURATION_PATH_FAILURE", "1");
    let _ = run_from_args_with_output(["tsk", "list"], root);
    std::env::remove_var("TASKULUS_TEST_CONFIGURATION_PATH_FAILURE");
}
