//! API Gateway HTTP API transport. Authentication relies on verified JWT or IAM authorizer context.

use base64::{engine::general_purpose::STANDARD, Engine};
use kanbus_api::{
    api_gateway_response as response, authenticate_cloud, Api, ApiRequest, ServicePrincipals,
};
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde_json::{json, Value};
use std::{collections::BTreeMap, sync::Arc};
use virtuus_store::aws::{DynamoCatalog, S3Store};
use virtuus_store::JournaledStore;

#[tokio::main]
async fn main() -> Result<(), Error> {
    if std::env::var("KANBUS_BACKEND")?.as_str() != "s3" {
        return Err("Lambda requires KANBUS_BACKEND=s3".into());
    }
    let credentials = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let objects = S3Store::new(
        aws_sdk_s3::Client::new(&credentials),
        std::env::var("KANBUS_OBJECT_BUCKET")?,
    );
    let catalog = DynamoCatalog::new(
        aws_sdk_dynamodb::Client::new(&credentials),
        std::env::var("KANBUS_CATALOG_TABLE")?,
    );
    let objects = Arc::new(objects);
    let api = Api::new(
        JournaledStore::new(objects.clone(), Arc::new(catalog)),
        objects,
    )
    .map_err(|error| error.message)?;
    let service_principals = Arc::new(ServicePrincipals::from_environment()?);
    run(service_fn(move |event: LambdaEvent<Value>| {
        let api = api.clone();
        let service_principals = service_principals.clone();
        async move { Ok::<_, Error>(handle(&api, &service_principals, event.payload).await) }
    }))
    .await
}

async fn handle(api: &Api, service_principals: &ServicePrincipals, event: Value) -> Value {
    let principal = match authenticate_cloud(&event, service_principals) {
        Ok(principal) => principal,
        Err(error) => {
            if error.status == 403 {
                let groups = event.pointer("/requestContext/authorizer/jwt/claims/cognito:groups");
                let kind = match groups {
                    Some(Value::String(_)) => "string",
                    Some(Value::Array(_)) => "array",
                    None => "missing",
                    _ => "other",
                };
                let whitespace = groups.and_then(Value::as_str).is_some_and(|value| {
                    value
                        .chars()
                        .any(|character| character.is_ascii_whitespace())
                });
                eprintln!("Kanbus membership denied: group_claim_kind={kind} group_claim_has_whitespace={whitespace}");
            }
            return response(error.status, error.body());
        }
    };
    let Some(method) = event
        .pointer("/requestContext/http/method")
        .and_then(Value::as_str)
    else {
        return response(
            400,
            json!({"error":"invalid_request","message":"HTTP API v2 request required."}),
        );
    };
    let body = event.get("body").and_then(Value::as_str).unwrap_or("");
    let bytes = if event["isBase64Encoded"].as_bool() == Some(true) {
        match STANDARD.decode(body) {
            Ok(bytes) => bytes,
            Err(_) => {
                return response(
                    400,
                    json!({"error":"invalid_request","message":"Invalid body encoding."}),
                )
            }
        }
    } else {
        body.as_bytes().to_vec()
    };
    if bytes.len() > 2 * 1024 * 1024 {
        return response(
            413,
            json!({"error":"body_too_large","message":"Request body exceeds 2 MiB."}),
        );
    }
    let body = if bytes.is_empty() {
        Value::Null
    } else {
        match serde_json::from_slice(&bytes) {
            Ok(body) => body,
            Err(_) => {
                return response(
                    400,
                    json!({"error":"invalid_request","message":"Invalid JSON body."}),
                )
            }
        }
    };
    let query: BTreeMap<_, _> =
        url::form_urlencoded::parse(event["rawQueryString"].as_str().unwrap_or("").as_bytes())
            .into_owned()
            .collect();
    let headers = event["headers"]
        .as_object()
        .map(|headers| {
            headers
                .iter()
                .filter_map(|(key, value)| {
                    value
                        .as_str()
                        .map(|value| (key.to_ascii_lowercase(), value.into()))
                })
                .collect()
        })
        .unwrap_or_default();
    let request = ApiRequest {
        method: method.into(),
        path: event["rawPath"].as_str().unwrap_or("").into(),
        query,
        headers,
        body,
        principal,
    };
    match api.handle(request).await {
        Ok(result) => response(result.status, result.body),
        Err(error) => response(error.status, error.body()),
    }
}
