//! Scheduled Lambda that purges archived boards whose retention has expired.
//!
//! The deployment invokes it on a schedule; the event payload is ignored. It logs counts
//! only, never board or issue content.

use kanbus_api::{Api, BoardLifecycle};
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde_json::{json, Value};
use std::sync::Arc;
use virtuus_store::aws::{DynamoCatalog, S3Store};
use virtuus_store::JournaledStore;

#[tokio::main]
async fn main() -> Result<(), Error> {
    if std::env::var("KANBUS_BACKEND")?.as_str() != "s3" {
        return Err("The sweeper requires KANBUS_BACKEND=s3".into());
    }
    let credentials = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let objects = Arc::new(S3Store::new(
        aws_sdk_s3::Client::new(&credentials),
        std::env::var("KANBUS_OBJECT_BUCKET")?,
    ));
    let catalog = DynamoCatalog::new(
        aws_sdk_dynamodb::Client::new(&credentials),
        std::env::var("KANBUS_CATALOG_TABLE")?,
    );
    let lifecycle = BoardLifecycle::new(
        BoardLifecycle::retention_days_from_environment()?,
        objects.clone(),
    )?;
    let api = Api::new(
        JournaledStore::new(objects.clone(), Arc::new(catalog)),
        objects,
        lifecycle,
    )
    .map_err(|error| error.message)?;
    run(service_fn(move |_event: LambdaEvent<Value>| {
        let api = api.clone();
        async move {
            let report = api
                .sweep_expired_archives(chrono::Utc::now())
                .await
                .map_err(|error| Error::from(error.message))?;
            eprintln!(
                "Kanbus sweep finished: purged={} stale_removed={} failed={}",
                report.purged, report.stale_removed, report.failed
            );
            Ok::<_, Error>(json!({
                "purged": report.purged,
                "stale_removed": report.stale_removed,
                "failed": report.failed
            }))
        }
    }))
    .await
}
