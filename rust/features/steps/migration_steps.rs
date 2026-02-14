use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, then, when};
use serde_json::Value;

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::migration::migrate_from_beads;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn fixture_beads_dir() -> PathBuf {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("repo root");
    root.join("specs")
        .join("fixtures")
        .join("beads_repo")
        .join(".beads")
}

fn copy_dir(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).expect("create destination");
    for entry in fs::read_dir(source).expect("read source") {
        let entry = entry.expect("entry");
        let path = entry.path();
        let target = destination.join(entry.file_name());
        if path.is_dir() {
            copy_dir(&path, &target);
        } else {
            fs::copy(&path, &target).expect("copy file");
        }
    }
}

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[given("a git repository with a .beads issues database")]
fn given_repo_with_beads(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let target_beads = repo_path.join(".beads");
    copy_dir(&fixture_beads_dir(), &target_beads);
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with a .beads issues database containing blank lines")]
fn given_repo_with_blank_lines(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("beads dir");
    let record = serde_json::json!({
        "id": "kanbus-001",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": []
    });
    let lines = format!(
        "{}\n\n{}\n",
        record.to_string(),
        serde_json::json!({
            "id": "kanbus-002",
            "title": "Title",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00Z",
            "updated_at": "2026-02-11T00:00:00Z",
            "dependencies": [],
            "comments": []
        })
        .to_string()
    );
    fs::write(beads_dir.join("issues.jsonl"), lines).expect("write issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with Beads metadata and dependencies")]
fn given_repo_with_metadata(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("beads dir");
    let base = serde_json::json!({
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": []
    });
    let parent = serde_json::json!({
        "id": "kanbus-parent",
        "title": base["title"],
        "issue_type": base["issue_type"],
        "status": base["status"],
        "priority": base["priority"],
        "created_at": base["created_at"],
        "updated_at": base["updated_at"],
        "dependencies": base["dependencies"],
        "comments": base["comments"]
    });
    let child = serde_json::json!({
        "id": "kanbus-child",
        "title": base["title"],
        "issue_type": base["issue_type"],
        "status": base["status"],
        "priority": base["priority"],
        "created_at": base["created_at"],
        "updated_at": base["updated_at"],
        "dependencies": [{"type": "blocked-by", "depends_on_id": "kanbus-parent"}],
        "comments": base["comments"],
        "notes": "Notes",
        "acceptance_criteria": "Criteria",
        "close_reason": "Done",
        "owner": "dev@example.com"
    });
    let lines = format!("{}\n{}", parent.to_string(), child.to_string());
    fs::write(beads_dir.join("issues.jsonl"), lines).expect("write issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with a Beads feature issue")]
fn given_repo_with_feature_issue(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("beads dir");
    let record = serde_json::json!({
        "id": "bdx-feature",
        "title": "Feature issue",
        "issue_type": "feature",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": []
    });
    fs::write(beads_dir.join("issues.jsonl"), record.to_string()).expect("write issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with Beads epic parent and child")]
fn given_repo_with_epic_parent_child(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("beads dir");
    let parent = serde_json::json!({
        "id": "bdx-parent",
        "title": "Parent epic",
        "issue_type": "epic",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": []
    });
    let child = serde_json::json!({
        "id": "bdx-child",
        "title": "Child epic",
        "issue_type": "epic",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [
            {
                "issue_id": "bdx-child",
                "depends_on_id": "bdx-parent",
                "type": "parent-child",
                "created_at": "2026-02-11T00:00:00Z",
                "created_by": "dev@example.com"
            }
        ],
        "comments": []
    });
    let lines = format!("{}\n{}", parent.to_string(), child.to_string());
    fs::write(beads_dir.join("issues.jsonl"), lines).expect("write issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with Beads issues containing fractional timestamps")]
fn given_repo_with_fractional_timestamps(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("beads dir");
    let records = vec![
        serde_json::json!({
            "id": "bdx-frac-short",
            "title": "Short fractional",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.1+00:00",
            "updated_at": "2026-02-11T00:00:00.1+00:00",
            "dependencies": [],
            "comments": []
        }),
        serde_json::json!({
            "id": "bdx-frac-long",
            "title": "Long fractional",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.1234567+00:00",
            "updated_at": "2026-02-11T00:00:00.1234567+00:00",
            "dependencies": [],
            "comments": []
        }),
        serde_json::json!({
            "id": "bdx-frac-nozone",
            "title": "No zone",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.123",
            "updated_at": "2026-02-11T00:00:00.123",
            "dependencies": [],
            "comments": []
        }),
        serde_json::json!({
            "id": "bdx-frac-negative",
            "title": "Negative offset",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.123456-05:00",
            "updated_at": "2026-02-11T00:00:00.123456-05:00",
            "dependencies": [],
            "comments": []
        }),
    ];
    let lines = records
        .into_iter()
        .map(|record| record.to_string())
        .collect::<Vec<_>>()
        .join("\n");
    fs::write(beads_dir.join("issues.jsonl"), lines).expect("write issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a Kanbus project already exists")]
fn given_kanbus_project_exists(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    fs::create_dir_all(cwd.join("project").join("issues")).expect("create project");
}

#[given("a git repository without a .beads directory")]
fn given_repo_without_beads(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with an empty .beads directory")]
fn given_repo_empty_beads(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    fs::create_dir_all(repo_path.join(".beads")).expect("create beads dir");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with an empty issues.jsonl file")]
fn given_repo_with_empty_issues_jsonl(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("create beads dir");
    fs::write(beads_dir.join("issues.jsonl"), "").expect("write empty issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with a .beads issues database containing an invalid id")]
fn given_repo_with_invalid_beads_id(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let beads_dir = repo_path.join(".beads");
    fs::create_dir_all(&beads_dir).expect("create beads dir");
    let record = serde_json::json!({
        "id": "invalidid",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": []
    });
    fs::write(beads_dir.join("issues.jsonl"), record.to_string()).expect("write issues");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[when("I run \"kanbus migrate\"")]
fn when_run_migrate(world: &mut KanbusWorld) {
    run_cli(world, "kanbus migrate");
}

#[when("I validate migration error cases")]
fn when_validate_migration_errors(world: &mut KanbusWorld) {
    let mut errors = Vec::new();

    let mut run_case = |records: Vec<serde_json::Value>, label: &str| {
        let temp_dir = tempfile::TempDir::new().expect("tempdir");
        let repo_path = temp_dir.path().join(format!("case-{label}"));
        fs::create_dir_all(&repo_path).expect("create repo dir");
        Command::new("git")
            .args(["init"])
            .current_dir(&repo_path)
            .output()
            .expect("git init failed");
        let beads_dir = repo_path.join(".beads");
        fs::create_dir_all(&beads_dir).expect("create beads dir");
        let lines: Vec<String> = records
            .into_iter()
            .map(|record| serde_json::to_string(&record).expect("serialize record"))
            .collect();
        fs::write(beads_dir.join("issues.jsonl"), lines.join("\n")).expect("write issues");
        match migrate_from_beads(&repo_path) {
            Ok(_) => errors.push("expected error not raised".to_string()),
            Err(error) => errors.push(error.to_string()),
        }
    };

    let valid_base = serde_json::json!({
        "id": "kanbus-001",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "closed_at": serde_json::Value::Null,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": []
    });

    let build_record = |base: &serde_json::Value, updates: Vec<(&str, serde_json::Value)>| {
        let mut map = base.as_object().expect("object").clone();
        for (key, value) in updates {
            map.insert(key.to_string(), value);
        }
        serde_json::Value::Object(map)
    };

    run_case(
        vec![serde_json::json!({"title": "Missing id"})],
        "missing-id",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("title", serde_json::json!(""))],
        )],
        "missing-title",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("issue_type", serde_json::json!(""))],
        )],
        "missing-type",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("status", serde_json::json!(""))],
        )],
        "missing-status",
    );
    let mut record_without_priority = valid_base.as_object().expect("object").clone();
    record_without_priority.remove("priority");
    run_case(
        vec![serde_json::Value::Object(record_without_priority)],
        "missing-priority-field",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("priority", serde_json::Value::Null)],
        )],
        "missing-priority",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("priority", serde_json::json!(99))],
        )],
        "invalid-priority",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("issue_type", serde_json::json!("unknown"))],
        )],
        "unknown-type",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("status", serde_json::json!("invalid"))],
        )],
        "invalid-status",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "dependencies",
                serde_json::json!([{"type": "", "depends_on_id": ""}]),
            )],
        )],
        "invalid-dependency",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "dependencies",
                serde_json::json!([{"type": "blocked-by", "depends_on_id": "kanbus-missing"}]),
            )],
        )],
        "missing-dependency",
    );
    run_case(
        vec![
            build_record(
                &valid_base,
                vec![
                    ("id", serde_json::json!("kanbus-child")),
                    (
                        "dependencies",
                        serde_json::json!([
                            {"type": "parent-child", "depends_on_id": "kanbus-parent"},
                            {"type": "parent-child", "depends_on_id": "kanbus-parent-2"}
                        ]),
                    ),
                ],
            ),
            build_record(
                &valid_base,
                vec![("id", serde_json::json!("kanbus-parent"))],
            ),
            build_record(
                &valid_base,
                vec![("id", serde_json::json!("kanbus-parent-2"))],
            ),
        ],
        "multiple-parents",
    );
    run_case(
        vec![
            serde_json::json!({
                "id": "kanbus-child",
                "title": "Child",
                "issue_type": "task",
                "status": "open",
                "priority": 2,
                "created_at": "2026-02-11T00:00:00Z",
                "updated_at": "2026-02-11T00:00:00Z",
                "dependencies": [{"type": "parent-child", "depends_on_id": "kanbus-parent"}],
                "comments": []
            }),
            serde_json::json!({
                "id": "kanbus-parent",
                "title": "Parent",
                "status": "open",
                "priority": 2,
                "created_at": "2026-02-11T00:00:00Z",
                "updated_at": "2026-02-11T00:00:00Z"
            }),
        ],
        "parent-issue-type-missing",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "comments",
                serde_json::json!([{"author": "", "text": "bad", "created_at": "2026-02-11T00:00:00Z"}]),
            )],
        )],
        "invalid-comment",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "comments",
                serde_json::json!([{"author": "dev", "text": "ok"}]),
            )],
        )],
        "comment-created-missing",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "comments",
                serde_json::json!([{"author": "dev", "text": "ok", "created_at": 123}]),
            )],
        )],
        "comment-created-not-string",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "comments",
                serde_json::json!([{"author": "dev", "text": "ok", "created_at": "bad"}]),
            )],
        )],
        "comment-created-invalid",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "comments",
                serde_json::json!([{"author": "dev", "text": "ok", "created_at": ""}]),
            )],
        )],
        "comment-created-empty",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("created_at", serde_json::Value::Null)],
        )],
        "created-missing",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("created_at", serde_json::json!(""))],
        )],
        "created-empty",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("created_at", serde_json::json!(123))],
        )],
        "created-not-string",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![("created_at", serde_json::json!("invalid"))],
        )],
        "created-invalid",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "created_at",
                serde_json::json!("2026-02-11T00:00:00.bad+00:00"),
            )],
        )],
        "created-invalid-fractional",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "created_at",
                serde_json::json!("2026-02-11T00:00:00.bad-00:00"),
            )],
        )],
        "created-invalid-negative",
    );
    run_case(
        vec![build_record(
            &valid_base,
            vec![(
                "created_at",
                serde_json::json!("2026-02-11T00:00:00.123+00:00-00"),
            )],
        )],
        "created-invalid-mixed-offset",
    );

    world.migration_errors = errors;
}

#[then("a Kanbus project should be initialized")]
fn then_kanbus_initialized(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    assert!(project_dir.is_dir());
}

#[then("all Beads issues should be converted to Kanbus issues")]
fn then_beads_converted(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let issues_path = cwd.join(".beads").join("issues.jsonl");
    let contents = fs::read_to_string(issues_path).expect("read issues");
    let line_count = contents
        .lines()
        .filter(|line| !line.trim().is_empty())
        .count();
    let project_dir = load_project_dir(world);
    let issue_files = fs::read_dir(project_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.path().extension().and_then(|ext| ext.to_str()) == Some("json"))
        .count();
    assert_eq!(issue_files, line_count);
}

#[then("migrated issues should include metadata and dependencies")]
fn then_migration_includes_metadata(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-child.json");
    let contents = fs::read_to_string(issue_path).expect("read issue");
    let payload: serde_json::Value = serde_json::from_str(&contents).expect("parse issue");
    let custom = payload
        .get("custom")
        .and_then(|value| value.as_object())
        .expect("custom");
    assert_eq!(
        custom.get("beads_notes").and_then(|v| v.as_str()),
        Some("Notes")
    );
    assert_eq!(
        custom
            .get("beads_acceptance_criteria")
            .and_then(|v| v.as_str()),
        Some("Criteria")
    );
    assert_eq!(
        custom.get("beads_close_reason").and_then(|v| v.as_str()),
        Some("Done")
    );
    assert_eq!(
        custom.get("beads_owner").and_then(|v| v.as_str()),
        Some("dev@example.com")
    );
    let deps = payload
        .get("dependencies")
        .and_then(|v| v.as_array())
        .expect("deps");
    let has_dep = deps.iter().any(|item| {
        item.get("target").and_then(|v| v.as_str()) == Some("kanbus-parent")
            && item.get("type").and_then(|v| v.as_str()) == Some("blocked-by")
    });
    assert!(has_dep);
}

#[then(expr = "migrated issue {string} should have type {string}")]
fn then_migrated_issue_type(world: &mut KanbusWorld, identifier: String, issue_type: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    let payload: Value = serde_json::from_str(&contents).expect("parse issue");
    assert_eq!(
        payload.get("type").and_then(|value| value.as_str()),
        Some(issue_type.as_str())
    );
}

#[then(expr = "migrated issue {string} should have parent {string}")]
fn then_migrated_issue_parent(world: &mut KanbusWorld, identifier: String, parent: String) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    let payload: Value = serde_json::from_str(&contents).expect("parse issue");
    assert_eq!(
        payload.get("parent").and_then(|value| value.as_str()),
        Some(parent.as_str())
    );
}

#[then(expr = "migrated issue {string} should preserve beads issue type {string}")]
fn then_migrated_issue_preserves_type(
    world: &mut KanbusWorld,
    identifier: String,
    issue_type: String,
) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    let payload: Value = serde_json::from_str(&contents).expect("parse issue");
    let custom = payload.get("custom").and_then(|value| value.as_object());
    assert_eq!(
        custom
            .and_then(|map| map.get("beads_issue_type"))
            .and_then(|value| value.as_str()),
        Some(issue_type.as_str())
    );
}

#[then(expr = "migration errors should include {string}")]
fn then_migration_errors_include(world: &mut KanbusWorld, message: String) {
    assert!(world.migration_errors.contains(&message));
}
