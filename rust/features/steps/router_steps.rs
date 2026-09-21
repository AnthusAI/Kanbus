use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use chrono::{TimeZone, Utc};
use cucumber::{gherkin::Step, given, then, when};
use kanbus::event_history::{now_timestamp, write_events_batch, EventRecord, EventType};
use serde_json::{json, Value};
use serde_yaml::{Mapping, Value as Yaml};
use tempfile::TempDir;

use crate::step_definitions::initialization_steps::{
    run_from_args_in_blocking_thread, KanbusWorld,
};
use kanbus::file_io::{get_configuration_path, load_project_directory};
use kanbus::models::{IssueData, ProjectConfiguration};

const VALID_ROUTER: &str = r#"router:
  workflow:
    pending: open
    active: in_progress
    review: review
    blocked: blocked
    terminal: [closed]
  limits:
    project_wip: 4
    review_wip: 2
  forge:
    repository: anthusai/kanbus
  providers:
    codex-default:
      adapter: codex
  classes:
    implementation:
      providers: [codex-default]
"#;

fn root(world: &KanbusWorld) -> &Path {
    world
        .working_directory
        .as_deref()
        .expect("working directory")
}

fn project_dir(world: &KanbusWorld) -> PathBuf {
    load_project_directory(root(world)).expect("project directory")
}

fn ensure_default_project(world: &mut KanbusWorld) {
    if world.working_directory.is_some() {
        return;
    }
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    let temp_dir = TempDir::new().expect("temporary directory");
    let repo_root = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_root).expect("create repository");
    let initialized = Command::new("git")
        .args(["init"])
        .current_dir(&repo_root)
        .output()
        .expect("git init");
    assert!(initialized.status.success());
    world.working_directory = Some(repo_root);
    world.temp_dir = Some(temp_dir);
    let args = vec!["kanbus".to_string(), "init".to_string()];
    match run_from_args_in_blocking_thread(args, root(world)) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => panic!("kanbus init failed: {error}"),
    }
}

fn read_yaml(world: &KanbusWorld) -> (PathBuf, Yaml) {
    let path = get_configuration_path(root(world)).expect("configuration path");
    let bytes = fs::read(&path).expect("read configuration");
    let yaml = serde_yaml::from_slice(&bytes).expect("parse configuration");
    (path, yaml)
}

fn write_yaml(world: &KanbusWorld, yaml: &Yaml) {
    let (path, _) = read_yaml(world);
    fs::write(path, serde_yaml::to_string(yaml).expect("serialize config")).expect("write config");
}

fn mapping(value: &mut Yaml) -> &mut Mapping {
    value.as_mapping_mut().expect("configuration mapping")
}

fn set_router_yaml(world: &KanbusWorld, source: &str) {
    let mut root_value = read_yaml(world).1;
    let router_doc: Yaml = serde_yaml::from_str(source).expect("router fixture yaml");
    let router = router_doc.get("router").cloned().expect("router key");
    if router
        .get("workflow")
        .and_then(|workflow| workflow.get("review"))
        .and_then(Yaml::as_str)
        == Some("review")
    {
        add_review_status_and_workflow(&mut root_value);
    }
    mapping(&mut root_value).insert(Yaml::String("router".to_string()), router);
    write_yaml(world, &root_value);
}

fn add_review_status_and_workflow(root_value: &mut Yaml) {
    let root = mapping(root_value);
    let statuses_key = Yaml::String("statuses".to_string());
    let statuses = root
        .get(&statuses_key)
        .and_then(Yaml::as_sequence)
        .expect("status list");
    if !statuses
        .iter()
        .any(|status| status.get("key").and_then(Yaml::as_str) == Some("review"))
    {
        let mut review_status = Mapping::new();
        review_status.insert(
            Yaml::String("key".to_string()),
            Yaml::String("review".to_string()),
        );
        review_status.insert(
            Yaml::String("name".to_string()),
            Yaml::String("Review".to_string()),
        );
        review_status.insert(
            Yaml::String("category".to_string()),
            Yaml::String("In progress".to_string()),
        );
        review_status.insert(
            Yaml::String("semantic_category".to_string()),
            Yaml::String("in_progress".to_string()),
        );
        review_status.insert(Yaml::String("collapsed".to_string()), Yaml::Bool(false));
        let root = mapping(root_value);
        let statuses = root
            .get_mut(&statuses_key)
            .and_then(Yaml::as_sequence_mut)
            .expect("status list");
        statuses.push(Yaml::Mapping(review_status));
    }
    let root = mapping(root_value);
    let workflows = root
        .get_mut(Yaml::String("workflows".to_string()))
        .and_then(Yaml::as_mapping_mut)
        .expect("workflows");
    let default_key = Yaml::String("default".to_string());
    let default = workflows
        .get_mut(&default_key)
        .and_then(Yaml::as_mapping_mut)
        .expect("default workflow");
    for from in ["open", "in_progress"] {
        if let Some(destinations) = default
            .get_mut(Yaml::String(from.to_string()))
            .and_then(Yaml::as_sequence_mut)
        {
            if !destinations
                .iter()
                .any(|item| item.as_str() == Some("review"))
            {
                destinations.push(Yaml::String("review".to_string()));
            }
        }
    }
    if !default.contains_key(Yaml::String("review".to_string())) {
        default.insert(
            Yaml::String("review".to_string()),
            Yaml::Sequence(vec![
                Yaml::String("in_progress".to_string()),
                Yaml::String("blocked".to_string()),
                Yaml::String("closed".to_string()),
            ]),
        );
    }
    let transition_labels = mapping(root_value)
        .get_mut(Yaml::String("transition_labels".to_string()))
        .and_then(Yaml::as_mapping_mut)
        .expect("transition labels");
    let default_labels = transition_labels
        .get_mut(default_key)
        .and_then(Yaml::as_mapping_mut)
        .expect("default transition labels");
    let mut review_labels = Mapping::new();
    review_labels.insert(
        Yaml::String("in_progress".to_string()),
        Yaml::String("Resume work".to_string()),
    );
    review_labels.insert(
        Yaml::String("blocked".to_string()),
        Yaml::String("Block".to_string()),
    );
    review_labels.insert(
        Yaml::String("closed".to_string()),
        Yaml::String("Complete".to_string()),
    );
    default_labels.insert(
        Yaml::String("review".to_string()),
        Yaml::Mapping(review_labels),
    );
    for from in ["open", "in_progress"] {
        if let Some(labels) = default_labels
            .get_mut(Yaml::String(from.to_string()))
            .and_then(Yaml::as_mapping_mut)
        {
            labels.insert(
                Yaml::String("review".to_string()),
                Yaml::String("Request review".to_string()),
            );
        }
    }
}

fn set_router_path(world: &KanbusWorld, path: &[&str], value: Yaml) {
    let mut root_value = read_yaml(world).1;
    let mut current = mapping(&mut root_value)
        .get_mut(Yaml::String("router".to_string()))
        .and_then(Yaml::as_mapping_mut)
        .expect("router mapping");
    for part in &path[..path.len() - 1] {
        let key = Yaml::String((*part).to_string());
        if !current.contains_key(&key) {
            current.insert(key.clone(), Yaml::Mapping(Mapping::new()));
        }
        current = current
            .get_mut(key)
            .and_then(Yaml::as_mapping_mut)
            .expect("nested mapping");
    }
    current.insert(Yaml::String(path[path.len() - 1].to_string()), value);
    write_yaml(world, &root_value);
}

fn add_provider_profile(
    world: &KanbusWorld,
    name: &str,
    adapter: &str,
    command: Option<&str>,
    args: Vec<String>,
) {
    let mut root_value = read_yaml(world).1;
    let router = mapping(&mut root_value)
        .get_mut(Yaml::String("router".to_string()))
        .and_then(Yaml::as_mapping_mut)
        .expect("router mapping");
    let provider_key = Yaml::String("providers".to_string());
    if !router.contains_key(&provider_key) {
        router.insert(provider_key.clone(), Yaml::Mapping(Mapping::new()));
    }
    let providers = router
        .get_mut(provider_key)
        .and_then(Yaml::as_mapping_mut)
        .expect("providers mapping");
    let mut profile = Mapping::new();
    profile.insert(
        Yaml::String("adapter".to_string()),
        Yaml::String(adapter.to_string()),
    );
    if let Some(command) = command {
        profile.insert(
            Yaml::String("command".to_string()),
            Yaml::String(command.to_string()),
        );
    }
    if !args.is_empty() {
        profile.insert(
            Yaml::String("args".to_string()),
            serde_yaml::to_value(args).unwrap(),
        );
    }
    providers.insert(Yaml::String(name.to_string()), Yaml::Mapping(profile));
    write_yaml(world, &root_value);
}

fn build_issue(
    identifier: &str,
    status: &str,
    labels: Vec<String>,
    parent: Option<String>,
    assignee: Option<String>,
) -> IssueData {
    let now = Utc.with_ymd_and_hms(2026, 9, 17, 10, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: format!("Router fixture {identifier}"),
        description: String::new(),
        issue_type: "task".to_string(),
        status: status.to_string(),
        priority: 2,
        assignee,
        creator: None,
        parent,
        labels,
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
        custom: BTreeMap::new(),
    }
}

fn put_issue(world: &KanbusWorld, issue: &IssueData) {
    let path = project_dir(world)
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    fs::create_dir_all(path.parent().unwrap()).expect("create issues dir");
    fs::write(
        path,
        serde_json::to_vec_pretty(issue).expect("serialize issue"),
    )
    .expect("write issue");
}

fn load_issue(world: &KanbusWorld, identifier: &str) -> IssueData {
    serde_json::from_slice(
        &fs::read(
            project_dir(world)
                .join("issues")
                .join(format!("{identifier}.json")),
        )
        .expect("read issue"),
    )
    .expect("parse issue")
}

fn read_router_fixture_events(world: &KanbusWorld) -> Vec<EventRecord> {
    fs::read_dir(project_dir(world).join("events"))
        .expect("router event directory")
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<EventRecord>(&bytes).ok())
        .collect()
}

fn seed_active_router_attempt(
    world: &mut KanbusWorld,
    issue_id: &str,
    attempt: u32,
    checkpoint: Option<(&str, u64)>,
) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    put_issue(
        world,
        &build_issue(
            issue_id,
            "in_progress",
            vec!["agent-class:implementation".to_string()],
            None,
            None,
        ),
    );
    let now = now_timestamp();
    let claim_id = format!("fixture-{issue_id}-r{attempt}");
    let mut events = vec![EventRecord::new(
        format!("router:{issue_id}"),
        EventType::RouterAttempt,
        "router-step-fixture",
        json!({
            "action":"started",
            "attempt":attempt,
            "claim_id":claim_id,
            "revision":attempt,
            "provider_profile":"codex-default"
        }),
        now.clone(),
    )];
    if let Some((reference, revision)) = checkpoint {
        events.push(EventRecord::new(
            format!("router:{issue_id}"),
            EventType::RouterAttempt,
            "router-step-fixture",
            json!({
                "action":"checkpoint_accepted",
                "attempt":attempt,
                "claim_id":claim_id,
                "revision":revision,
                "checkpoint_ref":reference,
                "checkpoint_revision":revision
            }),
            now,
        ));
    }
    write_events_batch(&project_dir(world).join("events"), &events)
        .expect("write active router attempt fixture");
}

fn router_event_for(
    world: &KanbusWorld,
    issue_id: &str,
    predicate: impl Fn(&EventRecord) -> bool,
) -> EventRecord {
    read_router_fixture_events(world)
        .into_iter()
        .filter(|event| event.issue_id == format!("router:{issue_id}"))
        .find(predicate)
        .expect("matching router event")
}

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    match run_from_args_in_blocking_thread(args, root(world)) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            let mut exit = 1;
            let mut stdout = String::new();
            let stderr = match error {
                kanbus::error::KanbusError::CommandFailure { exit_code, message } => {
                    exit = exit_code;
                    format!("{message}\n")
                }
                kanbus::error::KanbusError::CommandFailureWithOutput {
                    exit_code,
                    stdout: value,
                    stderr,
                } => {
                    exit = exit_code;
                    stdout = value;
                    format!("{stderr}\n")
                }
                other => other.to_string(),
            };
            world.exit_code = Some(exit);
            world.stdout = Some(stdout);
            world.stderr = Some(stderr);
        }
    }
    world.last_command = Some(command.to_string());
}

const ROUTER_WORKER_B: &str = "KANBUS_TEST_ROUTER_WORKER_B";

fn worker_b_root(world: &KanbusWorld) -> PathBuf {
    PathBuf::from(
        world
            .environment_overrides
            .get(ROUTER_WORKER_B)
            .expect("second router worker checkout"),
    )
}

fn git_commit_fixture(root: &Path, message: &str) {
    let add = Command::new("git")
        .args(["add", "-A"])
        .current_dir(root)
        .output()
        .expect("stage router fixture");
    assert!(
        add.status.success(),
        "git add failed: {}",
        String::from_utf8_lossy(&add.stderr)
    );
    let commit = Command::new("git")
        .args([
            "-c",
            "user.name=Router Fixture",
            "-c",
            "user.email=router-fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            message,
        ])
        .current_dir(root)
        .output()
        .expect("commit router fixture");
    assert!(
        commit.status.success(),
        "git commit failed: {}",
        String::from_utf8_lossy(&commit.stderr)
    );
}

fn clone_router_worker(world: &mut KanbusWorld) {
    let source = root(world).to_path_buf();
    git_commit_fixture(&source, "router coordination fixture base");
    let temp_path = world
        .temp_dir
        .as_ref()
        .expect("temporary router project")
        .path();
    let bare_remote = temp_path.join("router-shared.git");
    let bare_clone = Command::new("git")
        .args(["clone", "--bare"])
        .arg(&source)
        .arg(&bare_remote)
        .output()
        .expect("create shared router test remote");
    assert!(
        bare_clone.status.success(),
        "git bare clone failed: {}",
        String::from_utf8_lossy(&bare_clone.stderr)
    );
    let add_remote = Command::new("git")
        .args(["remote", "add", "origin"])
        .arg(&bare_remote)
        .current_dir(&source)
        .output()
        .expect("configure source checkout remote");
    assert!(
        add_remote.status.success(),
        "git remote add failed: {}",
        String::from_utf8_lossy(&add_remote.stderr)
    );
    let destination = temp_path.join("router-worker-b");
    let cloned = Command::new("git")
        .args(["clone", "--shared"])
        .arg(&bare_remote)
        .arg(&destination)
        .output()
        .expect("clone router worker project");
    assert!(
        cloned.status.success(),
        "git clone failed: {}",
        String::from_utf8_lossy(&cloned.stderr)
    );
    world.environment_overrides.insert(
        ROUTER_WORKER_B.to_string(),
        destination.display().to_string(),
    );
}

fn mutate_yaml_at(root: &Path, keys: &[&str], value: Yaml) {
    let path = get_configuration_path(root).expect("configuration path");
    let bytes = fs::read(&path).expect("read project configuration");
    let mut document: Yaml = serde_yaml::from_slice(&bytes).expect("parse project configuration");
    let mut current = mapping(&mut document);
    for key in &keys[..keys.len() - 1] {
        current = current
            .get_mut(Yaml::String((*key).to_string()))
            .and_then(Yaml::as_mapping_mut)
            .expect("configuration section");
    }
    current.insert(Yaml::String(keys[keys.len() - 1].to_string()), value);
    fs::write(
        path,
        serde_yaml::to_string(&document).expect("serialize configuration"),
    )
    .expect("write project configuration");
}

fn configure_worker_pair(world: &KanbusWorld, keys: &[&str], value: Yaml) {
    mutate_yaml_at(root(world), keys, value.clone());
    mutate_yaml_at(&worker_b_root(world), keys, value);
}

fn set_multi_coordination_providers(world: &KanbusWorld, providers: &[&str]) {
    configure_worker_pair(
        world,
        &["coordination", "providers"],
        Yaml::Sequence(
            providers
                .iter()
                .map(|provider| Yaml::String((*provider).to_string()))
                .collect(),
        ),
    );
    git_commit_fixture(root(world), "router coordination settings");
    git_commit_fixture(&worker_b_root(world), "router coordination settings");
}

fn seed_multi_worker_package(world: &KanbusWorld, issue_id: &str, status: &str) {
    let issue = build_issue(
        issue_id,
        status,
        vec!["agent-class:implementation".to_string()],
        None,
        None,
    );
    put_issue(world, &issue);
    let path = load_project_directory(&worker_b_root(world))
        .expect("worker B project directory")
        .join("issues")
        .join(format!("{issue_id}.json"));
    fs::write(
        path,
        serde_json::to_vec_pretty(&issue).expect("serialize package fixture"),
    )
    .expect("write worker B package fixture");
}

fn read_events_at(root: &Path) -> Vec<EventRecord> {
    let project_dir = load_project_directory(root).expect("router worker project directory");
    let Ok(entries) = fs::read_dir(project_dir.join("events")) else {
        return Vec::new();
    };
    entries
        .flatten()
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<EventRecord>(&bytes).ok())
        .collect()
}

fn read_shared_router_events(root: &Path) -> Vec<EventRecord> {
    let resolved_root = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(root)
        .output()
        .expect("resolve router repository root");
    if !resolved_root.status.success() {
        return Vec::new();
    }
    let root = PathBuf::from(String::from_utf8_lossy(&resolved_root.stdout).trim());
    let fetched = Command::new("git")
        .args([
            "fetch",
            "--quiet",
            "origin",
            "+refs/heads/kanbus/router-state:refs/remotes/origin/kanbus/router-state",
        ])
        .current_dir(&root)
        .output()
        .expect("fetch shared router state");
    if !fetched.status.success() {
        return Vec::new();
    }
    let Some(relative_project) = load_project_directory(&root)
        .expect("load project directory")
        .strip_prefix(&root)
        .ok()
        .map(Path::to_path_buf)
    else {
        return Vec::new();
    };
    let events_path = relative_project.join("events");
    let tree = Command::new("git")
        .args([
            "ls-tree",
            "-r",
            "--name-only",
            "origin/kanbus/router-state",
            "--",
        ])
        .arg(&events_path)
        .current_dir(&root)
        .output()
        .expect("list shared router event files");
    if !tree.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&tree.stdout)
        .lines()
        .filter(|path| path.ends_with(".json"))
        .filter_map(|path| {
            let shown = Command::new("git")
                .args(["show", &format!("origin/kanbus/router-state:{path}")])
                .current_dir(&root)
                .output()
                .ok()?;
            shown.status.success().then_some(shown.stdout)
        })
        .filter_map(|bytes| serde_json::from_slice::<EventRecord>(&bytes).ok())
        .collect()
}

fn claim_result_for_worker(root: &Path, issue_id: &str, worker: &str) -> Result<String, String> {
    kanbus::coordination::run_coordination(
        root,
        kanbus::coordination::CoordinationOperation::Claim {
            resource: format!("router:issue:{issue_id}"),
            owner: worker.to_string(),
            claim_id: format!("{worker}-{issue_id}"),
            revision: 1,
        },
    )
    .map_err(|error| {
        let message = error.to_string();
        if message.contains("lease already held") {
            "package already claimed".to_string()
        } else {
            message
        }
    })
}

fn run_worker_command(root: PathBuf, command: &'static str) -> (i32, String, String) {
    let args = shell_words::split(command).expect("parse router command");
    match run_from_args_in_blocking_thread(args, &root) {
        Ok(output) => (0, output.stdout, output.stderr),
        Err(kanbus::error::KanbusError::CommandFailure { exit_code, message }) => {
            (exit_code, String::new(), format!("{message}\n"))
        }
        Err(kanbus::error::KanbusError::CommandFailureWithOutput {
            exit_code,
            stdout,
            stderr,
        }) => (exit_code, stdout, format!("{stderr}\n")),
        Err(error) => (1, String::new(), error.to_string()),
    }
}

fn run_worker_command_with_router_token(
    root: PathBuf,
    command: &'static str,
) -> (i32, String, String) {
    let previous_token = std::env::var_os("GITHUB_TOKEN");
    std::env::set_var("GITHUB_TOKEN", "router-fixture-token");
    let result = run_worker_command(root, command);
    match previous_token {
        Some(value) => std::env::set_var("GITHUB_TOKEN", value),
        None => std::env::remove_var("GITHUB_TOKEN"),
    }
    result
}

fn ensure_mutex_router_fixture(world: &mut KanbusWorld) {
    if world.mutex_api_fixture.is_none() {
        let fixture = crate::step_definitions::mutex_api_steps::MutexApiFixture::start()
            .expect("start mutex API fixture");
        if world.mutex_api_original_env.is_none() {
            world.mutex_api_original_env = Some((
                std::env::var_os("KANBUS_COORDINATION_MUTEX_API_ENDPOINT"),
                std::env::var_os("KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN"),
            ));
        }
        std::env::set_var("KANBUS_COORDINATION_MUTEX_API_ENDPOINT", &fixture.endpoint);
        std::env::set_var(
            "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN",
            "mutex-api-test-token",
        );
        configure_worker_pair(
            world,
            &["coordination", "mutex_api", "endpoint"],
            Yaml::String(fixture.endpoint.clone()),
        );
        configure_worker_pair(
            world,
            &["coordination", "mutex_api", "bearer_token"],
            Yaml::String("mutex-api-test-token".to_string()),
        );
        world.mutex_api_fixture = Some(fixture);
    }
}

fn parallel_worker_claims(world: &KanbusWorld, issue_id: &str) -> [Result<String, String>; 2] {
    let first_root = root(world).to_path_buf();
    let second_root = worker_b_root(world);
    let issue_a = issue_id.to_string();
    let issue_b = issue_id.to_string();
    let worker_a =
        thread::spawn(move || claim_result_for_worker(&first_root, &issue_a, "worker-a"));
    let worker_b =
        thread::spawn(move || claim_result_for_worker(&second_root, &issue_b, "worker-b"));
    [
        worker_a.join().expect("worker A claim thread"),
        worker_b.join().expect("worker B claim thread"),
    ]
}

fn record_worker_claim_results(world: &mut KanbusWorld, results: &[Result<String, String>; 2]) {
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_WORKER_CLAIMS".to_string(),
        serde_json::to_string(
            &results
                .iter()
                .map(|result| match result {
                    Ok(output) => json!({"ok":true,"output":output}),
                    Err(error) => json!({"ok":false,"error":error}),
                })
                .collect::<Vec<_>>(),
        )
        .expect("serialize worker claim results"),
    );
}

fn worker_claim_results(world: &KanbusWorld) -> Vec<Value> {
    serde_json::from_str(
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_WORKER_CLAIMS")
            .expect("router worker claim results"),
    )
    .expect("parse router worker claim results")
}

fn router_plan_for(root: &Path) -> Value {
    let (exit_code, stdout, stderr) =
        run_worker_command(root.to_path_buf(), "kanbus router plan --json");
    assert_eq!(
        exit_code,
        0,
        "router plan failed in {}: stdout={stdout:?}, stderr={stderr:?}",
        root.display()
    );
    serde_json::from_str(&stdout).expect("router plan JSON")
}

fn append_multi_router_event(root: &Path, event: &EventRecord) {
    let project_dir = load_project_directory(root).expect("router project directory");
    write_events_batch(&project_dir.join("events"), std::slice::from_ref(event))
        .expect("append router coordination fixture event");
}

fn run_parallel_router_passes(world: &KanbusWorld) -> [(i32, String, String); 2] {
    let previous_token = std::env::var_os("GITHUB_TOKEN");
    std::env::set_var("GITHUB_TOKEN", "router-fixture-token");
    let first_root = root(world).to_path_buf();
    let second_root = worker_b_root(world);
    let worker_a =
        thread::spawn(move || run_worker_command(first_root, "kanbus router run --once"));
    let worker_b =
        thread::spawn(move || run_worker_command(second_root, "kanbus router run --once"));
    let results = [
        worker_a.join().expect("worker A scheduling pass"),
        worker_b.join().expect("worker B scheduling pass"),
    ];
    match previous_token {
        Some(value) => std::env::set_var("GITHUB_TOKEN", value),
        None => std::env::remove_var("GITHUB_TOKEN"),
    }
    results
}

fn configure_multi_retryable_adapter(world: &KanbusWorld) {
    configure_multi_adapter_result(
        world,
        r#"{"schema_version":1,"outcome":"retryable_failure","summary":"fixture retryable failure","issue_updates":[],"checkpoint":null,"artifacts":[]}"#,
    );
}

fn configure_multi_active_adapter(world: &KanbusWorld) {
    // A retryable result leaves the package in its active state during the
    // retry window, allowing the shared WIP policy to be observed without
    // relying on an invalid adapter response.
    configure_multi_adapter_result(
        world,
        r#"{"schema_version":1,"outcome":"retryable_failure","summary":"fixture active worker","issue_updates":[],"checkpoint":null,"artifacts":[]}"#,
    );
}

fn configure_multi_adapter_result(world: &KanbusWorld, result: &str) {
    let script = root(world).join(".git/router-multi-adapter.sh");
    let request_log = root(world)
        .join(".git/router-multi-adapter-request.txt")
        .display()
        .to_string();
    fs::write(
        &script,
        format!(
            "#!/bin/sh\n{}printf '%s' \"$5\" > '{}'\nprintf '%s\\n' '{}'\n",
            crate::step_definitions::router_contract_steps::AGENT_WORK_LINE,
            request_log.replace('\'', "'\\''"),
            result.replace('\'', "'\\''")
        ),
    )
    .expect("write deterministic router fixture adapter");
    let mut permissions = fs::metadata(&script)
        .expect("adapter metadata")
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script, permissions).expect("make fixture adapter executable");
    for worker_root in [root(world).to_path_buf(), worker_b_root(world)] {
        mutate_yaml_at(
            &worker_root,
            &["router", "providers", "codex-default", "command"],
            Yaml::String(script.display().to_string()),
        );
        mutate_yaml_at(
            &worker_root,
            &["router", "providers", "codex-default", "args"],
            Yaml::Sequence(Vec::new()),
        );
    }
}

fn start_multi_test_forge(world: &KanbusWorld) -> (Arc<AtomicBool>, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind router fake GitHub API");
    listener
        .set_nonblocking(true)
        .expect("set fake GitHub listener nonblocking");
    let address = listener.local_addr().expect("fake GitHub address");
    let stop = Arc::new(AtomicBool::new(false));
    let stop_thread = Arc::clone(&stop);
    let join = thread::spawn(move || {
        while !stop_thread.load(Ordering::Relaxed) {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
                    let mut request = Vec::new();
                    let mut buffer = [0_u8; 4096];
                    loop {
                        match stream.read(&mut buffer) {
                            Ok(0) => break,
                            Ok(count) => {
                                request.extend_from_slice(&buffer[..count]);
                                let Some(header_end) =
                                    request.windows(4).position(|b| b == b"\r\n\r\n")
                                else {
                                    continue;
                                };
                                let headers = String::from_utf8_lossy(&request[..header_end]);
                                let body_length = headers
                                    .lines()
                                    .find_map(|line| {
                                        let (name, value) = line.split_once(':')?;
                                        name.eq_ignore_ascii_case("content-length")
                                            .then(|| value.trim().parse::<usize>().ok())
                                            .flatten()
                                    })
                                    .unwrap_or_default();
                                if request.len() >= header_end + 4 + body_length {
                                    break;
                                }
                            }
                            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                            Err(_) => break,
                        }
                    }
                    let raw = String::from_utf8_lossy(&request);
                    let method = raw.split_whitespace().next().unwrap_or_default();
                    let body = if method == "POST" {
                        r#"{"number":73,"head":{"sha":"router-fixture-head","ref":"codex/router/fixture/r1"}}"#
                    } else {
                        "[]"
                    };
                    let response = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                        body.len()
                    );
                    let _ = stream.write_all(response.as_bytes());
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(5));
                }
                Err(_) => break,
            }
        }
    });
    let url = format!("http://{address}");
    for worker_root in [root(world).to_path_buf(), worker_b_root(world)] {
        mutate_yaml_at(
            &worker_root,
            &["router", "forge", "api_url"],
            Yaml::String(url.clone()),
        );
    }
    (stop, join)
}

#[given("two router workers use isolated checkouts of the same Kanbus project")]
fn given_two_router_workers(world: &mut KanbusWorld) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    put_issue(
        world,
        &build_issue(
            "kbs-601",
            "open",
            vec!["agent-class:implementation".to_string()],
            None,
            None,
        ),
    );
    clone_router_worker(world);
}

#[given(
    regex = r#"^both workers plan package \"(?P<issue>[^\"]+)\" at the same logical revision$"#
)]
fn given_both_workers_plan_package(world: &mut KanbusWorld, issue: String) {
    let plan_a = router_plan_for(root(world));
    let plan_b = router_plan_for(&worker_b_root(world));
    for (worker, plan) in [("worker-a", plan_a), ("worker-b", plan_b)] {
        assert!(
            plan["eligible"]
                .as_array()
                .is_some_and(|items| items.iter().any(|item| item["issue_id"] == issue)),
            "{worker} did not plan {issue}: {plan}"
        );
    }
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_MULTI_ISSUE".to_string(), issue);
}

#[given(regex = r#"^router coordination mode is \"(?P<mode>soft|hard)\"$"#)]
fn given_router_coordination_mode(world: &mut KanbusWorld, mode: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    match mode.as_str() {
        "soft" => set_multi_coordination_providers(world, &["git"]),
        "hard" => {
            ensure_mutex_router_fixture(world);
            set_multi_coordination_providers(world, &["mutex_api", "mqtt", "git"]);
            let configuration = kanbus::config_loader::load_project_configuration(
                &get_configuration_path(root(world)).expect("configuration path"),
            )
            .expect("load hard coordination config");
            assert!(
                configuration
                    .coordination
                    .providers
                    .iter()
                    .any(|provider| provider == "mutex_api"),
                "hard router fixture must select Mutex API: {:?}",
                configuration.coordination.providers
            );
            assert!(
                kanbus::mutex_api::is_configured(&configuration.coordination.mutex_api),
                "hard router fixture must have a configured Mutex API: {:?}",
                configuration.coordination
            );
        }
        _ => unreachable!(),
    }
}

#[given("Git is the only coordination provider")]
fn given_git_only_coordination(world: &mut KanbusWorld) {
    set_multi_coordination_providers(world, &["git"]);
}

#[given("the Mutex API provider is available")]
fn given_mutex_api_available(world: &mut KanbusWorld) {
    ensure_mutex_router_fixture(world);
    set_multi_coordination_providers(world, &["mutex_api", "mqtt", "git"]);
}

#[when(
    regex = r#"^both router workers start package \"(?P<issue>[^\"]+)\" during a simulated partition$"#
)]
fn when_both_workers_claim_soft(world: &mut KanbusWorld, issue: String) {
    let results = parallel_worker_claims(world, &issue);
    record_worker_claim_results(world, &results);
}

#[when("both router workers request the package claim at the same time")]
fn when_both_workers_claim_hard(world: &mut KanbusWorld) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .cloned()
        .unwrap_or_else(|| "kbs-601".to_string());
    let results = parallel_worker_claims(world, &issue);
    record_worker_claim_results(world, &results);
    // Exercise the actual router scheduler after the concurrent hard claim.
    // The worker which lost the lease must not enter the adapter; if it did,
    // the fixture adapter returns a valid retryable result so the attempt is
    // durably observable rather than being hidden by a malformed /bin/true.
    configure_multi_retryable_adapter(world);
    git_commit_fixture(root(world), "router fixture adapter");
    git_commit_fixture(&worker_b_root(world), "router fixture adapter");
    let scheduler_results = run_parallel_router_passes(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_SCHEDULER_RESULTS".into(),
        serde_json::to_string(
            &scheduler_results
                .iter()
                .map(|(code, out, err)| json!({"exit":code,"stdout":out,"stderr":err}))
                .collect::<Vec<_>>(),
        )
        .unwrap(),
    );
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_MULTI_ISSUE".into(), issue);
}

#[then("both workers may report that their claim was accepted")]
fn then_both_claims_may_be_accepted(world: &mut KanbusWorld) {
    let results = worker_claim_results(world);
    assert_eq!(
        results.iter().filter(|result| result["ok"] == true).count(),
        2,
        "{results:?}"
    );
}

#[then("the project history should retain both claims")]
fn then_both_claims_in_history(world: &mut KanbusWorld) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    let resource = format!("router:issue:{issue}");
    let mut claims = read_events_at(root(world))
        .into_iter()
        .chain(read_events_at(&worker_b_root(world)))
        .filter(|event| {
            event.issue_id == resource && matches!(&event.event_type, EventType::CoordinationClaim)
        })
        .filter_map(|event| {
            event
                .payload
                .get("claim_id")
                .and_then(Value::as_str)
                .map(str::to_string)
        })
        .collect::<std::collections::BTreeSet<_>>();
    assert!(
        claims.len() >= 2,
        "expected both soft claims in durable project history: {claims:?}"
    );
    claims.clear();
}

#[then("publication should still accept only the current claim revision")]
fn then_stale_revision_publication_rejected(world: &mut KanbusWorld) {
    let resource = format!(
        "router:package:{}:checkpoint",
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
            .unwrap()
    );
    kanbus::coordination::run_coordination(
        root(world),
        kanbus::coordination::CoordinationOperation::PublishResult {
            resource: resource.clone(),
            revision: 2,
            artifact: "refs/kanbus/router/checkpoints/r2".to_string(),
        },
    )
    .expect("publish current result revision");
    let stale = kanbus::coordination::run_coordination(
        root(world),
        kanbus::coordination::CoordinationOperation::PublishResult {
            resource,
            revision: 1,
            artifact: "refs/kanbus/router/checkpoints/r1".to_string(),
        },
    );
    assert!(stale.is_err(), "stale result revision was accepted");
}

#[then("exactly one worker should acquire the package claim")]
fn then_one_worker_claimed(world: &mut KanbusWorld) {
    let results = worker_claim_results(world);
    assert_eq!(
        results.iter().filter(|result| result["ok"] == true).count(),
        1,
        "{results:?}"
    );
}

#[then(regex = r#"^the other worker should report \"(?P<message>[^\"]+)\"$"#)]
fn then_losing_worker_error(world: &mut KanbusWorld, message: String) {
    let results = worker_claim_results(world);
    assert!(
        results.iter().any(|result| {
            result["ok"] == false
                && result["error"]
                    .as_str()
                    .is_some_and(|error| error.to_lowercase().contains(&message.to_lowercase()))
        }),
        "no worker reported {message}: {results:?}"
    );
}

#[then("the losing worker should not start an adapter")]
fn then_loser_no_adapter(world: &mut KanbusWorld) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    assert!(!read_events_at(root(world))
        .iter()
        .chain(read_events_at(&worker_b_root(world)).iter())
        .any(|event| {
            event.issue_id == format!("router:{issue}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == "started"
        }));
    let runs: Vec<Value> = serde_json::from_str(
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_SCHEDULER_RESULTS")
            .expect("production scheduler run results"),
    )
    .expect("parse scheduler run results");
    assert!(
        runs.iter().all(|run| run["stdout"]
            .as_str()
            .unwrap_or_default()
            .contains("started=0")),
        "a scheduler started an adapter despite the live hard claim: {runs:?}"
    );
}

#[given(regex = r#"^the project WIP limit is (?P<limit>\d+)$"#)]
fn given_project_wip_limit(world: &mut KanbusWorld, limit: String) {
    let limit = limit.parse::<u64>().expect("project WIP limit");
    // The scenario background's kbs-601 package exists only to prove the two
    // workers share a plan. It is not one of this scenario's two contenders.
    // Make that seed terminal so the scheduler's deterministic oldest-first
    // choice is among the explicitly eligible kbs-603/kbs-604 fixtures.
    seed_multi_worker_package(world, "kbs-601", "closed");
    configure_worker_pair(
        world,
        &["router", "limits", "project_wip"],
        Yaml::Number(limit.into()),
    );
    configure_worker_pair(
        world,
        &["router", "limits", "review_wip"],
        Yaml::Number(limit.into()),
    );
    git_commit_fixture(root(world), "router project WIP limit");
    git_commit_fixture(&worker_b_root(world), "router project WIP limit");
}

#[given(regex = r#"^pending packages \"(?P<issues>[^\"]+)\" are eligible$"#)]
fn given_pending_multi_packages(world: &mut KanbusWorld, issues: String) {
    for issue in issues.split(',').map(str::trim) {
        seed_multi_worker_package(world, issue, "open");
    }
    git_commit_fixture(root(world), "router pending package fixtures");
    git_commit_fixture(&worker_b_root(world), "router pending package fixtures");
    for root_path in [root(world).to_path_buf(), worker_b_root(world)] {
        let plan = router_plan_for(&root_path);
        for issue in issues.split(',').map(str::trim) {
            assert!(
                plan["eligible"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|item| item["issue_id"] == issue),
                "{issue} not eligible: {plan}"
            );
        }
    }
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_MULTI_PACKAGES".to_string(), issues);
    configure_multi_active_adapter(world);
}

#[when("both router workers run one scheduling pass at the same time")]
fn when_workers_schedule_together(world: &mut KanbusWorld) {
    let results = run_parallel_router_passes(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_SCHEDULER_RESULTS".to_string(),
        serde_json::to_string(
            &results
                .iter()
                .map(|(code, out, err)| json!({"exit":code,"stdout":out,"stderr":err}))
                .collect::<Vec<_>>(),
        )
        .unwrap(),
    );
}

#[then("exactly one adapter should start")]
fn then_one_adapter_starts(world: &mut KanbusWorld) {
    let events = read_events_at(root(world))
        .into_iter()
        .chain(read_events_at(&worker_b_root(world)));
    let started = events
        .filter(|event| {
            matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == "started"
        })
        .map(|event| event.event_id)
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(
        started.len(),
        1,
        "router started attempts: {started:?}; results={}",
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_SCHEDULER_RESULTS")
            .unwrap_or(&String::new())
    );
}

#[then("exactly one package should enter the active status")]
fn then_one_package_active(world: &mut KanbusWorld) {
    let issues = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_PACKAGES")
        .unwrap();
    let roots = [root(world).to_path_buf(), worker_b_root(world)];
    let active = issues
        .split(',')
        .map(str::trim)
        .filter(|issue| {
            roots.iter().any(|root| {
                kanbus::router::effective_issue_router_status(root, issue)
                    .is_ok_and(|status| status == "in_progress")
            })
        })
        .count();
    let package_states = roots
        .iter()
        .map(|root| {
            let states = issues
                .split(',')
                .map(str::trim)
                .map(|issue| {
                    let state = kanbus::router::effective_issue_router_status(root, issue)
                        .ok()
                        .unwrap_or_else(|| "missing".to_string());
                    format!("{issue}={state}")
                })
                .collect::<Vec<_>>();
            format!("{}: {}", root.display(), states.join(", "))
        })
        .collect::<Vec<_>>();
    assert_eq!(
        active,
        1,
        "active package count: {}; results={}",
        package_states.join(" | "),
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_SCHEDULER_RESULTS")
            .unwrap_or(&String::new())
    );
}

#[then(regex = r#"^the other package should be deferred with reason \"(?P<reason>[^\"]+)\"$"#)]
fn then_other_package_deferred(world: &mut KanbusWorld, reason: String) {
    let plan = router_plan_for(root(world));
    assert!(
        plan["deferred"]
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item["reason"] == reason),
        "expected {reason}: {plan}"
    );
}

#[when(regex = r#"^both router workers attempt package \"(?P<issue>[^\"]+)\"$"#)]
fn when_both_router_run_issue(world: &mut KanbusWorld, issue: String) {
    let coordination = read_yaml(world)
        .1
        .get("coordination")
        .cloned()
        .expect("configured coordination settings");
    mutate_yaml_at(&worker_b_root(world), &["coordination"], coordination);
    git_commit_fixture(root(world), "router coordination settings");
    git_commit_fixture(&worker_b_root(world), "router coordination settings");
    let package = build_issue(
        &issue,
        "open",
        vec!["agent-class:implementation".to_string()],
        None,
        None,
    );
    put_issue(world, &package);
    let b_path = load_project_directory(&worker_b_root(world))
        .unwrap()
        .join("issues")
        .join(format!("{issue}.json"));
    if let Some(parent) = b_path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(&b_path, serde_json::to_vec_pretty(&package).unwrap()).unwrap();
    let runs = run_parallel_router_passes(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_UNAVAILABLE_RUNS".into(),
        serde_json::to_string(
            &runs
                .iter()
                .map(|(code, out, err)| json!({"exit":code,"stdout":out,"stderr":err}))
                .collect::<Vec<_>>(),
        )
        .unwrap(),
    );
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_MULTI_ISSUE".into(), issue);
}

#[then("neither worker should start an adapter")]
fn then_no_worker_adapter_starts(world: &mut KanbusWorld) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    assert!(!read_events_at(root(world))
        .iter()
        .chain(read_events_at(&worker_b_root(world)).iter())
        .any(|event| event.issue_id == format!("router:{issue}")
            && matches!(&event.event_type, EventType::RouterAttempt)
            && event.payload["action"] == "started"));
}

#[then(regex = r#"^both workers should report \"(?P<message>[^\"]+)\"$"#)]
fn then_both_router_failures(world: &mut KanbusWorld, message: String) {
    let runs: Vec<Value> = serde_json::from_str(
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_UNAVAILABLE_RUNS")
            .unwrap(),
    )
    .unwrap();
    assert!(
        runs.iter().all(|run| run["stderr"]
            .as_str()
            .unwrap_or_default()
            .contains(&message)),
        "{runs:?}"
    );
}

#[then(regex = r#"^both workers should leave package \"(?P<issue>[^\"]+)\" unchanged$"#)]
fn then_workers_leave_package_unchanged(world: &mut KanbusWorld, issue: String) {
    assert_eq!(load_issue(world, &issue).status, "open");
    let b_issue: IssueData = serde_json::from_slice(
        &fs::read(
            load_project_directory(&worker_b_root(world))
                .unwrap()
                .join("issues")
                .join(format!("{issue}.json")),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(b_issue.status, "open");
}

#[given(
    regex = r#"^router worker \"(?P<worker>[^\"]+)\" owns package \"(?P<issue>[^\"]+)\" claim \"(?P<claim>[^\"]+)\" until \"(?P<expires>[^\"]+)\"$"#
)]
fn given_expired_claim_owner(
    world: &mut KanbusWorld,
    worker: String,
    issue: String,
    claim: String,
    expires: String,
) {
    ensure_mutex_router_fixture(world);
    set_multi_coordination_providers(world, &["mutex_api", "mqtt", "git"]);
    seed_multi_worker_package(world, &issue, "in_progress");
    let fixture = world.mutex_api_fixture.as_ref().unwrap();
    let expiry = chrono::DateTime::parse_from_rfc3339(&expires)
        .expect("parse fixture claim expiry")
        .timestamp()
        .max(0) as u64;
    let now = expiry.saturating_sub(300);
    let resource = format!("router:issue:{issue}");
    fixture.leases.lock().unwrap().insert(resource.clone(), json!({"resource":resource,"owner":worker,"claim_id":claim,"revision":1,"claimed_at":now,"expires_at":expiry}));
    let event = EventRecord::new(
        resource.clone(),
        EventType::CoordinationClaim,
        &worker,
        json!({"owner":worker,"claim_id":claim,"revision":1,"lease_expires_at":expires,"contention_window_s":0,"ttl_s":300}),
        now_timestamp(),
    );
    append_multi_router_event(root(world), &event);
    append_multi_router_event(&worker_b_root(world), &event);
    let accepted_checkpoint = format!("refs/kanbus/router/checkpoints/{issue}");
    let checkpoint_attempt = EventRecord::new(
        format!("router:{issue}"),
        EventType::RouterAttempt,
        &worker,
        json!({"action":"checkpoint_accepted","attempt":1,"claim_id":claim,"revision":1,"checkpoint_ref":accepted_checkpoint,"checkpoint_revision":1}),
        now_timestamp(),
    );
    append_multi_router_event(root(world), &checkpoint_attempt);
    append_multi_router_event(&worker_b_root(world), &checkpoint_attempt);
    let checkpoint_result = EventRecord::new(
        format!("router:package:{issue}:checkpoint"),
        EventType::CoordinationResultPublished,
        &worker,
        json!({"resource":format!("router:package:{issue}:checkpoint"),"revision":1,"artifact":accepted_checkpoint}),
        now_timestamp(),
    );
    append_multi_router_event(root(world), &checkpoint_result);
    append_multi_router_event(&worker_b_root(world), &checkpoint_result);
    let started_attempt = EventRecord::new(
        format!("router:{issue}"),
        EventType::RouterAttempt,
        &worker,
        json!({"action":"started","attempt":1,"claim_id":claim,"revision":1,"provider_profile":"codex-default"}),
        now_timestamp(),
    );
    append_multi_router_event(root(world), &started_attempt);
    append_multi_router_event(&worker_b_root(world), &started_attempt);
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_MULTI_ISSUE".into(), issue);
}

#[when("simulated time advances past the claim expiry")]
fn when_simulated_expiry(world: &mut KanbusWorld) {
    let fixture = world.mutex_api_fixture.as_ref().expect("mutex fixture");
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    let resource = format!("router:issue:{issue}");
    if let Some(lease) = fixture.leases.lock().unwrap().get_mut(&resource) {
        lease["expires_at"] = json!(0);
    }
}

#[when(regex = r#"^router worker \"(?P<worker>[^\"]+)\" requests package \"(?P<issue>[^\"]+)\"$"#)]
fn when_router_worker_requests_package(world: &mut KanbusWorld, worker: String, issue: String) {
    assert_eq!(worker, "worker-b");
    configure_multi_retryable_adapter(world);
    let worker_root = worker_b_root(world);
    let result = run_worker_command_with_router_token(worker_root, "kanbus router run --once");
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_TAKEOVER_RUN".into(),
        json!({"exit":result.0,"stdout":result.1,"stderr":result.2}).to_string(),
    );
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_TAKEOVER".into(), issue);
}

#[then(regex = r#"^worker \"(?P<worker>[^\"]+)\" should acquire a new claim revision$"#)]
fn then_worker_new_claim_revision(world: &mut KanbusWorld, _worker: String) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_TAKEOVER")
        .unwrap();
    let started = read_events_at(&worker_b_root(world))
        .into_iter()
        .filter(|event| {
            event.issue_id == format!("router:{issue}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == "started"
        })
        .max_by_key(|event| event.payload["revision"].as_u64().unwrap_or_default())
        .expect("takeover started attempt");
    assert_eq!(started.payload["revision"], 2);
    assert_ne!(started.payload["claim_id"], "claim-a");
}

#[then("worker \"worker-b\" should start from the latest accepted checkpoint")]
fn then_worker_starts_from_checkpoint(world: &mut KanbusWorld) {
    let request = fs::read_to_string(root(world).join(".git/router-multi-adapter-request.txt"))
        .expect("takeover adapter request capture");
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    assert!(
        request.contains(&format!("refs/kanbus/router/checkpoints/{issue}")),
        "takeover prompt omitted the accepted checkpoint: {request}"
    );
    assert!(
        request.contains("\"revision\":1"),
        "takeover prompt omitted accepted checkpoint revision: {request}"
    );
}

#[then("worker \"worker-a\" should be unable to publish its obsolete result")]
fn then_old_worker_cannot_publish(world: &mut KanbusWorld) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    let result = kanbus::router::publish_issue_router_result_for_claim(
        &worker_b_root(world),
        issue,
        &[issue.to_string()],
        "claim-a",
        1,
        "completed",
        "obsolete completion",
        &[],
        Some(("refs/kanbus/router/checkpoints/obsolete", 1)),
        &[],
    );
    assert!(
        result.is_err(),
        "obsolete claim published a completed result"
    );
}

#[given(regex = r#"^both router workers are watching with interval (?P<interval>\d+) seconds$"#)]
fn given_both_workers_watch(world: &mut KanbusWorld, interval: String) {
    let providers = read_yaml(world)
        .1
        .get("coordination")
        .and_then(|coordination| coordination.get("providers"))
        .cloned()
        .expect("configured coordination providers");
    configure_worker_pair(world, &["coordination", "providers"], providers);
    configure_worker_pair(
        world,
        &["router", "watch_interval"],
        Yaml::String(format!("{interval}s")),
    );
    git_commit_fixture(root(world), "router watch interval");
    git_commit_fixture(&worker_b_root(world), "router watch interval");
}

#[when("the workers poll Git history")]
fn when_workers_poll_git_history(world: &mut KanbusWorld) {
    assert!(
        world.mosquitto_unavailable,
        "MQTT outage fixture was not set"
    );
    let realtime = read_yaml(world)
        .1
        .get("realtime")
        .cloned()
        .expect("configured realtime settings");
    mutate_yaml_at(&worker_b_root(world), &["realtime"], realtime);
    git_commit_fixture(root(world), "router MQTT broker fixture");
    git_commit_fixture(&worker_b_root(world), "router MQTT broker fixture");

    // Leave a second pending package for the peer to plan after worker A's
    // watch cycle publishes its retry event into the shared Git router state.
    seed_multi_worker_package(world, "kbs-602", "open");
    configure_multi_retryable_adapter(world);
    let (forge_stop, forge_thread) = start_multi_test_forge(world);
    git_commit_fixture(root(world), "router local forge fixture");
    git_commit_fixture(&worker_b_root(world), "router local forge fixture");
    let original_token = std::env::var_os("GITHUB_TOKEN");
    std::env::set_var("GITHUB_TOKEN", "router-fixture-token");

    let root_a = root(world).to_path_buf();
    let worker_a_result = Arc::new(Mutex::new(None));
    let worker_a_result_thread = Arc::clone(&worker_a_result);
    let worker_a = thread::spawn(move || {
        let result = run_worker_command(root_a, "kanbus router run --watch");
        *worker_a_result_thread.lock().unwrap() = Some(result.clone());
        result
    });
    wait_router_watch_started(root(world), &worker_a, &worker_a_result);
    wait_for_router_event(
        root(world),
        "kbs-601",
        "retryable_failure",
        &worker_a,
        &worker_a_result,
    );

    let plan_b_before_watch = router_plan_for(&worker_b_root(world));
    let plan_a = router_plan_for(root(world));
    let shared_events_a = read_shared_router_events(root(world));
    let shared_events_b = read_shared_router_events(&worker_b_root(world));
    let shared_retry_event = shared_events_b.iter().any(|event| {
        event.issue_id == "router:kbs-601"
            && matches!(&event.event_type, EventType::RouterAttempt)
            && event.payload["action"] == "retryable_failure"
    });
    assert!(
        shared_retry_event,
        "worker B did not fetch A's retry event from the shared Git ref: plan={plan_b_before_watch}; shared A={:?}; shared B={:?}",
        shared_events_a
            .iter()
            .map(|event| (&event.event_type, &event.issue_id, &event.payload))
            .collect::<Vec<_>>(),
        shared_events_b
            .iter()
            .map(|event| (&event.event_type, &event.issue_id, &event.payload))
            .collect::<Vec<_>>(),
    );
    assert!(!plan_b_before_watch["eligible"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["issue_id"] == "kbs-601"));
    assert!(plan_a["eligible"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["issue_id"] == "kbs-602"));
    assert!(plan_b_before_watch["eligible"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["issue_id"] == "kbs-602"));

    let root_b = worker_b_root(world);
    let worker_b_result = Arc::new(Mutex::new(None));
    let worker_b_result_thread = Arc::clone(&worker_b_result);
    let worker_b = thread::spawn(move || {
        let result = run_worker_command(root_b, "kanbus router run --watch");
        *worker_b_result_thread.lock().unwrap() = Some(result.clone());
        result
    });
    wait_router_watch_started(&worker_b_root(world), &worker_b, &worker_b_result);
    let watch_states = json!([
        run_worker_command(root(world).to_path_buf(), "kanbus router status").1,
        run_worker_command(worker_b_root(world), "kanbus router status").1
    ]);
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_WATCH_STATES".into(),
        watch_states.to_string(),
    );
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_POLLED_PLANS".into(),
        json!([plan_a, plan_b_before_watch]).to_string(),
    );

    let stop_a = run_worker_command(root(world).to_path_buf(), "kanbus router stop");
    let stop_b = run_worker_command(worker_b_root(world), "kanbus router stop");
    assert_eq!(stop_a.0, 0, "stop worker A: {stop_a:?}");
    assert_eq!(stop_b.0, 0, "stop worker B: {stop_b:?}");
    let result_a = worker_a.join().expect("worker A watch thread");
    let result_b = worker_b.join().expect("worker B watch thread");
    assert_eq!(result_a.0, 0, "worker A watch failed: {result_a:?}");
    assert_eq!(result_b.0, 0, "worker B watch failed: {result_b:?}");
    for worker_root in [root(world).to_path_buf(), worker_b_root(world)] {
        assert!(
            read_events_at(&worker_root).iter().any(|event| {
                event.issue_id == "router:scheduler"
                    && matches!(&event.event_type, EventType::CoordinationRelease)
            }),
            "watch shutdown did not durably release scheduler claim on {}",
            worker_root.display()
        );
    }
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .cloned()
        .unwrap_or_else(|| "kbs-601".into());
    let soft_claims = parallel_worker_claims(world, &issue);
    record_worker_claim_results(world, &soft_claims);
    forge_stop.store(true, Ordering::Relaxed);
    forge_thread.join().expect("fake GitHub API thread");
    match original_token {
        Some(value) => std::env::set_var("GITHUB_TOKEN", value),
        None => std::env::remove_var("GITHUB_TOKEN"),
    }
}

fn wait_router_watch_started(
    root: &Path,
    worker: &thread::JoinHandle<(i32, String, String)>,
    result: &Arc<Mutex<Option<(i32, String, String)>>>,
) {
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        let (exit, stdout, stderr) = run_worker_command(root.to_path_buf(), "kanbus router status");
        if exit == 0 && stdout.contains("Issue Router: running") {
            return;
        }
        assert!(
            !worker.is_finished(),
            "router watch exited before becoming running: result={:?}, status={stdout:?} {stderr:?}",
            result.lock().unwrap()
        );
        assert!(
            Instant::now() < deadline,
            "router watch did not start: {stdout:?} {stderr:?}"
        );
        thread::sleep(Duration::from_millis(100));
    }
}

fn wait_for_router_event(
    root: &Path,
    issue: &str,
    action: &str,
    worker: &thread::JoinHandle<(i32, String, String)>,
    result: &Arc<Mutex<Option<(i32, String, String)>>>,
) {
    let deadline = Instant::now() + Duration::from_secs(20);
    loop {
        if read_events_at(root).iter().any(|event| {
            event.issue_id == format!("router:{issue}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == action
        }) {
            return;
        }
        assert!(
            !worker.is_finished(),
            "router watch exited before {action} for {issue}: {:?}",
            result.lock().unwrap()
        );
        assert!(
            Instant::now() < deadline,
            "router watch did not publish {action} for {issue}"
        );
        thread::sleep(Duration::from_millis(100));
    }
}

#[then("both workers should observe durable router events from Git")]
fn then_workers_observe_git_events(world: &mut KanbusWorld) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_MULTI_ISSUE")
        .unwrap();
    let resource = format!("router:issue:{issue}");
    let count = read_shared_router_events(root(world))
        .into_iter()
        .chain(read_shared_router_events(&worker_b_root(world)))
        .filter(|event| {
            event.issue_id == resource && matches!(&event.event_type, EventType::CoordinationClaim)
        })
        .count();
    assert!(
        count >= 1,
        "no durable Git coordination event for {resource}"
    );
    let states: Value = serde_json::from_str(
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_WATCH_STATES")
            .expect("actual router watch states"),
    )
    .expect("parse watch states");
    assert!(
        states.as_array().unwrap().iter().all(|state| {
            state
                .as_str()
                .is_some_and(|text| text.contains("Issue Router: running"))
        }),
        "both production watch loops must have been running: {states}"
    );
}

#[then("both workers should continue planning eligible packages")]
fn then_both_workers_continue_planning(world: &mut KanbusWorld) {
    let plans: Vec<Value> = serde_json::from_str(
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_POLLED_PLANS")
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        plans.len(),
        2,
        "both worker plans should be captured: {plans:?}"
    );
    assert!(
        plans.iter().all(|plan| {
            plan["eligible"]
                .as_array()
                .is_some_and(|eligible| eligible.iter().any(|item| item["issue_id"] == "kbs-602"))
        }),
        "both workers should retain the independent pending package: {plans:?}"
    );
}

#[then("duplicate work may still occur because soft coordination is not hard exclusion")]
fn then_soft_duplicate_work(world: &mut KanbusWorld) {
    let results = worker_claim_results(world);
    assert_eq!(
        results.iter().filter(|result| result["ok"] == true).count(),
        2,
        "soft Git claims should admit both workers: {results:?}"
    );
}

#[given("a Kanbus project without a router configuration")]
fn given_project_without_router(world: &mut KanbusWorld) {
    ensure_default_project(world);
    let mut yaml = read_yaml(world).1;
    mapping(&mut yaml).remove(Yaml::String("router".to_string()));
    write_yaml(world, &yaml);
}

#[given(expr = "a Kanbus project with router configuration:")]
fn given_project_with_router_config(world: &mut KanbusWorld, step: &Step) {
    ensure_default_project(world);
    set_router_yaml(world, step.docstring().expect("router config docstring"));
}

#[given("a Kanbus project with valid Codex-first router configuration")]
fn given_valid_router_config(world: &mut KanbusWorld) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
}

#[given(expr = "a Kanbus project with router configuration {string}")]
fn given_router_configuration_string(world: &mut KanbusWorld, source: String) {
    ensure_default_project(world);
    set_router_yaml(world, &source);
}

#[given(expr = "a valid router configuration without a forge repository")]
fn given_router_without_repository(world: &mut KanbusWorld) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    let mut root_value = read_yaml(world).1;
    let router = mapping(&mut root_value)
        .get_mut(Yaml::String("router".to_string()))
        .and_then(Yaml::as_mapping_mut)
        .unwrap();
    let mut forge = serde_yaml::Mapping::new();
    forge.insert(
        Yaml::String("provider".to_string()),
        Yaml::String("github".to_string()),
    );
    router.insert(Yaml::String("forge".to_string()), Yaml::Mapping(forge));
    write_yaml(world, &root_value);
}

#[given(expr = "a valid router configuration with forge provider {string}")]
fn given_router_forge_provider(world: &mut KanbusWorld, provider: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    set_router_path(world, &["forge", "provider"], Yaml::String(provider));
}

#[given(
    regex = r#"^a valid router configuration with forge repository "(?P<repository>[^"]+)" and base branch "(?P<branch>[^"]+)"$"#
)]
fn given_router_forge_repository_branch(
    world: &mut KanbusWorld,
    repository: String,
    branch: String,
) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    set_router_path(world, &["forge", "repository"], Yaml::String(repository));
    set_router_path(world, &["forge", "base_branch"], Yaml::String(branch));
}

#[given(regex = r#"^a valid router configuration with forge repository "(?P<repository>[^"]+)"$"#)]
fn given_router_forge_repository(world: &mut KanbusWorld, repository: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    set_router_path(world, &["forge", "repository"], Yaml::String(repository));
}

#[given(
    regex = r#"^a valid router configuration with forge token environment variable "(?P<name>[^"]+)"$"#
)]
fn given_router_forge_token_name(world: &mut KanbusWorld, name: String) {
    ensure_default_project(world);
    if !read_yaml(world).1.get("router").is_some() {
        set_router_yaml(world, VALID_ROUTER);
    }
    set_router_path(world, &["forge", "token_env"], Yaml::String(name.clone()));
    world
        .environment_overrides
        .insert(name, "configured-token-fixture".to_string());
}

#[given(expr = "the forge API URL is {string}")]
fn given_forge_api_url(world: &mut KanbusWorld, api: String) {
    set_router_path(world, &["forge", "api_url"], Yaml::String(api));
}

#[given(expr = "the forge token environment variable is {string}")]
fn given_forge_token_name(world: &mut KanbusWorld, name: String) {
    if world.working_directory.is_none() {
        ensure_default_project(world);
        set_router_yaml(world, VALID_ROUTER);
    }
    set_router_path(world, &["forge", "token_env"], Yaml::String(name.clone()));
    world
        .environment_overrides
        .insert(name, "configured-token-fixture".to_string());
}

#[given(expr = "{string} is also set to {string}")]
fn given_other_token_env(world: &mut KanbusWorld, name: String, value: String) {
    world.environment_overrides.insert(name, value);
}

#[when("the router forge client is initialized")]
fn when_router_forge_client_initialized(world: &mut KanbusWorld) {
    let selected = kanbus::router::validate_router_forge_credentials(
        root(world),
        &world.environment_overrides,
    )
    .expect("initialize the configured forge client");
    world
        .environment_overrides
        .insert("KANBUS_TEST_SELECTED_FORGE_TOKEN_ENV".to_string(), selected);
}

#[given(regex = r#"^a valid router configuration with watch interval "(?P<interval>[^"]+)"$"#)]
fn given_router_watch_interval(world: &mut KanbusWorld, interval: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    set_router_path(world, &["watch_interval"], Yaml::String(interval));
}

#[given(
    regex = r#"^a valid router configuration with workflow role "(?P<role>[^"]+)" set to "(?P<status>.*)"$"#
)]
fn given_router_workflow_role(world: &mut KanbusWorld, role: String, status: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    let value: Yaml = if role == "terminal" {
        Yaml::Sequence(vec![Yaml::String(status)])
    } else {
        serde_yaml::from_str(&status).unwrap_or(Yaml::String(status))
    };
    set_router_path(world, &["workflow", &role], value);
}

#[given(
    regex = r#"^a valid router configuration with "(?P<field>[^"]+)" set to "(?P<value>[^"]+)"$"#
)]
fn given_router_limit(world: &mut KanbusWorld, field: String, value: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    let yaml_value = serde_yaml::from_str(&value).unwrap_or(Yaml::String(value));
    set_router_path(world, &["limits", &field], yaml_value);
}

#[given(expr = "a valid router configuration with project WIP {int} and review WIP {int}")]
fn given_router_wip_values(world: &mut KanbusWorld, project: i32, review: i32) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    set_router_path(
        world,
        &["limits", "project_wip"],
        Yaml::Number(project.into()),
    );
    set_router_path(
        world,
        &["limits", "review_wip"],
        Yaml::Number(review.into()),
    );
}

#[given(
    expr = "a valid router configuration with active status {string} and review status {string}"
)]
fn given_duplicate_router_roles(world: &mut KanbusWorld, active: String, review: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    set_router_path(world, &["workflow", "active"], Yaml::String(active));
    set_router_path(world, &["workflow", "review"], Yaml::String(review));
}

#[given(expr = "a valid router configuration with terminal statuses {string}")]
fn given_terminal_statuses(world: &mut KanbusWorld, statuses: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    let value = serde_yaml::from_str(&statuses).expect("terminal YAML list");
    set_router_path(world, &["workflow", "terminal"], value);
}

#[given(
    regex = r#"^a valid router configuration with provider profile "(?P<profile>[^"]+)" using adapter "(?P<adapter>[^"]+)"$"#
)]
fn given_router_provider_adapter(world: &mut KanbusWorld, profile: String, adapter: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    add_provider_profile(world, &profile, &adapter, None, Vec::new());
}

#[given(
    regex = r#"^a valid router configuration with class "(?P<class>[^"]+)" using provider profiles "(?P<profiles>[^"]*)"$"#
)]
fn given_router_class_profiles(world: &mut KanbusWorld, class: String, profiles: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    let profiles = profiles
        .split(',')
        .map(str::trim)
        .filter(|profile| !profile.is_empty())
        .map(|profile| Yaml::String(profile.to_string()))
        .collect::<Vec<_>>();
    set_router_path(
        world,
        &["classes", &class, "providers"],
        Yaml::Sequence(profiles),
    );
}

#[given(
    regex = r#"^provider profile "(?P<profile>[^"]+)" has command "(?P<command>[^"]+)" and arguments (?P<args>\[.*\])$"#
)]
fn given_provider_command_args(
    world: &mut KanbusWorld,
    profile: String,
    command: String,
    args: String,
) {
    let args: Vec<String> = serde_json::from_str(&args).expect("provider arguments JSON");
    add_provider_profile(world, &profile, "codex", Some(&command), args);
}

#[given(expr = "a Kanbus project with router configuration field {string}")]
fn given_unknown_router_field(world: &mut KanbusWorld, field: String) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    let mut root_value = read_yaml(world).1;
    let router = mapping(&mut root_value)
        .get_mut(Yaml::String("router".to_string()))
        .and_then(Yaml::as_mapping_mut)
        .unwrap();
    router.insert(Yaml::String(field), Yaml::Bool(true));
    write_yaml(world, &root_value);
}

#[when("the router configuration is loaded")]
fn when_router_configuration_loaded(world: &mut KanbusWorld) {
    let path = get_configuration_path(root(world)).expect("configuration path");
    match kanbus::config_loader::load_project_configuration(&path) {
        Ok(config) => {
            let errors = kanbus::router::validate_issue_router_configuration(&config);
            if errors.is_empty() {
                world.exit_code = Some(0);
                world.stdout = Some(String::new());
                world.stderr = Some(String::new());
                world.configuration = Some(config);
            } else {
                world.exit_code = Some(1);
                world.stdout = Some(String::new());
                world.stderr = Some(format!("error: {}\n", errors[0]));
            }
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(format!("error: {error}\n"));
        }
    }
}

#[then("the configuration should be valid")]
fn then_configuration_valid(world: &mut KanbusWorld) {
    assert_eq!(
        world.exit_code,
        Some(0),
        "{}",
        world.stderr.as_deref().unwrap_or("")
    );
    let path = get_configuration_path(root(world)).expect("configuration path");
    let loaded: ProjectConfiguration =
        kanbus::config_loader::load_project_configuration(&path).expect("valid configuration");
    assert!(loaded.router.is_some());
}

#[then(expr = "the default provider profile should be {string}")]
fn then_default_provider(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert!(
        router
            .classes
            .values()
            .any(|class| class.providers.first() == Some(&expected))
            || router.providers.contains_key(&expected)
    );
}

#[then(
    regex = r#"^provider profile "(?P<profile>[^"]+)" should use command "(?P<command>[^"]+)" and no arguments$"#
)]
fn then_provider_default_command(world: &mut KanbusWorld, profile: String, command: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    let provider = router.providers.get(&profile).expect("provider profile");
    assert_eq!(provider.resolved_command(), command);
    assert!(provider.args.is_empty());
}

#[then(expr = "the maximum retry attempts should be {int}")]
fn then_max_attempts(world: &mut KanbusWorld, expected: i32) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.retries.max_attempts, expected as u32);
}

#[then(expr = "the router watch interval should be {int} seconds")]
fn then_watch_interval(world: &mut KanbusWorld, expected: i32) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(
        kanbus::coordination::parse_duration_seconds(&router.watch_interval),
        Ok(expected as u64)
    );
}

#[then(expr = "the default forge provider should be {string}")]
fn then_default_forge_provider(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().provider, expected);
}

#[then(expr = "the default forge base branch should be {string}")]
fn then_default_forge_base(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().base_branch, expected);
}

#[then(expr = "the default forge API URL should be {string}")]
fn then_default_forge_api(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().api_url, expected);
}

#[then(expr = "the default forge token environment variable should be {string}")]
fn then_default_forge_token_env(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().token_env, expected);
}

#[then(expr = "the forge should use base branch {string}")]
fn then_forge_base(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().base_branch, expected);
}

#[then(expr = "the forge should use API URL {string}")]
fn then_forge_api(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().api_url, expected);
}

#[then(expr = "the forge should read credentials only from environment variable {string}")]
fn then_forge_credential_environment(world: &mut KanbusWorld, expected: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    assert_eq!(router.forge.unwrap().token_env, expected);
}

#[then(expr = "the client should read credentials only from {string}")]
fn then_forge_client_credential_environment(world: &mut KanbusWorld, expected: String) {
    assert_eq!(
        world
            .environment_overrides
            .get("KANBUS_TEST_SELECTED_FORGE_TOKEN_ENV")
            .map(String::as_str),
        Some(expected.as_str())
    );
}

#[then(
    regex = r#"^provider profile "(?P<profile>[^"]+)" should use command "(?P<command>[^"]+)" and arguments (?P<args>\[.*\])$"#
)]
fn then_provider_command_arguments(
    world: &mut KanbusWorld,
    profile: String,
    command: String,
    args: String,
) {
    let expected: Vec<String> = serde_json::from_str(&args).expect("provider argument JSON");
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    let provider = router
        .providers
        .get(&profile)
        .expect("configured provider profile");
    assert_eq!(provider.resolved_command(), command);
    assert_eq!(provider.args, expected);
}

#[given(
    regex = r#"^provider profile "(?P<profile>[^"]+)" has model "(?P<model>[^"]+)" and environment (?P<env>\{.*\})$"#
)]
fn given_provider_model_env(world: &mut KanbusWorld, profile: String, model: String, env: String) {
    let env: serde_yaml::Value = serde_yaml::from_str(&env).expect("environment mapping");
    set_router_path(
        world,
        &["providers", &profile, "model"],
        Yaml::String(model),
    );
    set_router_path(world, &["providers", &profile, "env"], env);
}

#[then(regex = r#"^provider profile "(?P<profile>[^"]+)" should use model "(?P<model>[^"]+)"$"#)]
fn then_provider_model(world: &mut KanbusWorld, profile: String, model: String) {
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).unwrap(),
    )
    .unwrap()
    .router
    .unwrap();
    let provider = router.providers.get(&profile).expect("provider profile");
    assert_eq!(provider.model.as_deref(), Some(model.as_str()));
}

#[given(expr = "the maximum retry attempts are {int}")]
fn given_max_attempts(world: &mut KanbusWorld, attempts: i32) {
    ensure_default_project(world);
    set_router_path(
        world,
        &["retries", "max_attempts"],
        Yaml::Number(attempts.into()),
    );
}

#[given(expr = "router retry max attempts is {int}")]
fn given_retry_attempts(world: &mut KanbusWorld, attempts: i32) {
    given_max_attempts(world, attempts);
}

#[given(expr = "active package {string} has accepted checkpoint {string} at revision {int}")]
fn given_active_package_with_checkpoint(
    world: &mut KanbusWorld,
    issue_id: String,
    checkpoint: String,
    revision: i32,
) {
    seed_active_router_attempt(world, &issue_id, 1, Some((&checkpoint, revision as u64)));
}

#[given(
    regex = r#"^the fake adapter returns outcome "(?P<outcome>[^"]+)" for attempt (?P<attempt>\d+)$"#
)]
fn given_fake_adapter_outcome_for_attempt(
    world: &mut KanbusWorld,
    outcome: String,
    _attempt: String,
) {
    crate::step_definitions::router_contract_steps::configure_fake_adapter(
        world,
        &json!({
            "schema_version":1,
            "outcome":outcome,
            "summary":"fixture failure",
            "issue_updates":[],
            "checkpoint":null,
            "artifacts":[]
        })
        .to_string(),
    );
}

#[given(expr = "package {string} has failed retryably {int} times")]
fn given_package_failed_retryably(world: &mut KanbusWorld, issue_id: String, attempts: i32) {
    seed_active_router_attempt(world, &issue_id, attempts as u32, None);
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_RETRY_ATTEMPT".to_string(),
        attempts.to_string(),
    );
}

#[when("I inspect its next retry time")]
fn when_inspect_next_retry_time(world: &mut KanbusWorld) {
    let attempt = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_RETRY_ATTEMPT")
        .expect("retry attempt fixture")
        .parse::<u32>()
        .expect("retry attempt number");
    world.stdout = Some(format!("{}s", kanbus::router::retry_delay_seconds(attempt)));
}

#[then(regex = r#"^the retry delay should be (?P<expected>\d+s)$"#)]
fn then_retry_delay(world: &mut KanbusWorld, expected: String) {
    assert_eq!(world.stdout.as_deref(), Some(expected.as_str()));
}

#[given(regex = r#"^package "(?P<issue>[^"]+)" is active at attempt (?P<attempt>\d+)$"#)]
fn given_package_active_at_attempt(world: &mut KanbusWorld, issue_id: String, attempt: String) {
    let attempt_number = attempt.parse::<u32>().expect("attempt number");
    let checkpoint = format!("refs/kanbus/router/checkpoints/{issue_id}");
    seed_active_router_attempt(
        world,
        &issue_id,
        attempt_number,
        Some((&checkpoint, u64::from(attempt_number))),
    );
}

#[given(regex = r#"^active package "(?P<issue>[^"]+)" is at attempt (?P<attempt>\d+)$"#)]
fn given_active_package_at_attempt(world: &mut KanbusWorld, issue_id: String, attempt: String) {
    given_package_active_at_attempt(world, issue_id, attempt);
}

#[given(regex = r#"^the fake adapter returns outcome "(?P<outcome>[^"]+)"$"#)]
fn given_fake_adapter_outcome(world: &mut KanbusWorld, outcome: String) {
    crate::step_definitions::router_contract_steps::configure_fake_adapter(
        world,
        &json!({
            "schema_version":1,
            "outcome":outcome,
            "summary":"fixture failure",
            "issue_updates":[],
            "checkpoint":null,
            "artifacts":[]
        })
        .to_string(),
    );
}

#[then(
    regex = r#"^package "(?P<issue>[^"]+)" should have attempt (?P<attempt>\d+) available after (?P<seconds>\d+) seconds$"#
)]
fn then_retry_available_after(
    world: &mut KanbusWorld,
    issue_id: String,
    attempt: String,
    seconds: String,
) {
    let next_attempt = attempt.parse::<u32>().expect("next attempt");
    let expected_seconds = seconds.parse::<i64>().expect("retry seconds");
    let event = router_event_for(world, &issue_id, |event| {
        event.payload.get("action").and_then(Value::as_str) == Some("retryable_failure")
            && event.payload.get("next_attempt").and_then(Value::as_u64)
                == Some(next_attempt as u64)
    });
    let retry_at =
        chrono::DateTime::parse_from_rfc3339(event.payload["retry_at"].as_str().expect("retry_at"))
            .expect("parse retry_at")
            .with_timezone(&Utc);
    let occurred_at = chrono::DateTime::parse_from_rfc3339(&event.occurred_at)
        .expect("parse event timestamp")
        .with_timezone(&Utc);
    let actual_seconds = (retry_at - occurred_at).num_seconds();
    assert!((actual_seconds - expected_seconds).abs() <= 1);
}

#[then(
    regex = r#"^the next attempt should start from checkpoint "(?P<reference>[^"]+)" at revision (?P<revision>\d+)$"#
)]
fn then_next_attempt_checkpoint(world: &mut KanbusWorld, reference: String, revision: String) {
    let expected_revision = revision.parse::<u64>().expect("checkpoint revision");
    let events = read_router_fixture_events(world);
    assert!(
        events.iter().any(|event| {
            matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload.get("action").and_then(Value::as_str) == Some("started")
                && event.payload.get("checkpoint_ref").and_then(Value::as_str)
                    == Some(reference.as_str())
                && event
                    .payload
                    .get("checkpoint_revision")
                    .and_then(Value::as_u64)
                    == Some(expected_revision)
        }),
        "checkpoint was not forwarded in started attempt: {events:?}"
    );
}

#[then(
    regex = r#"^package "(?P<issue>[^"]+)" should record the diagnostic "(?P<diagnostic>[^"]+)"$"#
)]
fn then_package_router_diagnostic(world: &mut KanbusWorld, issue_id: String, diagnostic: String) {
    assert!(read_router_fixture_events(world).iter().any(|event| {
        event.issue_id == format!("router:{issue_id}")
            && event.payload.get("diagnostic").and_then(Value::as_str) == Some(diagnostic.as_str())
    }));
}

#[then("the accepted checkpoint should remain available for a human or later router run")]
fn then_accepted_checkpoint_remains_available(world: &mut KanbusWorld) {
    let issue_id = "kbs-303";
    assert!(read_router_fixture_events(world).iter().any(|event| {
        event.issue_id == format!("router:{issue_id}")
            && event.payload.get("action").and_then(Value::as_str) == Some("checkpoint_accepted")
    }));
}

#[then(regex = r#"^package "(?P<issue>[^"]+)" should not receive a retry time$"#)]
fn then_no_retry_time(world: &mut KanbusWorld, issue_id: String) {
    assert!(!read_router_fixture_events(world).iter().any(|event| {
        event.issue_id == format!("router:{issue_id}") && event.payload.get("retry_at").is_some()
    }));
}

#[given(expr = "pending issue {string} has routing label {string}")]
fn given_pending_routed_issue(world: &mut KanbusWorld, identifier: String, label: String) {
    put_issue(
        world,
        &build_issue(
            &identifier,
            "open",
            if label.is_empty() {
                Vec::new()
            } else {
                label.split_whitespace().map(str::to_string).collect()
            },
            None,
            None,
        ),
    );
}

#[given(regex = r#"^pending issue "(?P<issue>[^"]+)" has routing labels "(?P<labels>[^"]*)"$"#)]
fn given_pending_issue_labels(world: &mut KanbusWorld, identifier: String, labels: String) {
    put_issue(
        world,
        &build_issue(
            &identifier,
            "open",
            labels.split_whitespace().map(str::to_string).collect(),
            None,
            None,
        ),
    );
}

#[given(expr = "issue {string} is pending with assignee {string} and no routing label")]
fn given_pending_assigned_issue(world: &mut KanbusWorld, identifier: String, assignee: String) {
    put_issue(
        world,
        &build_issue(&identifier, "open", Vec::new(), None, Some(assignee)),
    );
}

#[when(expr = "I run {string} in the same project")]
fn when_run_in_same_project(world: &mut KanbusWorld, command: String) {
    run_cli(world, &command);
}

#[then(expr = "running {string} in the same project should succeed")]
fn then_running_command_succeeds(world: &mut KanbusWorld, command: String) {
    run_cli(world, &command);
    assert_eq!(
        world.exit_code,
        Some(0),
        "{}",
        world.stderr.as_deref().unwrap_or("")
    );
}

#[then("the command should fail with exit code 2")]
fn then_exit_two(world: &mut KanbusWorld) {
    assert_eq!(world.exit_code, Some(2));
}

#[then(expr = "stdout should equal {string}")]
fn then_stdout_equals(world: &mut KanbusWorld, expected: String) {
    assert_eq!(
        world.stdout.as_deref().unwrap_or(""),
        expected.replace("\\n", "\n")
    );
}

#[then(expr = "stderr should equal {string}")]
fn then_stderr_equals(world: &mut KanbusWorld, expected: String) {
    assert_eq!(
        world.stderr.as_deref().unwrap_or(""),
        expected.replace("\\n", "\n").replace("\\\"", "\"")
    );
}

#[then(
    regex = r#"^stderr should equal "error: router\.workflow\.terminal references undefined status .*"$"#
)]
fn then_terminal_role_stderr(world: &mut KanbusWorld) {
    assert_eq!(
        world.stderr.as_deref().unwrap_or(""),
        "error: router.workflow.terminal references undefined status \"[\"unknown\"]\"\n"
    );
}

#[then(expr = "issue {string} should not appear in the eligible packages")]
fn then_issue_not_eligible(world: &mut KanbusWorld, identifier: String) {
    let output = world.stdout.as_deref().unwrap_or("");
    let plan: Value = serde_json::from_str(output).expect("router plan JSON");
    assert!(!plan["eligible"]
        .as_array()
        .unwrap()
        .iter()
        .any(|package| package["issue_id"] == identifier));
}

#[then(expr = "issue {string} should remain assigned to {string}")]
fn then_issue_assignee(world: &mut KanbusWorld, identifier: String, assignee: String) {
    assert_eq!(
        load_issue(world, &identifier).assignee.as_deref(),
        Some(assignee.as_str())
    );
}

#[given(
    regex = r#"^package "(?P<issue>[^"]+)" is in status "(?P<status>[^"]+)" with pull request (?P<number>\d+) at head "(?P<head>[^"]+)"$"#
)]
fn given_router_package_with_pull_request(
    world: &mut KanbusWorld,
    issue_id: String,
    status: String,
    number: String,
    head_sha: String,
) {
    seed_router_package_with_pull_request(
        world,
        &issue_id,
        &status,
        number.parse().expect("pull request number"),
        &head_sha,
    );
}

fn seed_router_package_with_pull_request(
    world: &mut KanbusWorld,
    issue_id: &str,
    status: &str,
    number: u64,
    head_sha: &str,
) {
    ensure_default_project(world);
    set_router_yaml(world, VALID_ROUTER);
    put_issue(
        world,
        &build_issue(
            &issue_id,
            status,
            vec!["agent-class:implementation".to_string()],
            None,
            None,
        ),
    );
    let event = EventRecord::new(
        format!("router:{issue_id}"),
        EventType::RouterForge,
        "cucumber-fixture",
        json!({
            "action": "opened",
            "repository": "anthusai/kanbus",
            "number": number,
            "head_sha": head_sha,
            "branch": format!("codex/{issue_id}"),
        }),
        now_timestamp(),
    );
    write_events_batch(&project_dir(world).join("events"), &[event])
        .expect("write pull request fixture event");
    if issue_id == "kbs-503" {
        put_issue(
            world,
            &build_issue(
                "kbs-504",
                "open",
                vec!["agent-class:implementation".to_string()],
                None,
                None,
            ),
        );
    }
}

#[given(expr = "GitHub is the configured forge for repository {string}")]
fn given_github_is_router_forge(world: &mut KanbusWorld, repository: String) {
    let configuration = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).expect("configuration path"),
    )
    .expect("router configuration");
    assert_eq!(
        configuration
            .router
            .and_then(|router| router.forge)
            .map(|forge| forge.repository),
        Some(repository)
    );
}

#[given(
    regex = r#"^package "(?P<issue>[^"]+)" has router pull request (?P<number>\d+) at head "(?P<head>[^"]+)"$"#
)]
fn given_package_has_router_pull_request(
    world: &mut KanbusWorld,
    issue_id: String,
    number: String,
    head_sha: String,
) {
    seed_router_package_with_pull_request(
        world,
        &issue_id,
        "review",
        number.parse().expect("pull request number"),
        &head_sha,
    );
}

#[given(
    regex = r#"^pull request (?P<number>\d+) has an approval recorded for head "(?P<head>[^"]+)"$"#
)]
fn given_pull_request_approval(world: &mut KanbusWorld, number: String, head_sha: String) {
    let number = number.parse::<u64>().expect("pull request number");
    let open = fs::read_dir(project_dir(world).join("events"))
        .expect("event directory")
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<EventRecord>(&bytes).ok())
        .find(|event| {
            event.payload.get("number").and_then(Value::as_u64) == Some(number)
                && event.payload.get("action").and_then(Value::as_str) == Some("opened")
        })
        .expect("opened pull request fixture");
    let event = EventRecord::new(
        open.issue_id,
        EventType::RouterForge,
        "cucumber-fixture",
        json!({
            "action": "approved",
            "repository": "anthusai/kanbus",
            "number": number,
            "head_sha": head_sha,
            "merged": false,
            "forge_event_id": format!("approval-fixture-{number}"),
        }),
        now_timestamp(),
    );
    write_events_batch(&project_dir(world).join("events"), &[event])
        .expect("write approval fixture");
}

#[when(
    regex = r#"^GitHub sends router check-run event "(?P<event>[^"]+)" for pull request (?P<number>\d+) and head "(?P<head>[^"]+)" with conclusion "(?P<conclusion>[^"]+)"$"#
)]
fn when_github_sends_router_check_run(
    world: &mut KanbusWorld,
    event_id: String,
    number: String,
    head_sha: String,
    conclusion: String,
) {
    match kanbus::router::record_router_check_run_event(
        root(world),
        &event_id,
        number.parse().expect("pull request number"),
        &head_sha,
        &conclusion,
    ) {
        Ok(_) => {
            world.exit_code = Some(0);
            world.stdout = Some(String::new());
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(format!("error: {error}\n"));
        }
    }
}

#[then(
    regex = r#"^package "(?P<issue>[^"]+)" should (?P<expected>remain in review|return to active) after the check-run event$"#
)]
fn then_router_check_run_lifecycle(world: &mut KanbusWorld, issue_id: String, expected: String) {
    assert_eq!(world.exit_code, Some(0));
    let router = kanbus::config_loader::load_project_configuration(
        &get_configuration_path(root(world)).expect("configuration path"),
    )
    .expect("load router configuration")
    .router
    .expect("router configuration");
    let expected_status = if expected == "remain in review" {
        router.workflow.review
    } else {
        router.workflow.active
    };
    assert_eq!(
        kanbus::router::effective_issue_router_status(root(world), &issue_id)
            .expect("reduce effective router status"),
        expected_status
    );
}

#[when("GitHub sends router event:")]
fn when_github_sends_router_event(world: &mut KanbusWorld, step: &Step) {
    let payload: Value = serde_json::from_str(step.docstring().expect("GitHub event JSON"))
        .expect("parse GitHub event JSON");
    match kanbus::router::record_router_pull_request_event(root(world), &payload) {
        Ok(_) => {
            world.exit_code = Some(0);
            world.stdout = Some(String::new());
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(format!("error: {error}\n"));
        }
    }
}

#[when(
    regex = r#"^the router receives the same approved GitHub event "(?P<event>[^"]+)" twice for pull request (?P<number>\d+) and head "(?P<head>[^"]+)"$"#
)]
fn when_router_receives_approved_event_twice(
    world: &mut KanbusWorld,
    event_id: String,
    number: String,
    head_sha: String,
) {
    let payload = json!({
        "schema_version": 1,
        "event_id": event_id,
        "kind": "pull_request",
        "action": "approved",
        "repository": "anthusai/kanbus",
        "number": number.parse::<u64>().expect("pull request number"),
        "head_sha": head_sha,
        "merged": false,
    });
    let first = kanbus::router::record_router_pull_request_event(root(world), &payload);
    let second = kanbus::router::record_router_pull_request_event(root(world), &payload);
    world.exit_code = Some(if first.is_ok() && second.is_ok() {
        0
    } else {
        1
    });
    world.stdout = Some(String::new());
    world.stderr = Some(String::new());
}

#[then(
    regex = r#"^package "(?P<issue>[^"]+)" should have a "(?P<author>[^"]+)" comment containing "(?P<text>[^"]+)"$"#
)]
fn then_router_package_comment(
    world: &mut KanbusWorld,
    issue: String,
    author: String,
    text: String,
) {
    let comments = load_issue(world, &issue).comments;
    assert!(
        comments.iter().any(|comment| comment.author == author
            && comment.text.as_deref().unwrap_or("").contains(&text)),
        "no {author} comment containing {text:?} on {issue}: {:?}",
        comments
            .iter()
            .map(|comment| (comment.author.clone(), comment.text.clone()))
            .collect::<Vec<_>>()
    );
}

#[then(expr = "package {string} should remain in status {string}")]
fn then_router_package_remains_status(world: &mut KanbusWorld, issue_id: String, expected: String) {
    assert_eq!(load_issue(world, &issue_id).status, expected);
}

#[then(expr = "package {string} should transition to status {string}")]
fn then_router_package_status(world: &mut KanbusWorld, issue_id: String, expected: String) {
    let actual_status = kanbus::router::effective_issue_router_status(root(world), &issue_id)
        .expect("reduce effective router status");
    let adapter_stdout =
        fs::read_to_string(root(world).join(".git/router-contract-adapter-stdout.txt"))
            .unwrap_or_default();
    let event_tail = read_router_fixture_events(world)
        .into_iter()
        .rev()
        .take(8)
        .map(|event| {
            (
                event.issue_id,
                format!("{:?}", event.event_type),
                event.payload,
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(
        actual_status,
        expected,
        "router output stdout={:?}, stderr={:?}, exit_code={:?}; fake adapter stdout={adapter_stdout:?}; recent events={event_tail:?}",
        world.stdout.as_deref().unwrap_or(""),
        world.stderr.as_deref().unwrap_or(""),
        world.exit_code
    );
}

#[then(expr = "package {string} should transition to terminal status {string}")]
fn then_router_package_terminal_status(
    world: &mut KanbusWorld,
    issue_id: String,
    expected: String,
) {
    assert_eq!(world.exit_code, Some(0));
    assert_eq!(
        kanbus::router::effective_issue_router_status(root(world), &issue_id)
            .expect("reduce effective router status"),
        expected
    );
}

#[then(expr = "GitHub event IDs {string} should be recorded once each")]
fn then_router_forge_event_ids_once(world: &mut KanbusWorld, event_ids: String) {
    let events = read_router_fixture_events(world);
    for event_id in event_ids.split(',').map(str::trim) {
        assert_eq!(
            events
                .iter()
                .filter(|event| {
                    event.payload.get("forge_event_id").and_then(Value::as_str) == Some(event_id)
                })
                .count(),
            1,
            "forge event {event_id} should have one immutable record"
        );
    }
}

#[then(expr = "package {string} should have approval recorded for head {string}")]
fn then_router_approval_recorded(world: &mut KanbusWorld, issue_id: String, head: String) {
    assert!(read_router_fixture_events(world).iter().any(|event| {
        event.issue_id == format!("router:{issue_id}")
            && event.payload.get("action").and_then(Value::as_str) == Some("approved")
            && event.payload.get("head_sha").and_then(Value::as_str) == Some(head.as_str())
    }));
}

#[then(expr = "pull request {int} should not have approval for head {string}")]
fn then_router_head_not_approved(world: &mut KanbusWorld, number: i32, head: String) {
    assert!(!read_router_fixture_events(world).iter().any(|event| {
        event.payload.get("number").and_then(Value::as_i64) == Some(i64::from(number))
            && event.payload.get("action").and_then(Value::as_str) == Some("approved")
            && event.payload.get("head_sha").and_then(Value::as_str) == Some(head.as_str())
    }));
}

#[then(expr = "the router should record diagnostic {string}")]
fn then_router_diagnostic(world: &mut KanbusWorld, expected: String) {
    assert!(read_router_fixture_events(world).iter().any(|event| {
        event.payload.get("diagnostic").and_then(Value::as_str) == Some(expected.as_str())
    }));
}

#[then(expr = "package {string} should be ordered before pending package {string}")]
fn then_router_recoverable_first(world: &mut KanbusWorld, issue_id: String, pending_id: String) {
    run_cli(world, "kanbus router plan --json");
    assert_eq!(world.exit_code, Some(0));
    let plan: Value = serde_json::from_str(world.stdout.as_deref().expect("router plan output"))
        .expect("router plan JSON");
    let eligible = plan["eligible"].as_array().expect("eligible list");
    let selected = eligible
        .iter()
        .position(|package| package["issue_id"] == issue_id)
        .expect("recoverable package is eligible");
    let pending = eligible
        .iter()
        .position(|package| package["issue_id"] == pending_id)
        .expect("pending package is eligible");
    assert!(selected < pending);
}

#[then(expr = "the next run should continue on pull request {int}")]
fn then_router_reuses_pull_request(world: &mut KanbusWorld, number: i32) {
    assert!(read_router_fixture_events(world).iter().any(|event| {
        event.payload.get("number").and_then(Value::as_i64) == Some(i64::from(number))
            && event.payload.get("action").and_then(Value::as_str) == Some("requested_changes")
    }));
}

#[then("one approval event should be recorded")]
fn then_router_one_approval_event(world: &mut KanbusWorld) {
    let approvals = read_router_fixture_events(world)
        .iter()
        .filter(|event| event.payload.get("action").and_then(Value::as_str) == Some("approved"))
        .count();
    assert_eq!(approvals, 1);
}

#[then("the event should fail with exit code 1")]
fn then_router_event_exit_one(world: &mut KanbusWorld) {
    assert_eq!(world.exit_code, Some(1));
}

#[then(regex = r#"^issue "(?P<issue>[^"]+)" should be deferred with reason "(?P<reason>[^"]+)"$"#)]
fn then_issue_deferred_reason(world: &mut KanbusWorld, identifier: String, reason: String) {
    let plan: Value = serde_json::from_str(world.stdout.as_deref().expect("plan output"))
        .expect("router plan JSON");
    assert!(plan["deferred"]
        .as_array()
        .unwrap()
        .iter()
        .any(|package| package["issue_id"] == identifier && package["reason"] == reason));
}

#[then(
    regex = r#"^issue "(?P<issue>[^"]+)" should be eligible with provider profile "(?P<profile>[^"]+)"$"#
)]
fn then_issue_eligible_profile(world: &mut KanbusWorld, identifier: String, profile: String) {
    let plan: Value = serde_json::from_str(world.stdout.as_deref().expect("plan output"))
        .expect("router plan JSON");
    assert!(plan["eligible"].as_array().unwrap().iter().any(|package| {
        package["issue_id"] == identifier
            && package
                .pointer("/route/provider_profile")
                .and_then(Value::as_str)
                == Some(&profile)
    }));
}
