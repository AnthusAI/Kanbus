//! Board archive, restore and purge, and the sweeper that purges expired archives.
//!
//! All lifecycle state lives in the reserved scope `_kanbus/archives` as ordinary
//! canonical objects, so it is listable, conditionally writable and deletable on every
//! backend, and API callers can never address it because tenant names beginning with an
//! underscore are rejected. The layout is:
//!
//! - `markers/<tenant>/<project>.json`: the archive marker, one per archived board.
//! - `index/<purge_after>/<tenant>/<project>.json`: the archive index. The timestamp
//!   segment sorts lexically, so the sweeper lists only the prefix that has expired.
//! - `receipts/<tenant>/<project>/<sha256 of operation id>.json`: the recorded outcome of
//!   each lifecycle operation, used to answer replays.

use super::*;
use chrono::{DateTime, Duration, SecondsFormat};

/// Environment variable holding the number of days an archived board is retained.
pub const ARCHIVE_RETENTION_VARIABLE: &str = "KANBUS_ARCHIVE_RETENTION_DAYS";

/// Most archived boards one sweeper run examines.
pub const SWEEP_BATCH_LIMIT: usize = 50;

const ARCHIVE_TENANT: &str = "_kanbus";
const ARCHIVE_PROJECT: &str = "archives";
const MARKERS_PREFIX: &str = "markers/";
const INDEX_PREFIX: &str = "index/";
const LIFECYCLE_OBJECT_LIMIT: usize = 64 * 1024;
const INDEX_PAGE_SIZE: usize = 100;

/// Retention policy and the object store holding archive state.
///
/// With a store that serves many boards, `archive_objects` is the same store as the board
/// objects. A transport that binds its store to one board supplies a separate store.
#[derive(Clone)]
pub struct BoardLifecycle {
    retention_days: u32,
    archive_objects: Arc<dyn ObjectStore>,
}

impl BoardLifecycle {
    /// Create a lifecycle policy; the retention must be a positive number of days.
    pub fn new(retention_days: u32, archive_objects: Arc<dyn ObjectStore>) -> Result<Self, String> {
        if retention_days == 0 {
            return Err(format!(
                "{ARCHIVE_RETENTION_VARIABLE} must be a positive integer."
            ));
        }
        Ok(Self {
            retention_days,
            archive_objects,
        })
    }

    /// Parse the retention setting, failing with a message naming the variable.
    pub fn parse_retention_days(value: Option<&str>) -> Result<u32, String> {
        let text = value.ok_or_else(|| format!("{ARCHIVE_RETENTION_VARIABLE} is required."))?;
        text.trim()
            .parse::<u32>()
            .ok()
            .filter(|days| *days > 0)
            .ok_or_else(|| format!("{ARCHIVE_RETENTION_VARIABLE} must be a positive integer."))
    }

    /// Read the retention setting from the process environment.
    pub fn retention_days_from_environment() -> Result<u32, String> {
        Self::parse_retention_days(std::env::var(ARCHIVE_RETENTION_VARIABLE).ok().as_deref())
    }
}

/// Counts reported by one sweeper run; never contains board or issue content.
#[derive(Debug, Default, PartialEq, Eq, Clone)]
pub struct SweepReport {
    /// Boards purged because their retention expired.
    pub purged: usize,
    /// Index entries removed because their board was restored or re-archived.
    pub stale_removed: usize,
    /// Boards whose purge failed and will be retried by a later run.
    pub failed: usize,
}

#[derive(Serialize, Deserialize, Clone)]
struct ArchiveMarker {
    archived_at: String,
    purge_after: String,
    archived_by: String,
    archive_operation_id: String,
    archive_request_hash: String,
    purge_operation_id: Option<String>,
    purge_request_hash: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct IndexEntry {
    tenant: String,
    project: String,
}

#[derive(Serialize, Deserialize)]
struct LifecycleReceipt {
    request_hash: String,
    status: u16,
    body: Value,
    closes_archive: Option<String>,
}

fn board_not_found() -> ApiError {
    ApiError::new(404, "not_found", "Board not found.")
}

fn board_archived() -> ApiError {
    ApiError::new(409, "board_archived", "The board is archived.")
}

fn board_not_archived() -> ApiError {
    ApiError::new(409, "board_not_archived", "The board is not archived.")
}

fn purge_in_progress() -> ApiError {
    ApiError::new(
        409,
        "purge_in_progress",
        "A purge of this board has already started under another operation.",
    )
}

fn archive_scope() -> Scope {
    Scope::new(ARCHIVE_TENANT, ARCHIVE_PROJECT).expect("the archive scope is statically valid")
}

fn marker_path(scope: &Scope) -> String {
    format!(
        "{MARKERS_PREFIX}{}/{}.json",
        scope.tenant(),
        scope.project()
    )
}

fn timestamp_segment(instant: &DateTime<Utc>) -> String {
    instant.format("%Y%m%dT%H%M%SZ").to_string()
}

fn index_path(purge_after: &str, scope: &Scope) -> Result<String, ApiError> {
    let instant = DateTime::parse_from_rfc3339(purge_after)
        .map_err(|_| ApiError::new(503, "invalid_archive_state", "Archive state is invalid."))?
        .with_timezone(&Utc);
    Ok(format!(
        "{INDEX_PREFIX}{}/{}/{}.json",
        timestamp_segment(&instant),
        scope.tenant(),
        scope.project()
    ))
}

fn receipt_path(scope: &Scope, operation: &str) -> String {
    format!(
        "receipts/{}/{}/{:x}.json",
        scope.tenant(),
        scope.project(),
        Sha256::digest(operation.as_bytes())
    )
}

fn derived_purge_identity(scope: &Scope, marker: &ArchiveMarker) -> (String, String) {
    let seed = format!("{}|{}", scope.namespace(), marker.archived_at);
    let digest = format!("{:x}", Sha256::digest(seed.as_bytes()));
    (
        format!("sweep-{digest}"),
        format!("{:x}", Sha256::digest(format!("sweep|{digest}").as_bytes())),
    )
}

fn invalid_archive_state(error: impl std::fmt::Display) -> ApiError {
    eprintln!("Kanbus archive state could not be decoded: {error}");
    ApiError::new(503, "invalid_archive_state", "Archive state is invalid.")
}

impl Api {
    pub(crate) fn reject_reserved_tenant(tenant: &str) -> Result<(), ApiError> {
        if tenant.starts_with('_') {
            return Err(invalid(
                "Tenant names beginning with an underscore are reserved.",
            ));
        }
        Ok(())
    }

    async fn read_lifecycle_object<T: for<'de> Deserialize<'de>>(
        &self,
        path: &str,
    ) -> Result<Option<(T, String)>, ApiError> {
        let stored = self
            .lifecycle
            .archive_objects
            .get_bounded(&archive_scope(), path, LIFECYCLE_OBJECT_LIMIT)
            .await
            .map_err(storage_error)?;
        stored
            .map(|object| {
                serde_json::from_slice(&object.bytes)
                    .map(|value| (value, object.revision))
                    .map_err(invalid_archive_state)
            })
            .transpose()
    }

    async fn write_lifecycle_object(
        &self,
        path: &str,
        value: &impl Serialize,
        condition: WriteCondition,
    ) -> Result<(), StoreError> {
        self.lifecycle
            .archive_objects
            .put(
                &archive_scope(),
                path,
                &json_bytes(value),
                "application/json",
                condition,
                None,
            )
            .await
            .map(|_| ())
    }

    async fn delete_lifecycle_object(&self, path: &str) -> Result<(), ApiError> {
        let stored = self
            .lifecycle
            .archive_objects
            .get_bounded(&archive_scope(), path, LIFECYCLE_OBJECT_LIMIT)
            .await
            .map_err(storage_error)?;
        if let Some(object) = stored {
            match self
                .lifecycle
                .archive_objects
                .delete(&archive_scope(), path, &object.revision)
                .await
            {
                Ok(()) => {}
                Err(error) => return Err(storage_error(error)),
            }
        }
        Ok(())
    }

    async fn read_marker(
        &self,
        scope: &Scope,
    ) -> Result<Option<(ArchiveMarker, String)>, ApiError> {
        self.read_lifecycle_object(&marker_path(scope)).await
    }

    pub(crate) async fn reject_unless_board_is_open(
        &self,
        scope: &Scope,
        request: &ApiRequest,
    ) -> Result<(), ApiError> {
        if self.read_marker(scope).await?.is_none() {
            return Ok(());
        }
        if !request.principal.provision {
            return Err(board_not_found());
        }
        if request.method != "GET" {
            return Err(board_archived());
        }
        Ok(())
    }

    pub(crate) async fn reject_archived_for_listing(
        &self,
        scope: &Scope,
        request: &ApiRequest,
    ) -> Result<(), ApiError> {
        if !request.principal.provision && self.read_marker(scope).await?.is_some() {
            return Err(board_not_found());
        }
        Ok(())
    }

    pub(crate) async fn lifecycle_route(
        &self,
        scope: &Scope,
        rest: &[&str],
        request: &ApiRequest,
    ) -> Result<Option<ApiResponse>, ApiError> {
        let action = match (request.method.as_str(), rest) {
            ("POST", ["board", "archive"]) => LifecycleAction::Archive,
            ("POST", ["board", "restore"]) => LifecycleAction::Restore,
            ("DELETE", ["board"]) => LifecycleAction::Purge,
            _ => return Ok(None),
        };
        if !request.principal.provision {
            return Err(forbidden());
        }
        let operation = operation_id(request)?;
        let hash = request_hash(request);
        if let Some(replayed) = self.replay_lifecycle(scope, &operation, &hash).await? {
            return Ok(Some(replayed));
        }
        if !request.body.is_null() {
            return Err(invalid(
                "Board lifecycle routes do not accept a request body.",
            ));
        }
        let response = match action {
            LifecycleAction::Archive => self.archive_board(scope, request, operation, hash).await?,
            LifecycleAction::Restore => self.restore_board(scope, operation, hash).await?,
            LifecycleAction::Purge => {
                self.purge_archived_board(scope, &operation, &hash).await?;
                ApiResponse::checked(200, json!({"purged":true}))?
            }
        };
        Ok(Some(response))
    }

    async fn replay_lifecycle(
        &self,
        scope: &Scope,
        operation: &str,
        hash: &str,
    ) -> Result<Option<ApiResponse>, ApiError> {
        let Some((receipt, _)) = self
            .read_lifecycle_object::<LifecycleReceipt>(&receipt_path(scope, operation))
            .await?
        else {
            return Ok(None);
        };
        if receipt.request_hash != hash {
            return Err(storage_error(StoreError::OperationMismatch));
        }
        if let Some(archive_operation) = &receipt.closes_archive {
            self.remove_closed_archive(scope, archive_operation).await?;
        }
        ApiResponse::checked(receipt.status, receipt.body).map(Some)
    }

    async fn record_receipt(
        &self,
        scope: &Scope,
        operation: &str,
        receipt: &LifecycleReceipt,
    ) -> Result<(), ApiError> {
        match self
            .write_lifecycle_object(
                &receipt_path(scope, operation),
                receipt,
                WriteCondition::Absent,
            )
            .await
        {
            Ok(()) | Err(StoreError::Conflict) => Ok(()),
            Err(error) => Err(storage_error(error)),
        }
    }

    async fn remove_closed_archive(
        &self,
        scope: &Scope,
        archive_operation: &str,
    ) -> Result<(), ApiError> {
        let Some((marker, revision)) = self.read_marker(scope).await? else {
            return Ok(());
        };
        if marker.archive_operation_id != archive_operation {
            return Ok(());
        }
        self.delete_lifecycle_object(&index_path(&marker.purge_after, scope)?)
            .await?;
        match self
            .lifecycle
            .archive_objects
            .delete(&archive_scope(), &marker_path(scope), &revision)
            .await
        {
            Ok(()) => Ok(()),
            Err(error) => Err(storage_error(error)),
        }
    }

    async fn archive_board(
        &self,
        scope: &Scope,
        request: &ApiRequest,
        operation: String,
        hash: String,
    ) -> Result<ApiResponse, ApiError> {
        let configuration = self
            .store
            .get_bounded(scope, ".kanbus.yml", MAX_CANONICAL_OBJECT_BYTES)
            .await
            .map_err(storage_error)?;
        if configuration.is_none() {
            return Err(board_not_found());
        }
        let existing = self.read_marker(scope).await?;
        let marker = match existing {
            Some((marker, _))
                if marker.archive_operation_id == operation
                    && marker.archive_request_hash == hash =>
            {
                marker
            }
            Some(_) => return Err(board_archived()),
            None => {
                let archived_at = (self.clock)();
                let marker = ArchiveMarker {
                    archived_at: archived_at.to_rfc3339_opts(SecondsFormat::Secs, true),
                    purge_after: (archived_at
                        + Duration::days(i64::from(self.lifecycle.retention_days)))
                    .to_rfc3339_opts(SecondsFormat::Secs, true),
                    archived_by: request.principal.actor.clone(),
                    archive_operation_id: operation.clone(),
                    archive_request_hash: hash.clone(),
                    purge_operation_id: None,
                    purge_request_hash: None,
                };
                self.write_index_entry(scope, &marker).await?;
                match self
                    .write_lifecycle_object(&marker_path(scope), &marker, WriteCondition::Absent)
                    .await
                {
                    Ok(()) => marker,
                    Err(StoreError::Conflict) => return Err(board_archived()),
                    Err(error) => return Err(storage_error(error)),
                }
            }
        };
        self.write_index_entry(scope, &marker).await?;
        let body = json!({"archived_at":marker.archived_at,"purge_after":marker.purge_after});
        self.record_receipt(
            scope,
            &operation,
            &LifecycleReceipt {
                request_hash: hash,
                status: 200,
                body: body.clone(),
                closes_archive: None,
            },
        )
        .await?;
        ApiResponse::checked(200, body)
    }

    async fn write_index_entry(
        &self,
        scope: &Scope,
        marker: &ArchiveMarker,
    ) -> Result<(), ApiError> {
        let entry = IndexEntry {
            tenant: scope.tenant().into(),
            project: scope.project().into(),
        };
        match self
            .write_lifecycle_object(
                &index_path(&marker.purge_after, scope)?,
                &entry,
                WriteCondition::Absent,
            )
            .await
        {
            Ok(()) | Err(StoreError::Conflict) => Ok(()),
            Err(error) => Err(storage_error(error)),
        }
    }

    async fn restore_board(
        &self,
        scope: &Scope,
        operation: String,
        hash: String,
    ) -> Result<ApiResponse, ApiError> {
        let Some((marker, _)) = self.read_marker(scope).await? else {
            return Err(board_not_archived());
        };
        if marker.purge_operation_id.is_some() {
            return Err(purge_in_progress());
        }
        let body = json!({"restored":true});
        self.record_receipt(
            scope,
            &operation,
            &LifecycleReceipt {
                request_hash: hash,
                status: 200,
                body: body.clone(),
                closes_archive: Some(marker.archive_operation_id.clone()),
            },
        )
        .await?;
        self.remove_closed_archive(scope, &marker.archive_operation_id)
            .await?;
        ApiResponse::checked(200, body)
    }

    pub(crate) async fn purge_archived_board(
        &self,
        scope: &Scope,
        operation: &str,
        hash: &str,
    ) -> Result<(), ApiError> {
        let Some((mut marker, revision)) = self.read_marker(scope).await? else {
            return Err(board_not_archived());
        };
        match marker.purge_operation_id.as_deref() {
            Some(started) if started != operation => return Err(purge_in_progress()),
            Some(_) if marker.purge_request_hash.as_deref() != Some(hash) => {
                return Err(storage_error(StoreError::OperationMismatch))
            }
            Some(_) => {}
            None => {
                marker.purge_operation_id = Some(operation.into());
                marker.purge_request_hash = Some(hash.into());
                self.write_lifecycle_object(
                    &marker_path(scope),
                    &marker,
                    WriteCondition::Revision(revision),
                )
                .await
                .map_err(storage_error)?;
            }
        }
        self.store
            .purge_scope(scope, operation)
            .await
            .map_err(storage_error)?;
        self.record_receipt(
            scope,
            operation,
            &LifecycleReceipt {
                request_hash: hash.into(),
                status: 200,
                body: json!({"purged":true}),
                closes_archive: Some(marker.archive_operation_id.clone()),
            },
        )
        .await?;
        self.remove_closed_archive(scope, &marker.archive_operation_id)
            .await
    }

    /// Purge every archived board whose retention has expired at `now`.
    ///
    /// The archive index is listed in expiry order up to `now`, never the tenants or the
    /// bucket. At most [`SWEEP_BATCH_LIMIT`] entries are examined per run; later runs
    /// continue with the rest. Entries whose board was restored or archived again are
    /// removed without purging. Each purge goes through the same code path as the API and
    /// uses an operation identifier derived from the board and its archive time, so reruns
    /// and resumed purges are idempotent.
    pub async fn sweep_expired_archives(
        &self,
        now: DateTime<Utc>,
    ) -> Result<SweepReport, ApiError> {
        let cutoff = timestamp_segment(&now);
        let mut report = SweepReport::default();
        let mut examined = 0;
        let mut cursor: Option<String> = None;
        loop {
            let page = self
                .lifecycle
                .archive_objects
                .list(
                    &archive_scope(),
                    INDEX_PREFIX,
                    cursor.as_deref(),
                    INDEX_PAGE_SIZE,
                )
                .await
                .map_err(storage_error)?;
            for path in page.paths {
                let expiry = path.split('/').nth(1).unwrap_or_default();
                if expiry > cutoff.as_str() || examined == SWEEP_BATCH_LIMIT {
                    return Ok(report);
                }
                examined += 1;
                self.sweep_index_entry(&path, expiry, &mut report).await?;
            }
            cursor = page.next_cursor;
            if cursor.is_none() {
                return Ok(report);
            }
        }
    }

    async fn sweep_index_entry(
        &self,
        path: &str,
        expiry: &str,
        report: &mut SweepReport,
    ) -> Result<(), ApiError> {
        let Some((entry, _)) = self.read_lifecycle_object::<IndexEntry>(path).await? else {
            return Ok(());
        };
        let scope = Scope::new(entry.tenant, entry.project).map_err(invalid_archive_state)?;
        let marker = self.read_marker(&scope).await?.map(|(marker, _)| marker);
        let current = marker.as_ref().is_some_and(|marker| {
            index_path(&marker.purge_after, &scope).is_ok_and(|expected| expected == path)
        });
        let Some(marker) = marker.filter(|_| current) else {
            self.delete_lifecycle_object(path).await?;
            report.stale_removed += 1;
            return Ok(());
        };
        let (operation, hash) = match (&marker.purge_operation_id, &marker.purge_request_hash) {
            (Some(operation), Some(hash)) => (operation.clone(), hash.clone()),
            _ => derived_purge_identity(&scope, &marker),
        };
        match self.purge_archived_board(&scope, &operation, &hash).await {
            Ok(()) => report.purged += 1,
            Err(error) => {
                eprintln!(
                    "Kanbus sweep purge failed: expiry={expiry} code={}",
                    error.code
                );
                report.failed += 1;
            }
        }
        Ok(())
    }
}

enum LifecycleAction {
    Archive,
    Restore,
    Purge,
}
