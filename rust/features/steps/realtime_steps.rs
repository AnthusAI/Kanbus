use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::Duration;

use chrono::{DateTime, TimeZone, Utc};
use cucumber::{given, then, when};
use tempfile::TempDir;

use kanbus::gossip::{autostart_mosquitto, DedupeSet, GossipEnvelope};
use kanbus::models::{IssueData, OverlayConfig};
use kanbus::overlay::{
    gc_overlay, overlay_issue_path, resolve_issue_with_overlay, write_overlay_issue,
    OverlayIssueRecord,
};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn parse_ts(value: &str) -> DateTime<Utc> {
    DateTime::parse_from_rfc3339(value)
        .map(|dt| dt.with_timezone(&Utc))
        .unwrap_or_else(|_| Utc.with_ymd_and_hms(2026, 3, 6, 0, 0, 0).unwrap())
}

fn issue(identifier: &str, updated_at: DateTime<Utc>) -> IssueData {
    IssueData {
        identifier: identifier.to_string(),
        title: "Realtime test".to_string(),
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
        created_at: updated_at,
        updated_at,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

#[when("I read the realtime documentation")]
fn when_read_realtime_docs(world: &mut KanbusWorld) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let doc_path = root.join("docs").join("REALTIME.md");
    let contents = fs::read_to_string(&doc_path).expect("REALTIME doc");
    world.realtime_doc = Some(contents);
}

#[then("the realtime guide documents transport selection")]
fn then_doc_transport(world: &mut KanbusWorld) {
    assert!(world
        .realtime_doc
        .as_ref()
        .expect("doc")
        .contains("Transport selection"));
}

#[then("the realtime guide documents broker discovery")]
fn then_doc_broker(world: &mut KanbusWorld) {
    assert!(world
        .realtime_doc
        .as_ref()
        .expect("doc")
        .contains("Discovery precedence"));
}

#[then("the realtime guide documents autostart behavior")]
fn then_doc_autostart(world: &mut KanbusWorld) {
    assert!(world
        .realtime_doc
        .as_ref()
        .expect("doc")
        .contains("Autostart"));
}

#[then("the realtime guide documents envelope schema")]
fn then_doc_envelope(world: &mut KanbusWorld) {
    assert!(world
        .realtime_doc
        .as_ref()
        .expect("doc")
        .contains("Envelope schema"));
}

#[then("the realtime guide documents dedupe rules")]
fn then_doc_dedupe(world: &mut KanbusWorld) {
    assert!(world.realtime_doc.as_ref().expect("doc").contains("Dedupe"));
}

#[then("the realtime guide documents overlay merge rules")]
fn then_doc_overlay(world: &mut KanbusWorld) {
    assert!(world
        .realtime_doc
        .as_ref()
        .expect("doc")
        .contains("Overlay merge"));
}

#[then("the realtime guide documents overlay GC and hooks")]
fn then_doc_gc(world: &mut KanbusWorld) {
    let doc = world.realtime_doc.as_ref().expect("doc");
    assert!(doc.contains("overlay gc"));
    assert!(doc.contains("install-hooks"));
}

#[then("the realtime guide documents CLI commands")]
fn then_doc_cli(world: &mut KanbusWorld) {
    assert!(world
        .realtime_doc
        .as_ref()
        .expect("doc")
        .contains("gossip watch"));
}

#[then("the realtime guide documents config blocks")]
fn then_doc_config(world: &mut KanbusWorld) {
    let doc = world.realtime_doc.as_ref().expect("doc");
    assert!(doc.contains("realtime:"));
    assert!(doc.contains("overlay:"));
}

#[given(expr = "a gossip issue {string} updated at {string}")]
fn given_gossip_issue(world: &mut KanbusWorld, identifier: String, timestamp: String) {
    let updated_at = parse_ts(&timestamp);
    world.gossip_issue = Some(issue(&identifier, updated_at));
}

#[when("I build a gossip envelope for the issue")]
fn when_build_envelope(world: &mut KanbusWorld) {
    let issue = world.gossip_issue.clone().expect("issue");
    let envelope = GossipEnvelope {
        id: "n1".to_string(),
        ts: issue
            .updated_at
            .to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
        project: "kanbus".to_string(),
        event_type: "issue.mutated".to_string(),
        issue_id: Some(issue.identifier.clone()),
        event_id: Some("evt-1".to_string()),
        producer_id: "producer-1".to_string(),
        origin_cluster_id: None,
        issue: Some(issue),
    };
    world.gossip_envelope = Some(envelope);
}

#[then("the envelope includes the issue snapshot")]
fn then_envelope_includes_issue(world: &mut KanbusWorld) {
    let envelope = world.gossip_envelope.as_ref().expect("envelope");
    let payload = serde_json::to_value(envelope).expect("serialize");
    assert!(payload.get("issue").is_some());
}

#[then("the envelope includes standard metadata fields")]
fn then_envelope_standard_metadata(world: &mut KanbusWorld) {
    let envelope = world.gossip_envelope.as_ref().expect("envelope");
    let payload = serde_json::to_value(envelope).expect("serialize");
    for key in [
        "id",
        "ts",
        "project",
        "type",
        "issue_id",
        "event_id",
        "producer_id",
    ] {
        assert!(payload.get(key).is_some(), "missing metadata field: {key}");
    }
}

#[given(expr = "a gossip receiver with producer id {string}")]
fn given_receiver(world: &mut KanbusWorld, producer_id: String) {
    world.gossip_producer_id = Some(producer_id);
    world.gossip_dedupe = Some(DedupeSet::new(Duration::from_secs(3600)));
}

#[given(expr = "it has already seen notification id {string}")]
fn given_seen(world: &mut KanbusWorld, notification_id: String) {
    if let Some(dedupe) = world.gossip_dedupe.as_mut() {
        dedupe.seen(&notification_id);
    }
}

#[when(expr = "it receives notification id {string} from producer {string}")]
fn when_receive(world: &mut KanbusWorld, notification_id: String, producer_id: String) {
    let mut ignored = false;
    if let Some(dedupe) = world.gossip_dedupe.as_mut() {
        if dedupe.seen(&notification_id) {
            ignored = true;
        }
    }
    if world.gossip_producer_id.as_deref() == Some(producer_id.as_str()) {
        ignored = true;
    }
    world.last_notification_ignored = Some(ignored);
}

#[then("the notification is ignored")]
fn then_notification_ignored(world: &mut KanbusWorld) {
    assert_eq!(world.last_notification_ignored, Some(true));
}

#[given(expr = "a base issue {string} updated at {string}")]
fn given_base_issue(world: &mut KanbusWorld, identifier: String, timestamp: String) {
    let updated_at = parse_ts(&timestamp);
    let base_issue = issue(&identifier, updated_at);
    if world.overlay_project_dir.is_none() {
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path().join("project");
        fs::create_dir_all(project_dir.join("issues")).expect("issues dir");
        world.overlay_temp_dir = Some(temp_dir);
        world.overlay_project_dir = Some(project_dir);
    }
    let project_dir = world.overlay_project_dir.as_ref().expect("project dir");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    fs::write(
        &issue_path,
        serde_json::to_vec(&base_issue).expect("serialize"),
    )
    .expect("write issue");
    world.overlay_base_issue = Some(base_issue);
}

#[given(expr = "an overlay issue {string} updated at {string}")]
fn given_overlay_issue(world: &mut KanbusWorld, identifier: String, timestamp: String) {
    let updated_at = parse_ts(&timestamp);
    let overlay_issue = issue(&identifier, updated_at);
    world.overlay_issue_record = Some(OverlayIssueRecord {
        overlay_ts: updated_at.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
        overlay_event_id: None,
        overrides: None,
        issue: overlay_issue,
    });
}

#[when("I resolve the overlay issue")]
fn when_resolve_overlay(world: &mut KanbusWorld) {
    let project_dir = world.overlay_project_dir.as_ref().expect("project dir");
    let resolved = resolve_issue_with_overlay(
        project_dir,
        world.overlay_base_issue.clone(),
        world.overlay_issue_record.clone(),
        None,
        &OverlayConfig {
            enabled: true,
            ttl_s: 86_400,
        },
        None,
    )
    .expect("resolve");
    world.overlay_resolved = resolved;
}

#[then("the overlay version is returned")]
fn then_overlay_version(world: &mut KanbusWorld) {
    let resolved = world.overlay_resolved.as_ref().expect("resolved");
    let overlay = world.overlay_issue_record.as_ref().expect("overlay");
    assert_eq!(resolved.updated_at, overlay.issue.updated_at);
}

#[given(expr = "an overlay snapshot {string} updated at {string}")]
fn given_overlay_snapshot(world: &mut KanbusWorld, identifier: String, timestamp: String) {
    let updated_at = parse_ts(&timestamp);
    let overlay_issue = issue(&identifier, updated_at);
    let project_dir = world.overlay_project_dir.as_ref().expect("project dir");
    write_overlay_issue(
        project_dir,
        &overlay_issue,
        &updated_at.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
        None,
    )
    .expect("write overlay");
    world.overlay_snapshot_id = Some(identifier);
}

#[when("I run overlay GC")]
fn when_run_overlay_gc(world: &mut KanbusWorld) {
    let project_dir = world.overlay_project_dir.as_ref().expect("project dir");
    gc_overlay(
        project_dir,
        &OverlayConfig {
            enabled: true,
            ttl_s: 86_400,
        },
    )
    .expect("gc overlay");
}

#[then(expr = "the overlay snapshot {string} is removed")]
fn then_overlay_removed(world: &mut KanbusWorld, identifier: String) {
    let project_dir = world.overlay_project_dir.as_ref().expect("project dir");
    let path = overlay_issue_path(project_dir, &identifier);
    assert!(!path.exists());
}

#[given("a running UDS gossip broker")]
fn given_uds_broker(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let socket_path = temp_dir.path().join("bus.sock");
    world.uds_temp_dir = Some(temp_dir);
    world.uds_socket_path = Some(socket_path.clone());
    thread::spawn(move || {
        let _ = kanbus::gossip::run_gossip_broker(Path::new("."), Some(socket_path));
    });
    thread::sleep(Duration::from_millis(100));
}

#[when(expr = "a subscriber listens on {string}")]
fn when_subscribe_uds(world: &mut KanbusWorld, topic: String) {
    let socket_path = world.uds_socket_path.clone().expect("socket");
    let mut stream = UnixStream::connect(socket_path).expect("connect");
    stream.set_read_timeout(Some(Duration::from_secs(2))).ok();
    let payload = serde_json::json!({"op": "sub", "topic": topic});
    let line = serde_json::to_string(&payload).expect("serialize") + "\n";
    stream.write_all(line.as_bytes()).expect("write");
    world.uds_subscriber = Some(stream);
}

#[when(expr = "a publisher sends a gossip envelope on {string}")]
fn when_publish_uds(world: &mut KanbusWorld, topic: String) {
    let socket_path = world.uds_socket_path.clone().expect("socket");
    let issue = issue("kanbus-uds", Utc::now());
    let envelope = GossipEnvelope {
        id: "uds-msg-1".to_string(),
        ts: issue
            .updated_at
            .to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
        project: "kanbus".to_string(),
        event_type: "issue.mutated".to_string(),
        issue_id: Some(issue.identifier.clone()),
        event_id: Some("evt-uds".to_string()),
        producer_id: "producer-uds".to_string(),
        origin_cluster_id: None,
        issue: Some(issue),
    };
    world.uds_published_id = Some(envelope.id.clone());
    let payload = serde_json::json!({"op": "pub", "topic": topic, "msg": envelope});
    let line = serde_json::to_string(&payload).expect("serialize") + "\n";
    let mut stream = UnixStream::connect(socket_path).expect("connect");
    stream.write_all(line.as_bytes()).expect("write");
}

#[then("the subscriber receives the envelope")]
fn then_subscriber_receives(world: &mut KanbusWorld) {
    let mut stream = world.uds_subscriber.take().expect("subscriber");
    let mut reader = BufReader::new(&mut stream);
    let mut line = String::new();
    let _ = reader.read_line(&mut line).expect("read");
    let payload: serde_json::Value = serde_json::from_str(&line).expect("json");
    let msg = payload.get("msg").expect("msg");
    let received_id = msg.get("id").and_then(|value| value.as_str()).unwrap_or("");
    assert_eq!(Some(received_id.to_string()), world.uds_published_id);
}

#[given("mosquitto is available")]
fn given_mosquitto_available(_world: &mut KanbusWorld) {
    if !mosquitto_on_path() {
        eprintln!("mosquitto not installed; skipping scenario");
    }
}

#[when("I autostart a mosquitto broker")]
fn when_autostart_mosquitto(world: &mut KanbusWorld) {
    if !mosquitto_on_path() {
        return;
    }
    let startup = autostart_mosquitto("mqtt://127.0.0.1:1883").expect("autostart");
    world.mosquitto_startup = startup;
    thread::sleep(Duration::from_millis(100));
}

#[then("broker metadata is written")]
fn then_broker_metadata(world: &mut KanbusWorld) {
    if !mosquitto_on_path() {
        return;
    }
    let broker_path = std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(".kanbus")
        .join("run")
        .join("broker.json");
    assert!(broker_path.exists());
    if let Some(mut startup) = world.mosquitto_startup.take() {
        let _ = startup.process.kill();
    }
}

fn mosquitto_on_path() -> bool {
    if let Ok(path) = std::env::var("PATH") {
        for entry in std::env::split_paths(&path) {
            if entry.join("mosquitto").exists() {
                return true;
            }
        }
    }
    false
}
