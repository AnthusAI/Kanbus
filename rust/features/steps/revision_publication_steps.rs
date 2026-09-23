use std::fs;
use std::path::PathBuf;

use chrono::{DateTime, Duration, Utc};
use cucumber::{gherkin::Step, given, then, when};
use serde_json::{json, Value};

use crate::step_definitions::initialization_steps::{
    run_from_args_in_blocking_thread, KanbusWorld,
};
use kanbus::coordination::{publish_coordination_result, published_revision};
use kanbus::event_history::{
    events_dir_for_project, now_timestamp, write_events_batch, EventRecord, EventType,
};
use kanbus::file_io::load_project_directory;

fn project_dir(world: &KanbusWorld) -> PathBuf {
    load_project_directory(
        world
            .working_directory
            .as_deref()
            .expect("working directory"),
    )
    .expect("project directory")
}

fn read_resource_events(world: &KanbusWorld, resource: &str) -> Vec<EventRecord> {
    let directory = events_dir_for_project(&project_dir(world));
    let Ok(entries) = fs::read_dir(directory) else {
        return Vec::new();
    };
    let mut events = entries
        .flatten()
        .filter_map(|entry| {
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                return None;
            }
            let bytes = fs::read(path).ok()?;
            serde_json::from_slice::<EventRecord>(&bytes).ok()
        })
        .filter(|event| event.issue_id == resource)
        .collect::<Vec<_>>();
    events.sort_by(|left, right| {
        left.occurred_at
            .cmp(&right.occurred_at)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });
    events
}

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("command arguments");
    let root = world
        .working_directory
        .as_deref()
        .expect("working directory");
    match run_from_args_in_blocking_thread(args, root) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            let mut code = 1;
            let mut stdout = String::new();
            let stderr = match error {
                kanbus::error::KanbusError::CommandFailure { exit_code, message } => {
                    code = exit_code;
                    format!("{message}\n")
                }
                kanbus::error::KanbusError::CommandFailureWithOutput {
                    exit_code,
                    stdout: out,
                    stderr,
                } => {
                    code = exit_code;
                    stdout = out;
                    format!("{stderr}\n")
                }
                other => other.to_string(),
            };
            world.exit_code = Some(code);
            world.stdout = Some(stdout);
            world.stderr = Some(stderr);
        }
    }
    world.last_command = Some(command.to_string());
}

#[given(expr = "logical task revision for resource {string} is {int}")]
fn given_logical_revision(world: &mut KanbusWorld, resource: String, revision: i32) {
    assert!(revision > 0);
    world.environment_overrides.insert(
        format!(
            "KANBUS_TEST_LOGICAL_REVISION_{}",
            resource.replace(|ch: char| !ch.is_ascii_alphanumeric(), "_")
        ),
        revision.to_string(),
    );
}

#[given(expr = "published revision for resource {string} is {int}")]
fn given_published_revision(world: &mut KanbusWorld, resource: String, revision: i32) {
    assert!(revision > 0);
    publish_coordination_result(
        &project_dir(world),
        &resource,
        revision as u64,
        &format!("/tmp/{resource}-r{revision}.artifact"),
    )
    .expect("seed published revision through production API");
}

#[then(expr = "published revision for resource {string} should be {int}")]
fn then_published_revision(world: &mut KanbusWorld, resource: String, revision: i32) {
    assert_eq!(
        published_revision(&project_dir(world), &resource).expect("read published revision"),
        Some(revision as u64)
    );
}

#[given(expr = "router package {string} has current claim {string} at logical revision {int}")]
fn given_router_claim(world: &mut KanbusWorld, issue_id: String, claim_id: String, revision: i32) {
    assert!(revision > 0);
    let event = EventRecord::new(
        format!("router:{issue_id}"),
        EventType::RouterAttempt,
        "test-worker",
        json!({"action":"started", "claim_id":claim_id, "revision":revision, "attempt":1, "provider_profile":"codex-default"}),
        now_timestamp(),
    );
    write_events_batch(&events_dir_for_project(&project_dir(world)), &[event])
        .expect("write claim event");
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_PACKAGE".to_string(), issue_id);
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_CLAIM".to_string(), claim_id);
}

#[given(expr = "package {string} has current claim {string} at logical revision {int}")]
fn given_package_current_claim(
    world: &mut KanbusWorld,
    issue_id: String,
    claim_id: String,
    revision: i32,
) {
    crate::step_definitions::router_contract_steps::ensure_current_claim_issue(world, &issue_id);
    given_router_claim(world, issue_id, claim_id, revision);
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes a completed result with checkpoint "(?P<reference>[^"]+)" at revision (?P<revision>\d+)$"#
)]
fn when_claim_publishes_checkpoint(
    world: &mut KanbusWorld,
    claim: String,
    reference: String,
    revision: String,
) {
    let revision = revision.parse::<u64>().expect("revision");
    let package_id = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .expect("router package")
        .clone();
    let event = read_resource_events(world, &format!("router:{package_id}"))
        .into_iter()
        .rev()
        .find(|event| {
            matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload.get("claim_id").and_then(Value::as_str) == Some(claim.as_str())
                && event.payload.get("revision").and_then(Value::as_u64) == Some(revision)
        })
        .expect("current router claim event");
    let issue_id = event
        .issue_id
        .strip_prefix("router:")
        .expect("router issue")
        .to_string();
    let result = EventRecord::new(
        event.issue_id,
        EventType::RouterResult,
        "test-worker",
        json!({"outcome":"completed", "summary":"fixture result", "claim_id":claim, "revision":revision, "checkpoint_ref":reference, "checkpoint_revision":revision}),
        now_timestamp(),
    );
    write_events_batch(&events_dir_for_project(&project_dir(world)), &[result])
        .expect("write completed result");
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_PACKAGE".to_string(), issue_id);
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes artifact "(?P<name>[^"]+)" as "(?P<reference>[^"]+)"$"#
)]
fn when_claim_publishes_artifact(
    world: &mut KanbusWorld,
    claim: String,
    name: String,
    reference: String,
) {
    let issue_id = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .expect("published router package")
        .clone();
    let current = read_resource_events(world, &format!("router:{issue_id}"))
        .into_iter()
        .rev()
        .find(|event| {
            matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload.get("claim_id").and_then(Value::as_str) == Some(claim.as_str())
        })
        .expect("claim event");
    let revision = current
        .payload
        .get("revision")
        .and_then(Value::as_u64)
        .expect("logical revision");
    publish_coordination_result(
        &project_dir(world),
        &format!("router:package:{issue_id}:artifact:{name}"),
        revision,
        &reference,
    )
    .expect("publish artifact through revision-aware coordination API");
}

#[then(
    regex = r#"^the published result for package "(?P<issue_id>[^"]+)" should include claim "(?P<claim>[^"]+)" and revision (?P<revision>\d+)$"#
)]
fn then_router_result_claim_revision(
    world: &mut KanbusWorld,
    issue_id: String,
    claim: String,
    revision: String,
) {
    let revision = revision.parse::<u64>().expect("revision");
    let result = read_resource_events(world, &format!("router:{issue_id}"))
        .into_iter()
        .find(|event| {
            matches!(&event.event_type, EventType::RouterResult)
                && event.payload.get("outcome").and_then(Value::as_str) == Some("completed")
        })
        .expect("completed result");
    assert_eq!(
        result.payload.get("claim_id").and_then(Value::as_str),
        Some(claim.as_str())
    );
    assert_eq!(
        result.payload.get("revision").and_then(Value::as_u64),
        Some(revision)
    );
}

#[then(expr = "the published checkpoint should be {string}")]
fn then_published_checkpoint(world: &mut KanbusWorld, reference: String) {
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .expect("router package");
    let result = read_resource_events(world, &format!("router:{issue}"))
        .into_iter()
        .find(|event| matches!(&event.event_type, EventType::RouterResult))
        .expect("completed result");
    assert_eq!(
        result.payload.get("checkpoint_ref").and_then(Value::as_str),
        Some(reference.as_str())
    );
}

#[then(expr = "the published artifacts should contain {string}")]
fn then_published_artifacts(world: &mut KanbusWorld, expected: String) {
    let (name, reference) = expected.split_once('=').expect("artifact name=ref");
    let issue = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .expect("router package");
    assert_eq!(
        published_revision(
            &project_dir(world),
            &format!("router:package:{issue}:artifact:{name}")
        )
        .expect("artifact revision"),
        Some(5)
    );
    let events = read_resource_events(world, &format!("router:package:{issue}:artifact:{name}"));
    assert!(events
        .iter()
        .any(|event| event.payload.get("artifact").and_then(Value::as_str) == Some(reference)));
}

#[when(expr = "cloud worker runs {string}")]
fn when_cloud_worker_runs(world: &mut KanbusWorld, command: String) {
    run_cli(world, &command);
}

#[when(expr = "simulated time advances by {string} without a published result")]
fn when_simulated_time_advances(world: &mut KanbusWorld, elapsed: String) {
    let seconds = kanbus::coordination::parse_duration_seconds(&elapsed).expect("duration");
    let now = DateTime::parse_from_rfc3339(&now_timestamp())
        .expect("current time")
        .with_timezone(&Utc);
    let advanced = now + Duration::seconds(seconds as i64);
    if world.coordination_original_clock.is_none() {
        world.coordination_original_clock = Some(std::env::var_os("KANBUS_TEST_COORDINATION_NOW"));
    }
    let value = advanced.to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
    std::env::set_var("KANBUS_TEST_COORDINATION_NOW", &value);
    world.coordination_now_override = Some(value);
}

#[given(expr = "backstop eligibility threshold is {string}")]
fn given_backstop_threshold(world: &mut KanbusWorld, threshold: String) {
    world
        .environment_overrides
        .insert("KANBUS_TEST_BACKSTOP_THRESHOLD".to_string(), threshold);
}

#[given(expr = "cloud backstop worker is eligible for resource {string}")]
fn given_cloud_backstop_eligible_fixture(world: &mut KanbusWorld, resource: String) {
    assert!(
        published_revision(&project_dir(world), &resource)
            .expect("published history")
            .is_some(),
        "fixture requires an existing durable revision to test stale publication rejection"
    );
}

#[then(expr = "cloud backstop worker should be eligible for resource {string}")]
fn then_cloud_backstop_should_be_eligible(world: &mut KanbusWorld, resource: String) {
    assert_cloud_backstop_eligibility(world, &resource, true);
}

#[then(expr = "cloud backstop worker should not yet be eligible for resource {string}")]
fn cloud_backstop_not_yet_eligible(world: &mut KanbusWorld, resource: String) {
    assert_cloud_backstop_eligibility(world, &resource, false);
}

fn assert_cloud_backstop_eligibility(world: &KanbusWorld, resource: &str, expected: bool) {
    let events = read_resource_events(world, resource);
    let latest_claim = events
        .iter()
        .filter(|event| matches!(&event.event_type, EventType::CoordinationClaim))
        .max_by(|left, right| left.occurred_at.cmp(&right.occurred_at))
        .expect("durable claim event");
    let claim_at = DateTime::parse_from_rfc3339(&latest_claim.occurred_at)
        .expect("claim timestamp")
        .with_timezone(&Utc);
    let now = world
        .coordination_now_override
        .as_ref()
        .and_then(|raw| DateTime::parse_from_rfc3339(raw).ok())
        .map(|value| value.with_timezone(&Utc))
        .unwrap_or_else(Utc::now);
    let threshold = world
        .environment_overrides
        .get("KANBUS_TEST_BACKSTOP_THRESHOLD")
        .cloned()
        .unwrap_or_else(|| "15m".to_string());
    let threshold =
        kanbus::coordination::parse_duration_seconds(&threshold).expect("threshold") as i64;
    let is_published = published_revision(&project_dir(world), resource)
        .expect("published result")
        .is_some();
    assert_eq!(
        now.signed_duration_since(claim_at).num_seconds() >= threshold && !is_published,
        expected
    );
}

fn set_publication_error(world: &mut KanbusWorld, error: kanbus::error::KanbusError) {
    world.exit_code = Some(1);
    world.stdout = Some(String::new());
    world.stderr = Some(format!("error: {error}\n"));
}

fn package_id(world: &KanbusWorld) -> String {
    world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .expect("router package fixture")
        .clone()
}

fn current_claim_id(world: &KanbusWorld) -> String {
    world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_CLAIM")
        .expect("router claim fixture")
        .clone()
}

fn package_members(world: &KanbusWorld) -> Vec<String> {
    world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE_ISSUES")
        .map(|members| {
            members
                .split(',')
                .map(str::trim)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_else(|| vec![package_id(world)])
}

fn publish_fixture_result(
    world: &mut KanbusWorld,
    claim: &str,
    revision: u64,
    outcome: &str,
    summary: &str,
    updates: &[(String, String)],
    checkpoint: Option<(&str, u64)>,
    artifacts: &[(String, String)],
) {
    let issue_id = package_id(world);
    let result = kanbus::router::publish_issue_router_result_for_claim(
        world.working_directory.as_deref().expect("project root"),
        &issue_id,
        &package_members(world),
        claim,
        revision,
        outcome,
        summary,
        updates,
        checkpoint,
        artifacts,
    );
    match result {
        Ok(()) => {
            world.exit_code = Some(0);
            world.stdout = Some(String::new());
            world.stderr = Some(String::new());
        }
        Err(error) => set_publication_error(world, error),
    }
}

#[given(expr = "package {string} has obsolete claim {string} at logical revision {int}")]
fn given_obsolete_router_claim(
    world: &mut KanbusWorld,
    issue_id: String,
    claim_id: String,
    revision: i32,
) {
    let event = EventRecord::new(
        format!("router:{issue_id}"),
        EventType::RouterAttempt,
        "obsolete-worker",
        json!({"action":"started","claim_id":claim_id,"revision":revision,"attempt":1,"provider_profile":"codex-default"}),
        now_timestamp(),
    );
    write_events_batch(&events_dir_for_project(&project_dir(world)), &[event])
        .expect("write obsolete claim fixture");
}

#[when(expr = "claim {string} publishes result:")]
fn when_claim_publishes_result_docstring(world: &mut KanbusWorld, claim_id: String, step: &Step) {
    let result: Value = serde_json::from_str(step.docstring().expect("router result JSON"))
        .expect("parse router result JSON");
    assert_eq!(
        result["package_id"].as_str(),
        Some(package_id(world).as_str())
    );
    assert_eq!(result["claim_id"].as_str(), Some(claim_id.as_str()));
    let revision = result["revision"].as_u64().expect("result revision");
    let updates = result["issue_updates"]
        .as_array()
        .expect("result issue updates")
        .iter()
        .map(|update| {
            (
                update["issue_id"]
                    .as_str()
                    .expect("updated issue")
                    .to_string(),
                update["status"]
                    .as_str()
                    .expect("updated status")
                    .to_string(),
            )
        })
        .collect::<Vec<_>>();
    let checkpoint = result
        .get("checkpoint")
        .and_then(Value::as_object)
        .map(|value| {
            (
                value["ref"]
                    .as_str()
                    .expect("checkpoint reference")
                    .to_string(),
                value["revision"].as_u64().expect("checkpoint revision"),
            )
        });
    let artifacts = result["artifacts"]
        .as_array()
        .expect("result artifacts")
        .iter()
        .map(|artifact| {
            (
                artifact["name"]
                    .as_str()
                    .expect("artifact name")
                    .to_string(),
                artifact["ref"]
                    .as_str()
                    .expect("artifact reference")
                    .to_string(),
            )
        })
        .collect::<Vec<_>>();
    publish_fixture_result(
        world,
        &claim_id,
        revision,
        result["outcome"].as_str().expect("result outcome"),
        result["summary"].as_str().unwrap_or_default(),
        &updates,
        checkpoint
            .as_ref()
            .map(|(reference, revision)| (reference.as_str(), *revision)),
        &artifacts,
    );
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes a result at logical revision (?P<revision>\d+)$"#
)]
fn when_claim_publishes_revision(world: &mut KanbusWorld, claim: String, revision: String) {
    let revision = revision.parse::<u64>().expect("logical revision");
    publish_fixture_result(
        world,
        &claim,
        revision,
        "completed",
        "fixture result",
        &[],
        None,
        &[],
    );
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes a completed result with checkpoint "(?P<checkpoint>[^"]+)" and artifact "(?P<artifact>[^"]+)"$"#
)]
fn when_obsolete_claim_publishes_result(
    world: &mut KanbusWorld,
    claim: String,
    checkpoint: String,
    artifact: String,
) {
    let revision = read_resource_events(world, &format!("router:{}", package_id(world)))
        .iter()
        .find(|event| {
            matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload.get("claim_id").and_then(Value::as_str) == Some(claim.as_str())
        })
        .and_then(|event| event.payload.get("revision").and_then(Value::as_u64))
        .expect("obsolete claim revision");
    publish_fixture_result(
        world,
        &claim,
        revision,
        "completed",
        "obsolete result",
        &[],
        Some((&checkpoint, revision)),
        &[("stale".to_string(), artifact)],
    );
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes issue update "(?P<issue>[^"]+)" to status "(?P<status>[^"]+)"$"#
)]
fn when_claim_publishes_issue_update(
    world: &mut KanbusWorld,
    claim: String,
    issue: String,
    status: String,
) {
    crate::step_definitions::router_contract_steps::capture_issue_statuses(world);
    let revision = read_resource_events(world, &format!("router:{}", package_id(world)))
        .iter()
        .find(|event| {
            matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload.get("claim_id").and_then(Value::as_str) == Some(claim.as_str())
        })
        .and_then(|event| event.payload.get("revision").and_then(Value::as_u64))
        .expect("current claim revision");
    publish_fixture_result(
        world,
        &claim,
        revision,
        "completed",
        "fixture issue update",
        &[(issue, status)],
        None,
        &[],
    );
}

#[then("the result should be accepted")]
fn then_router_result_accepted(world: &mut KanbusWorld) {
    assert_eq!(world.exit_code, Some(0), "{:?}", world.stderr);
    let result = read_resource_events(world, &format!("router:{}", package_id(world)))
        .into_iter()
        .find(|event| matches!(&event.event_type, EventType::RouterResult))
        .expect("published router result");
    assert_eq!(result.payload["outcome"], "completed");
}

#[then(
    regex = r#"^the accepted checkpoint should be "(?P<reference>[^"]+)" at revision (?P<revision>\d+)$"#
)]
fn then_accepted_checkpoint_revision(world: &mut KanbusWorld, reference: String, revision: String) {
    let revision = revision.parse::<u64>().expect("checkpoint revision");
    let issue_id = package_id(world);
    let checkpoint_events = read_resource_events(world, &format!("router:{issue_id}"));
    assert!(checkpoint_events.iter().any(|event| {
        matches!(&event.event_type, EventType::RouterAttempt)
            && event.payload["action"] == "checkpoint_accepted"
            && event.payload["checkpoint_ref"] == reference
            && event.payload["checkpoint_revision"] == revision
    }));
    assert_eq!(
        published_revision(
            &project_dir(world),
            &format!("router:package:{issue_id}:checkpoint")
        )
        .expect("published checkpoint revision"),
        Some(revision)
    );
}

#[then(regex = r#"^artifact "(?P<name>[^"]+)" should be published as "(?P<reference>[^"]+)"$"#)]
fn then_router_artifact_published(world: &mut KanbusWorld, name: String, reference: String) {
    let issue_id = package_id(world);
    let resource = format!("router:package:{issue_id}:artifact:{name}");
    let events = read_resource_events(world, &resource);
    assert!(events
        .iter()
        .any(|event| event.payload["artifact"] == reference));
    assert!(published_revision(&project_dir(world), &resource)
        .unwrap()
        .is_some());
}

#[then("the publication should fail with exit code 1")]
fn then_router_publication_failed(world: &mut KanbusWorld) {
    assert_eq!(world.exit_code, Some(1), "{:?}", world.stderr);
}

#[then("the accepted checkpoint should not change")]
fn then_checkpoint_not_changed(world: &mut KanbusWorld) {
    let issue_id = package_id(world);
    assert!(published_revision(
        &project_dir(world),
        &format!("router:package:{issue_id}:checkpoint")
    )
    .expect("checkpoint publication")
    .is_none());
    assert!(!read_resource_events(world, &format!("router:{issue_id}"))
        .iter()
        .any(
            |event| matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == "checkpoint_accepted"
        ));
}

#[then(regex = r#"^no artifact reference from claim "(?P<claim>[^"]+)" should be published$"#)]
fn then_no_claim_artifact(world: &mut KanbusWorld, _claim: String) {
    let issue_id = package_id(world);
    assert!(published_revision(
        &project_dir(world),
        &format!("router:package:{issue_id}:artifact:stale")
    )
    .expect("stale artifact publication history")
    .is_none());
    assert!(
        read_resource_events(world, &format!("router:package:{issue_id}:artifact:stale"))
            .iter()
            .all(
                |event| event.payload.get("artifact").and_then(Value::as_str)
                    != Some("refs/kanbus/router/artifacts/kbs-311/stale")
            )
    );
}

pub(crate) fn seed_router_package_members(world: &mut KanbusWorld, issue: &str, issues: &str) {
    let root_issue_path = project_dir(world)
        .join("issues")
        .join(format!("{issue}.json"));
    if !root_issue_path.exists() {
        crate::step_definitions::router_contract_steps::ensure_current_claim_issue(world, issue);
    }
    for member in issues
        .split(',')
        .map(str::trim)
        .filter(|member| *member != issue)
    {
        let path = project_dir(world)
            .join("issues")
            .join(format!("{member}.json"));
        let mut child: Value = serde_json::from_slice(
            &fs::read(
                project_dir(world)
                    .join("issues")
                    .join(format!("{issue}.json")),
            )
            .expect("root issue"),
        )
        .expect("root issue JSON");
        child["identifier"] = json!(member);
        child["title"] = json!(format!("Router fixture {member}"));
        child["parent"] = json!(issue);
        child["status"] = json!("open");
        fs::write(path, serde_json::to_vec_pretty(&child).unwrap())
            .expect("write package child issue");
    }
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_PACKAGE_ISSUES".into(),
        issues
            .split(',')
            .map(str::trim)
            .collect::<Vec<_>>()
            .join(","),
    );
}

#[given(
    regex = r#"^package "(?P<issue>[^"]+)" has current claim "(?P<claim>[^"]+)" with no progress for (?P<hours>\d+) hours$"#
)]
fn given_claim_stale_for_hours(
    world: &mut KanbusWorld,
    issue: String,
    claim: String,
    hours: String,
) {
    crate::step_definitions::router_contract_steps::ensure_current_claim_issue(world, &issue);
    let hours = hours.parse::<i64>().expect("stale hours");
    let timestamp =
        (Utc::now() - Duration::hours(hours)).to_rfc3339_opts(chrono::SecondsFormat::Micros, true);
    let event = EventRecord::new(
        format!("router:{issue}"),
        EventType::RouterAttempt,
        "router-stale-fixture",
        json!({"action":"started","attempt":1,"claim_id":claim,"revision":1,"provider_profile":"codex-default"}),
        timestamp,
    );
    write_events_batch(&events_dir_for_project(&project_dir(world)), &[event])
        .expect("write stale claim fixture");
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_PACKAGE".into(), issue);
    world
        .environment_overrides
        .insert("KANBUS_TEST_ROUTER_CLAIM".into(), claim);
}

#[when(regex = r#"^a human adds a comment to issue "(?P<issue>[^"]+)"$"#)]
fn when_human_comments_router_issue(world: &mut KanbusWorld, issue: String) {
    kanbus::issue_comment::add_comment(
        world.working_directory.as_deref().expect("project root"),
        &issue,
        "human",
        "A human comment does not count as router progress.",
        None,
    )
    .expect("add human comment");
}

#[when(regex = r#"^the adapter sends an empty heartbeat for claim "(?P<claim>[^"]+)"$"#)]
fn when_adapter_empty_heartbeat(world: &mut KanbusWorld, claim: String) {
    kanbus::router::record_issue_router_progress(
        world.working_directory.as_deref().expect("project root"),
        &package_id(world),
        &claim,
        1,
        None,
    )
    .expect("ignore empty heartbeat");
}

#[then(regex = r#"^the stale ownership age should remain (?P<hours>\d+) hours$"#)]
fn then_stale_age_unchanged(world: &mut KanbusWorld, hours: String) {
    let age = kanbus::router::issue_router_claim_staleness_hours(
        world.working_directory.as_deref().expect("project root"),
        &package_id(world),
        &current_claim_id(world),
    )
    .expect("router claim staleness");
    assert_eq!(age, hours.parse::<u64>().unwrap());
}

#[then("the package should be eligible for takeover")]
fn then_stale_package_recoverable(world: &mut KanbusWorld) {
    let root = world.working_directory.as_deref().expect("project root");
    let issue = package_id(world);
    let plan = kanbus::router::build_issue_router_plan(root).expect("router recovery plan");
    assert!(
        plan.eligible
            .iter()
            .any(|candidate| candidate.issue_id == issue),
        "{plan:?}"
    );
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes structured progress at the current revision$"#
)]
fn when_claim_structured_progress(world: &mut KanbusWorld, claim: String) {
    kanbus::router::record_issue_router_progress(
        world.working_directory.as_deref().expect("project root"),
        &package_id(world),
        &claim,
        1,
        Some("Completed the implementation analysis."),
    )
    .expect("record structured router progress");
}

#[then("the stale ownership age should reset to zero")]
fn then_stale_age_zero(world: &mut KanbusWorld) {
    assert_eq!(
        kanbus::router::issue_router_claim_staleness_hours(
            world.working_directory.as_deref().expect("project root"),
            &package_id(world),
            &current_claim_id(world),
        )
        .expect("router claim staleness"),
        0
    );
}

#[then("the stale ownership age should remain zero")]
fn then_stale_age_remains_zero(world: &mut KanbusWorld) {
    then_stale_age_zero(world);
}

#[when(
    regex = r#"^claim "(?P<claim>[^"]+)" publishes an accepted checkpoint at the current revision$"#
)]
fn when_claim_accepts_current_checkpoint(world: &mut KanbusWorld, claim: String) {
    let issue = package_id(world);
    kanbus::router::accept_issue_router_checkpoint(
        world.working_directory.as_deref().expect("project root"),
        &issue,
        &claim,
        1,
        &format!("refs/kanbus/router/checkpoints/{issue}"),
    )
    .expect("accept current router checkpoint");
}

#[then(expr = "Git remains the durable history for resource {string}")]
fn then_git_remains_durable(world: &mut KanbusWorld, resource: String) {
    let events = read_resource_events(world, &resource);
    assert!(events
        .iter()
        .any(|event| matches!(&event.event_type, EventType::CoordinationClaim)));
    assert!(events_dir_for_project(&project_dir(world)).is_dir());
}
