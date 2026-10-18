//! Shared console snapshot feeds: one background refresher per store root,
//! fanned out to every subscriber instead of one polling loop per client.

use std::collections::hash_map::DefaultHasher;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::sync::broadcast;

use crate::console_backend::{ConsoleSnapshot, FileStore};

const SNAPSHOT_REFRESH_INTERVAL: Duration = Duration::from_secs(15);
const SNAPSHOT_BROADCAST_CAPACITY: usize = 16;

/// Serialized console snapshot together with the fingerprint used to detect change.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SnapshotPayload {
    pub json: String,
    pub fingerprint: u64,
}

/// Build the serialized snapshot for a store, or a serialized error object when it cannot be built.
pub fn snapshot_payload(store: &FileStore) -> (String, u64) {
    match store.build_snapshot() {
        Ok(snapshot) => {
            let fingerprint = snapshot_fingerprint(&snapshot);
            let payload = serde_json::to_string(&snapshot).unwrap_or_else(|error| {
                serde_json::json!({
                    "error": error.to_string(),
                    "updated_at": chrono::Utc::now().to_rfc3339(),
                })
                .to_string()
            });
            (payload, fingerprint)
        }
        Err(error) => {
            let payload = serde_json::json!({
                "error": error.to_string(),
                "updated_at": chrono::Utc::now().to_rfc3339(),
            })
            .to_string();
            (payload.clone(), hash_payload(&payload))
        }
    }
}

/// Fingerprint of the parts of a snapshot that clients care about (excludes the timestamp).
pub fn snapshot_fingerprint(snapshot: &ConsoleSnapshot) -> u64 {
    let payload = serde_json::to_vec(&(&snapshot.config, &snapshot.issues)).unwrap_or_default();
    hash_bytes(&payload)
}

pub fn hash_payload(payload: &str) -> u64 {
    hash_bytes(payload.as_bytes())
}

pub fn hash_bytes(bytes: &[u8]) -> u64 {
    let mut hasher = DefaultHasher::new();
    bytes.hash(&mut hasher);
    hasher.finish()
}

fn build_snapshot_payload_record(store: &FileStore) -> SnapshotPayload {
    let (json, fingerprint) = snapshot_payload(store);
    SnapshotPayload { json, fingerprint }
}

async fn build_snapshot_payload_record_off_runtime(store: FileStore) -> SnapshotPayload {
    tokio::task::spawn_blocking(move || build_snapshot_payload_record(&store))
        .await
        .unwrap_or_else(|error| {
            let json = serde_json::json!({
                "error": error.to_string(),
                "updated_at": chrono::Utc::now().to_rfc3339(),
            })
            .to_string();
            SnapshotPayload {
                fingerprint: hash_payload(&json),
                json,
            }
        })
}

/// A subscriber's view of a feed: the current payload, then every later change.
pub struct SnapshotFeedSubscription {
    pub current: Arc<SnapshotPayload>,
    pub changes: broadcast::Receiver<Arc<SnapshotPayload>>,
}

struct SnapshotFeed {
    latest: Mutex<Arc<SnapshotPayload>>,
    change_sender: broadcast::Sender<Arc<SnapshotPayload>>,
}

impl SnapshotFeed {
    fn subscribe(&self) -> SnapshotFeedSubscription {
        let latest = self.latest.lock().expect("snapshot feed latest lock");
        SnapshotFeedSubscription {
            current: Arc::clone(&latest),
            changes: self.change_sender.subscribe(),
        }
    }

    fn publish_if_changed(&self, payload: SnapshotPayload) {
        let mut latest = self.latest.lock().expect("snapshot feed latest lock");
        if latest.fingerprint == payload.fingerprint {
            return;
        }
        let payload = Arc::new(payload);
        *latest = Arc::clone(&payload);
        let _ = self.change_sender.send(payload);
    }
}

/// Registry of snapshot feeds keyed by store root. Cheap to clone.
#[derive(Clone, Default)]
pub struct SnapshotFeedRegistry {
    feeds: Arc<Mutex<HashMap<PathBuf, Arc<SnapshotFeed>>>>,
}

impl SnapshotFeedRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    /// Subscribe to the feed for a store, starting its single refresher when none is running.
    pub async fn subscribe(&self, store: FileStore) -> SnapshotFeedSubscription {
        if let Some(subscription) = self.subscribe_to_existing_feed(store.root()) {
            return subscription;
        }
        let initial = build_snapshot_payload_record_off_runtime(store.clone()).await;
        let mut feeds = self.feeds.lock().expect("snapshot feed registry lock");
        if let Some(feed) = feeds.get(store.root()) {
            return feed.subscribe();
        }
        let (change_sender, _) = broadcast::channel(SNAPSHOT_BROADCAST_CAPACITY);
        let feed = Arc::new(SnapshotFeed {
            latest: Mutex::new(Arc::new(initial)),
            change_sender,
        });
        let subscription = feed.subscribe();
        feeds.insert(store.root().to_path_buf(), Arc::clone(&feed));
        drop(feeds);
        tokio::spawn(refresh_feed_until_unwatched(self.clone(), store, feed));
        subscription
    }

    fn subscribe_to_existing_feed(
        &self,
        root: &std::path::Path,
    ) -> Option<SnapshotFeedSubscription> {
        let feeds = self.feeds.lock().expect("snapshot feed registry lock");
        feeds.get(root).map(|feed| feed.subscribe())
    }

    fn remove_feed_if_unwatched(&self, root: &std::path::Path, feed: &Arc<SnapshotFeed>) -> bool {
        let mut feeds = self.feeds.lock().expect("snapshot feed registry lock");
        if feed.change_sender.receiver_count() > 0 {
            return false;
        }
        feeds.remove(root);
        true
    }

    #[cfg(test)]
    fn active_feed_count(&self) -> usize {
        self.feeds
            .lock()
            .expect("snapshot feed registry lock")
            .len()
    }
}

async fn refresh_feed_until_unwatched(
    registry: SnapshotFeedRegistry,
    store: FileStore,
    feed: Arc<SnapshotFeed>,
) {
    loop {
        tokio::time::sleep(SNAPSHOT_REFRESH_INTERVAL).await;
        if registry.remove_feed_if_unwatched(store.root(), &feed) {
            return;
        }
        let refreshed = build_snapshot_payload_record_off_runtime(store.clone()).await;
        feed.publish_if_changed(refreshed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::fs;
    use std::path::Path;

    fn write_minimal_project(root: &Path) {
        fs::create_dir_all(root.join("project/issues")).expect("create issues directory");
        fs::write(
            root.join(".kanbus.yml"),
            "project_directory: project\nproject_key: tst\n",
        )
        .expect("write configuration");
    }

    #[test]
    fn hash_helpers_are_deterministic() {
        assert_eq!(hash_payload("payload"), hash_payload("payload"));
        assert_eq!(hash_payload("payload"), hash_bytes(b"payload"));
        assert_ne!(hash_payload("payload"), hash_payload("other"));
    }

    #[test]
    fn snapshot_payload_reports_an_error_object_when_the_project_is_missing() {
        let temp = tempfile::tempdir().expect("tempdir");
        let (json, fingerprint) = snapshot_payload(&FileStore::new(temp.path()));
        assert!(json.contains("\"error\""));
        assert_eq!(fingerprint, hash_payload(&json));
    }

    #[test]
    fn snapshot_payload_for_a_valid_project_uses_the_snapshot_fingerprint() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_minimal_project(temp.path());
        let store = FileStore::new(temp.path());
        let expected_fingerprint = snapshot_fingerprint(&store.build_snapshot().expect("snapshot"));
        let (json, fingerprint) = snapshot_payload(&store);
        assert_eq!(fingerprint, expected_fingerprint);
        assert!(json.contains("\"issues\""));
    }

    #[tokio::test]
    async fn concurrent_subscribers_share_one_feed_per_store_root() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_minimal_project(temp.path());
        let registry = SnapshotFeedRegistry::new();
        let first = registry.subscribe(FileStore::new(temp.path())).await;
        let second = registry.subscribe(FileStore::new(temp.path())).await;
        assert_eq!(registry.active_feed_count(), 1);
        assert!(Arc::ptr_eq(&first.current, &second.current));
    }

    #[test]
    fn publishing_an_unchanged_fingerprint_does_not_notify_subscribers() {
        let (change_sender, _) = broadcast::channel(SNAPSHOT_BROADCAST_CAPACITY);
        let feed = SnapshotFeed {
            latest: Mutex::new(Arc::new(SnapshotPayload {
                json: "{}".to_string(),
                fingerprint: 7,
            })),
            change_sender,
        };
        let mut subscription = feed.subscribe();
        feed.publish_if_changed(SnapshotPayload {
            json: "{\"same\":true}".to_string(),
            fingerprint: 7,
        });
        assert!(subscription.changes.try_recv().is_err());
        feed.publish_if_changed(SnapshotPayload {
            json: "{\"different\":true}".to_string(),
            fingerprint: 8,
        });
        let delivered = subscription.changes.try_recv().expect("changed payload");
        assert_eq!(delivered.fingerprint, 8);
    }
}
