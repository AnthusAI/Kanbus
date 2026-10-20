//! Generic authenticated Kanbus application service.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chrono::Utc;
use kanbus::event_history::{
    event_filename, issue_created_payload, issue_deleted_payload, now_timestamp, EventRecord,
    EventType,
};
use kanbus::hierarchy::validate_parent_child_relationship;
use kanbus::ids::{generate_issue_identifier, IssueIdentifierRequest};
use kanbus::models::{IssueData, ProjectConfiguration};
use kanbus::queries::{filter_issues, search_issues};
use kanbus::workflows::{
    apply_transition_side_effects, validate_status_transition, validate_status_value,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};
use std::sync::Arc;
use virtuus_store::{
    compare_numbers, CatalogQuery, DeleteMutation, EventObject, JournaledStore, Mutation,
    ObjectStore, Scope, StoreError, StoredObject, WriteCondition,
};

mod relations;
use relations::RelationPlan;

const MAX_PROJECTS_PER_QUERY: usize = 8;
const GROUP_PREFIX: &str = "kanbus:";
const MAX_STREAMS: usize = 32;
const MAX_PREDICATES: usize = 16;
const MAX_CANDIDATES: usize = 1000;
const MAX_OBJECT_READS: usize = 1000;
const MAX_ACCEPTED_BYTES: usize = 16 * 1024 * 1024;
/// Maximum canonical file size accepted by writable application APIs.
pub const MAX_CANONICAL_OBJECT_BYTES: usize = 2 * 1024 * 1024;
/// Maximum compact JSON body before gateway string escaping.
pub const MAX_RESPONSE_BODY_BYTES: usize = 5 * 1024 * 1024 / 2;

#[derive(Default, Serialize)]
struct ReadBudget {
    collected_summaries: usize,
    catalog_candidates_examined: usize,
    catalog_requests: usize,
    listed_paths: usize,
    canonical_objects: usize,
    canonical_bytes: usize,
}

impl ReadBudget {
    fn exceeded(&self, limit: &'static str) -> ApiError {
        let message = match limit {
            "event_bytes" | "mutation_bytes" | "object_bytes" => "Canonical content or generated audit history exceeds the API's 2 MiB object limit. Reduce the content size.",
            _ => "Request exceeds bounded query work; narrow the board/type/status selection or reduce the imported dataset.",
        };
        let mut error = ApiError::new(422, "query_budget_exceeded", message);
        error.cost = Some(json!({"limit":limit,"consumed":self}));
        error
    }

    fn summaries(&mut self, count: usize) -> Result<(), ApiError> {
        self.collected_summaries = self.collected_summaries.saturating_add(count);
        if self.collected_summaries > MAX_CANDIDATES {
            return Err(self.exceeded("collected_summaries"));
        }
        Ok(())
    }

    fn before_read(&mut self) -> Result<(), ApiError> {
        if self.maximum_bytes() == 0 {
            return Err(self.exceeded("canonical_bytes"));
        }
        if self.canonical_objects >= MAX_OBJECT_READS {
            return Err(self.exceeded("canonical_objects"));
        }
        self.canonical_objects += 1;
        Ok(())
    }

    fn maximum_bytes(&self) -> usize {
        MAX_CANONICAL_OBJECT_BYTES.min(MAX_ACCEPTED_BYTES.saturating_sub(self.canonical_bytes))
    }

    fn read_error(&self, error: StoreError) -> ApiError {
        match error {
            StoreError::TooLarge { limit } => {
                self.exceeded(if limit < MAX_CANONICAL_OBJECT_BYTES {
                    "canonical_bytes"
                } else {
                    "object_bytes"
                })
            }
            error => storage_error(error),
        }
    }

    fn accept(&mut self, object: &StoredObject) -> Result<(), ApiError> {
        self.canonical_bytes = self.canonical_bytes.saturating_add(object.bytes.len());
        if object.bytes.len() > MAX_CANONICAL_OBJECT_BYTES {
            return Err(self.exceeded("object_bytes"));
        }
        if self.canonical_bytes > MAX_ACCEPTED_BYTES {
            return Err(self.exceeded("canonical_bytes"));
        }
        Ok(())
    }
}

/// Safe HTTP error returned without storage or credential internals.
#[derive(Debug)]
pub struct ApiError {
    /// HTTP status code.
    pub status: u16,
    /// Stable error category.
    pub code: &'static str,
    /// Human-readable explanation.
    pub message: String,
    cost: Option<Value>,
}

impl ApiError {
    fn new(status: u16, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            status,
            code,
            message: message.into(),
            cost: None,
        }
    }

    /// Serialize the public error contract.
    pub fn body(&self) -> Value {
        let message = if self.message.len() > 4096 {
            "Request rejected. Validation details exceed supported response limits."
        } else {
            &self.message
        };
        let mut body = json!({"error":self.code,"message":message});
        if let Some(cost) = &self.cost {
            body["cost"] = cost.clone();
        }
        body
    }
}

fn invalid(message: impl Into<String>) -> ApiError {
    ApiError::new(400, "invalid_request", message)
}

fn storage_error(error: StoreError) -> ApiError {
    match error {
        StoreError::Conflict => ApiError::new(
            409,
            "revision_conflict",
            "The record changed. Reload it before retrying.",
        ),
        StoreError::OperationMismatch => ApiError::new(
            409,
            "operation_conflict",
            "Operation ID already belongs to a different request.",
        ),
        StoreError::Invalid(message) => invalid(message),
        StoreError::TooLarge { .. } => ReadBudget::default().exceeded("object_bytes"),
        error => {
            eprintln!("Kanbus storage operation failed: {error}");
            ApiError::new(
                503,
                "storage_unavailable",
                "Storage is unavailable; the operation may require repair.",
            )
        }
    }
}

/// Which boards of a tenant a grant covers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProjectGrant {
    /// Exactly one named board.
    One(String),
    /// Every board of the tenant.
    AllInTenant,
    /// Every board of every tenant; used only by service principals mapped with tenants "*".
    AllTenants,
}

/// Permission to use boards of one tenant.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Grant {
    /// Tenant (organization) identifier.
    pub tenant: String,
    /// Boards of the tenant that the grant covers.
    pub project: ProjectGrant,
}

/// Verified caller identity and the boards it may use.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Principal {
    /// Verified subject recorded on mutations.
    pub actor: String,
    /// Boards the caller may use; empty grants nothing.
    pub grants: Vec<Grant>,
    /// Whether the caller may provision boards; parsed and exposed, not yet consumed.
    pub provision: bool,
    /// Whether the caller must name the acting user or bot in `X-Kanbus-Actor`.
    pub delegate_actor: bool,
}

impl Principal {
    /// Pure authorization decision for one board.
    pub fn allows(&self, scope: &Scope) -> bool {
        self.grants.iter().any(|grant| match &grant.project {
            ProjectGrant::AllTenants => true,
            ProjectGrant::AllInTenant => grant.tenant == scope.tenant(),
            ProjectGrant::One(project) => {
                grant.tenant == scope.tenant() && project == scope.project()
            }
        })
    }
}

fn group_names(groups: &Value) -> Vec<String> {
    match groups {
        Value::Array(values) => values
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect(),
        Value::String(value) => value
            .trim_matches(['[', ']'])
            .split(|character: char| character == ',' || character.is_ascii_whitespace())
            .map(|part| part.trim().trim_matches('"'))
            .filter(|part| !part.is_empty())
            .map(str::to_string)
            .collect(),
        _ => Vec::new(),
    }
}

/// Derive board grants from verified group claims named `kanbus:<tenant>/<project>`
/// or `kanbus:<tenant>/*`; unrelated groups and malformed names grant nothing.
pub fn grants_from_groups(groups: &Value) -> Vec<Grant> {
    group_names(groups)
        .iter()
        .filter_map(|name| name.strip_prefix(GROUP_PREFIX))
        .filter_map(|board| board.split_once('/'))
        .filter_map(|(tenant, project)| {
            if project == "*" {
                Scope::new(tenant, "board").ok()?;
                Some(Grant {
                    tenant: tenant.into(),
                    project: ProjectGrant::AllInTenant,
                })
            } else {
                Scope::new(tenant, project).ok()?;
                Some(Grant {
                    tenant: tenant.into(),
                    project: ProjectGrant::One(project.into()),
                })
            }
        })
        .collect()
}

const ACTOR_HEADER: &str = "x-kanbus-actor";
const SERVICE_PRINCIPALS_VARIABLE: &str = "KANBUS_SERVICE_PRINCIPALS";

/// Tenants a mapped service role may act in.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServiceTenants {
    /// Every tenant.
    All,
    /// Exactly these tenants.
    Listed(Vec<String>),
}

/// One mapped service role and its capabilities.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServicePrincipal {
    /// Normalized role ARN, `arn:<partition>:iam::<account>:role/<name>`.
    pub role_arn: String,
    /// Tenants the role may act in.
    pub tenants: ServiceTenants,
    /// Whether the role may provision boards.
    pub provision: bool,
    /// Whether the role must name the acting user or bot per request.
    pub delegate_actor: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ServicePrincipalEntry {
    role_arn: String,
    tenants: Value,
    #[serde(default)]
    provision: bool,
    #[serde(default)]
    delegate_actor: bool,
}

/// Deployment mapping from IAM roles to service principals.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ServicePrincipals {
    entries: Vec<ServicePrincipal>,
}

struct RoleArn<'a> {
    partition: &'a str,
    account: &'a str,
    name: &'a str,
}

fn role_name_is_valid(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "+=,.@_-".contains(c))
}

fn arn_fields_are_valid(partition: &str, account: &str) -> bool {
    !partition.is_empty()
        && partition
            .chars()
            .all(|c| c.is_ascii_lowercase() || c == '-')
        && account.len() == 12
        && account.chars().all(|c| c.is_ascii_digit())
}

fn parse_assumed_role_arn(arn: &str) -> Option<RoleArn<'_>> {
    let parts: Vec<&str> = arn.split(':').collect();
    let [prefix, partition, "sts", region, account, resource] = parts.as_slice() else {
        return None;
    };
    if *prefix != "arn" || !region.is_empty() || !arn_fields_are_valid(partition, account) {
        return None;
    }
    let segments: Vec<&str> = resource.split('/').collect();
    let ["assumed-role", name, session] = segments.as_slice() else {
        return None;
    };
    if !role_name_is_valid(name) || session.is_empty() {
        return None;
    }
    Some(RoleArn {
        partition,
        account,
        name,
    })
}

fn parse_configured_role_arn(arn: &str) -> Option<RoleArn<'_>> {
    let parts: Vec<&str> = arn.split(':').collect();
    let [prefix, partition, "iam", region, account, resource] = parts.as_slice() else {
        return None;
    };
    if *prefix != "arn" || !region.is_empty() || !arn_fields_are_valid(partition, account) {
        return None;
    }
    let name = resource.strip_prefix("role/")?;
    if !role_name_is_valid(name) {
        return None;
    }
    Some(RoleArn {
        partition,
        account,
        name,
    })
}

/// Convert an STS assumed-role ARN to the IAM role ARN it represents; the session
/// name is discarded. Anything that is not exactly an assumed-role ARN yields `None`.
pub fn normalize_assumed_role_arn(arn: &str) -> Option<String> {
    let parsed = parse_assumed_role_arn(arn)?;
    Some(format!(
        "arn:{}:iam::{}:role/{}",
        parsed.partition, parsed.account, parsed.name
    ))
}

fn service_principal_from_entry(entry: ServicePrincipalEntry) -> Result<ServicePrincipal, String> {
    let role = parse_configured_role_arn(&entry.role_arn).ok_or_else(|| {
        format!(
            "{SERVICE_PRINCIPALS_VARIABLE}: role_arn \"{}\" must look like arn:aws:iam::<12-digit account>:role/<name> without a path.",
            entry.role_arn
        )
    })?;
    let tenants = match &entry.tenants {
        Value::String(star) if star == "*" => ServiceTenants::All,
        Value::Array(values) if !values.is_empty() => {
            let mut tenants = Vec::new();
            for value in values {
                let tenant = value.as_str().ok_or_else(|| {
                    format!(
                        "{SERVICE_PRINCIPALS_VARIABLE}: tenants of \"{}\" must be strings.",
                        entry.role_arn
                    )
                })?;
                Scope::new(tenant, "board").map_err(|_| {
                    format!(
                        "{SERVICE_PRINCIPALS_VARIABLE}: tenant \"{tenant}\" of \"{}\" is not a valid tenant name.",
                        entry.role_arn
                    )
                })?;
                tenants.push(tenant.to_string());
            }
            ServiceTenants::Listed(tenants)
        }
        _ => {
            return Err(format!(
                "{SERVICE_PRINCIPALS_VARIABLE}: tenants of \"{}\" must be \"*\" or a non-empty list of tenant names.",
                entry.role_arn
            ))
        }
    };
    Ok(ServicePrincipal {
        role_arn: format!(
            "arn:{}:iam::{}:role/{}",
            role.partition, role.account, role.name
        ),
        tenants,
        provision: entry.provision,
        delegate_actor: entry.delegate_actor,
    })
}

impl ServicePrincipals {
    /// Parse the JSON array held in `KANBUS_SERVICE_PRINCIPALS`; an empty string means no
    /// service callers. Invalid JSON, invalid entries and duplicate roles are errors.
    pub fn from_json(text: &str) -> Result<Self, String> {
        if text.trim().is_empty() {
            return Ok(Self::default());
        }
        let entries: Vec<ServicePrincipalEntry> = serde_json::from_str(text)
            .map_err(|error| format!("{SERVICE_PRINCIPALS_VARIABLE} is invalid: {error}"))?;
        let mut parsed: Vec<ServicePrincipal> = Vec::new();
        for entry in entries {
            let principal = service_principal_from_entry(entry)?;
            if parsed
                .iter()
                .any(|existing| existing.role_arn == principal.role_arn)
            {
                return Err(format!(
                    "{SERVICE_PRINCIPALS_VARIABLE}: role_arn \"{}\" appears more than once.",
                    principal.role_arn
                ));
            }
            parsed.push(principal);
        }
        Ok(Self { entries: parsed })
    }

    /// Read `KANBUS_SERVICE_PRINCIPALS`; an absent variable means no service callers.
    pub fn from_environment() -> Result<Self, String> {
        match std::env::var(SERVICE_PRINCIPALS_VARIABLE) {
            Ok(text) => Self::from_json(&text),
            Err(std::env::VarError::NotPresent) => Ok(Self::default()),
            Err(error) => Err(format!(
                "{SERVICE_PRINCIPALS_VARIABLE} is unreadable: {error}"
            )),
        }
    }

    fn find(&self, role_arn: &str) -> Option<&ServicePrincipal> {
        self.entries.iter().find(|entry| entry.role_arn == role_arn)
    }
}

fn actor_value_is_valid(value: &str) -> bool {
    let parts: Vec<&str> = value.split(':').collect();
    let [kind, scope, subject] = parts.as_slice() else {
        return false;
    };
    let lowercase_segment = |segment: &str| {
        !segment.is_empty()
            && segment
                .chars()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
    };
    lowercase_segment(kind)
        && lowercase_segment(scope)
        && (1..=128).contains(&subject.len())
        && subject
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "-_.".contains(c))
}

fn actor_header(event: &Value) -> Option<String> {
    event
        .get("headers")
        .and_then(Value::as_object)?
        .iter()
        .find(|(name, _)| name.eq_ignore_ascii_case(ACTOR_HEADER))
        .map(|(_, value)| value.as_str().unwrap_or("\u{0}").to_string())
}

fn actor_forbidden() -> ApiError {
    ApiError::new(403, "forbidden", "This caller may not set X-Kanbus-Actor.")
}

fn user_principal(claims: &Value) -> Result<Principal, ApiError> {
    let actor = claims
        .get("sub")
        .and_then(Value::as_str)
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| ApiError::new(401, "unauthorized", "Verified subject is required."))?;
    let grants = claims
        .get("cognito:groups")
        .map(grants_from_groups)
        .unwrap_or_default();
    if grants.is_empty() {
        return Err(forbidden());
    }
    Ok(Principal {
        actor: actor.to_string(),
        grants,
        provision: false,
        delegate_actor: false,
    })
}

fn service_principal(
    iam: &Value,
    service_principals: &ServicePrincipals,
) -> Result<Principal, ApiError> {
    let caller = iam
        .get("userArn")
        .and_then(Value::as_str)
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| ApiError::new(401, "unauthorized", "Verified caller is required."))?;
    let parsed = parse_assumed_role_arn(caller).ok_or_else(forbidden)?;
    let account_matches = iam
        .get("accountId")
        .and_then(Value::as_str)
        .is_some_and(|account| account == parsed.account);
    if !account_matches {
        return Err(forbidden());
    }
    let role_arn = format!(
        "arn:{}:iam::{}:role/{}",
        parsed.partition, parsed.account, parsed.name
    );
    let mapped = service_principals.find(&role_arn).ok_or_else(forbidden)?;
    let grants = match &mapped.tenants {
        ServiceTenants::All => vec![Grant {
            tenant: "*".into(),
            project: ProjectGrant::AllTenants,
        }],
        ServiceTenants::Listed(tenants) => tenants
            .iter()
            .map(|tenant| Grant {
                tenant: tenant.clone(),
                project: ProjectGrant::AllInTenant,
            })
            .collect(),
    };
    Ok(Principal {
        actor: mapped.role_arn.clone(),
        grants,
        provision: mapped.provision,
        delegate_actor: mapped.delegate_actor,
    })
}

/// Build a principal only from the authorizer context API Gateway verified: a JWT context
/// yields a user, an IAM context yields a mapped service role, anything else is rejected.
/// `X-Kanbus-Actor` is honored only for service principals mapped with `delegate_actor`.
pub fn authenticate_cloud(
    event: &Value,
    service_principals: &ServicePrincipals,
) -> Result<Principal, ApiError> {
    let authorizer = event.pointer("/requestContext/authorizer");
    let present = |key: &str| {
        authorizer
            .and_then(|context| context.get(key))
            .filter(|value| !value.is_null())
    };
    let mut principal = match (present("jwt"), present("iam")) {
        (Some(jwt), None) => {
            let claims = jwt.get("claims").ok_or_else(|| {
                ApiError::new(401, "unauthorized", "Verified authorization is required.")
            })?;
            user_principal(claims)?
        }
        (None, Some(iam)) => service_principal(iam, service_principals)?,
        _ => {
            return Err(ApiError::new(
                401,
                "unauthorized",
                "Verified authorization is required.",
            ))
        }
    };
    let header = actor_header(event);
    if principal.delegate_actor {
        let value = header.ok_or_else(|| invalid("X-Kanbus-Actor is required."))?;
        if !actor_value_is_valid(&value) {
            return Err(invalid(
                "X-Kanbus-Actor must look like <kind>:<scope>:<subject>.",
            ));
        }
        principal.actor = value;
    } else if header.is_some() {
        return Err(actor_forbidden());
    }
    Ok(principal)
}

/// Authorize an explicitly configured secret for loopback development; the
/// principal is granted exactly the one board the local store serves.
pub fn authenticate_local(
    authorization: Option<&str>,
    secret: &str,
    served_board: &Scope,
    actor_header_value: Option<&str>,
) -> Result<Principal, ApiError> {
    let candidate = authorization
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or("");
    let candidate_hash = Sha256::digest(candidate.as_bytes());
    let secret_hash = Sha256::digest(secret.as_bytes());
    let difference = candidate_hash
        .iter()
        .zip(secret_hash.iter())
        .fold(0u8, |difference, (a, b)| difference | (a ^ b));
    if secret.is_empty() || candidate.is_empty() || difference != 0 {
        return Err(ApiError::new(
            401,
            "unauthorized",
            "A valid local bearer secret is required.",
        ));
    }
    if actor_header_value.is_some() {
        return Err(actor_forbidden());
    }
    Ok(Principal {
        actor: "local-member".into(),
        grants: vec![Grant {
            tenant: served_board.tenant().into(),
            project: ProjectGrant::One(served_board.project().into()),
        }],
        provision: false,
        delegate_actor: false,
    })
}

fn forbidden() -> ApiError {
    ApiError::new(403, "forbidden", "Board access is not granted.")
}

fn board_exists() -> ApiError {
    ApiError::new(409, "board_exists", "The board is already provisioned.")
}

fn parse_board_configuration(bytes: &[u8]) -> Result<ProjectConfiguration, String> {
    let configuration: ProjectConfiguration =
        serde_yaml::from_slice(bytes).map_err(|error| error.to_string())?;
    safe_relative_path(&configuration.project_directory).map_err(|error| error.message)?;
    let errors = kanbus::config_loader::validate_project_configuration(&configuration);
    if errors.is_empty() {
        Ok(configuration)
    } else {
        Err(errors.join("; "))
    }
}

fn provisioned_configuration_bytes(body: &Value) -> Result<Vec<u8>, ApiError> {
    let invalid_configuration =
        |message: &str| ApiError::new(422, "invalid_configuration", message);
    if body.is_null() {
        let defaults = kanbus::config::default_project_configuration();
        return serde_yaml::to_string(&defaults)
            .map(String::into_bytes)
            .map_err(|error| invalid(error.to_string()));
    }
    let text = body
        .as_object()
        .filter(|fields| fields.len() == 1)
        .and_then(|fields| fields.get("configuration"))
        .and_then(Value::as_str)
        .ok_or_else(|| {
            invalid_configuration(
                "Send no body for the default configuration or {\"configuration\": \"<.kanbus.yml text>\"}.",
            )
        })?;
    if text.len() > MAX_CANONICAL_OBJECT_BYTES {
        return Err(invalid_configuration(
            "Configuration exceeds the size limit.",
        ));
    }
    Ok(text.as_bytes().to_vec())
}

/// Generic API resolving the addressed board from each request path.
#[derive(Clone)]
pub struct Api {
    store: JournaledStore,
    object_store: Arc<dyn ObjectStore>,
}

#[derive(Clone)]
struct ScopedApi {
    store: JournaledStore,
    object_store: Arc<dyn ObjectStore>,
    scope: Scope,
    namespace: String,
}

/// Transport-independent request carrying a verified principal.
pub struct ApiRequest {
    /// HTTP verb.
    pub method: String,
    /// Absolute route path including the board prefix.
    pub path: String,
    /// Decoded URL parameters.
    pub query: BTreeMap<String, String>,
    /// Lowercase HTTP header keys.
    pub headers: BTreeMap<String, String>,
    /// Parsed JSON body.
    pub body: Value,
    /// Verified caller identity and board grants.
    pub principal: Principal,
}

/// JSON HTTP response.
pub struct ApiResponse {
    /// HTTP response status.
    pub status: u16,
    /// JSON response body.
    pub body: Value,
}

impl ApiResponse {
    fn checked(status: u16, body: Value) -> Result<Self, ApiError> {
        check_response_body(&body)?;
        Ok(Self { status, body })
    }
}

fn check_response_body(body: &Value) -> Result<(), ApiError> {
    let size = serde_json::to_vec(body).unwrap().len();
    if size > MAX_RESPONSE_BODY_BYTES {
        let mut error = ApiError::new(422, "query_budget_exceeded", "Response exceeds the workspace size limit. Select fewer records or contact an administrator for large histories.");
        error.cost = Some(json!({"limit":"response_bytes","serialized_body_bytes":size}));
        return Err(error);
    }
    Ok(())
}

/// Serialize a bounded HTTP API proxy envelope, including error bodies.
pub fn api_gateway_response(status: u16, body: Value) -> Value {
    let (status, body) = match check_response_body(&body) {
        Ok(()) => (status, body),
        Err(error) => (error.status, error.body()),
    };
    json!({"statusCode":status,"headers":{"content-type":"application/json","cache-control":"no-store"},"body":body.to_string(),"isBase64Encoded":false})
}

impl Api {
    /// Create an API over a journaled store and the object store beneath it; boards are
    /// resolved per request. The object store carries the relations control records and
    /// must be the same backend the journaled store publishes to.
    pub fn new(store: JournaledStore, objects: Arc<dyn ObjectStore>) -> Result<Self, ApiError> {
        let store = store
            .with_canonical_read_limit(MAX_CANONICAL_OBJECT_BYTES)
            .map_err(storage_error)?;
        Ok(Self {
            store,
            object_store: objects,
        })
    }

    /// Route an authenticated request to the board named in its path.
    pub async fn handle(&self, request: ApiRequest) -> Result<ApiResponse, ApiError> {
        if request
            .query
            .iter()
            .map(|(key, value)| key.len().saturating_add(value.len()))
            .sum::<usize>()
            > 64 * 1024
        {
            return Err(ReadBudget::default().exceeded("query_bytes"));
        }
        if request.principal.actor.trim().is_empty() {
            return Err(ApiError::new(
                401,
                "unauthorized",
                "A verified member is required.",
            ));
        }
        let path = request.path.clone();
        let segments: Vec<&str> = path.trim_matches('/').split('/').collect();
        match segments.as_slice() {
            [tenant, "api", "issues"] if request.method == "GET" => {
                self.list_across_boards(tenant, request).await
            }
            [tenant, project, "api", rest @ ..] => {
                let scope =
                    Scope::new(*tenant, *project).map_err(|error| invalid(error.to_string()))?;
                if !request.principal.allows(&scope) {
                    return Err(forbidden());
                }
                let mut scoped_request = request;
                scoped_request.path = format!("/api/{}", rest.join("/"));
                ScopedApi {
                    store: self.store.clone(),
                    object_store: self.object_store.clone(),
                    namespace: scope.namespace(),
                    scope,
                }
                .route(scoped_request)
                .await
            }
            _ => Err(ApiError::new(404, "not_found", "Route not found.")),
        }
    }

    async fn list_across_boards(
        &self,
        tenant: &str,
        request: ApiRequest,
    ) -> Result<ApiResponse, ApiError> {
        let names = request
            .query
            .get("projects")
            .ok_or_else(|| invalid("Name the boards to list with projects=a,b."))?;
        let mut scopes = BTreeMap::new();
        for name in names.split(',') {
            let scope = Scope::new(tenant, name).map_err(|error| invalid(error.to_string()))?;
            scopes.insert(name.to_string(), scope);
        }
        if scopes.len() > MAX_PROJECTS_PER_QUERY {
            return Err(ReadBudget::default().exceeded("selected_projects"));
        }
        if scopes
            .values()
            .any(|scope| !request.principal.allows(scope))
        {
            return Err(forbidden());
        }
        let selected: Vec<(String, Scope)> = scopes.into_iter().collect();
        let first = selected[0].1.clone();
        let scoped = ScopedApi {
            store: self.store.clone(),
            object_store: self.object_store.clone(),
            namespace: first.namespace(),
            scope: first,
        };
        ApiResponse::checked(200, scoped.list_issues(&request.query, selected).await?)
    }
}

impl ScopedApi {
    async fn route(&self, request: ApiRequest) -> Result<ApiResponse, ApiError> {
        if request.method == "DELETE" {
            let operation = operation_id(&request)?;
            if let Some(deleted) = self
                .store
                .deletion_operation(&self.scope, &operation, &request_hash(&request))
                .await
                .map_err(storage_error)?
            {
                return ApiResponse::checked(
                    200,
                    json!({"deleted":true,"issue_id":request.path.trim_end_matches('/').rsplit('/').next(),"catalog_pending":deleted.repair_pending}),
                );
            }
        }
        if matches!(request.method.as_str(), "POST" | "PATCH") {
            let operation = operation_id(&request)?;
            if let Some(committed) = self
                .store
                .operation(&self.scope, &operation, &request_hash(&request))
                .await
                .map_err(storage_error)?
            {
                let mut body = issue_response(&committed.stored)?;
                body["catalog_pending"] = json!(committed.repair_pending);
                return ApiResponse::checked(200, body);
            }
        }
        if request.method == "PUT" && request.path.trim_matches('/') == "api/config" {
            return self.provision(&request).await;
        }
        let configuration = self.configuration().await?;
        let segments: Vec<_> = request.path.trim_matches('/').split('/').collect();
        let result = match (request.method.as_str(), segments.as_slice()) {
            ("GET", ["api", "config"]) => {
                browser_configuration(&configuration, &request.principal.actor)?
            }
            ("GET", ["api", "issues"]) => {
                if request.query.contains_key("projects") {
                    return Err(invalid("Unknown query parameter."));
                }
                let project = self.scope.project().to_string();
                self.list_issues(&request.query, vec![(project, self.scope.clone())])
                    .await?
            }
            ("POST", ["api", "issues"]) => self.create(&configuration, &request).await?,
            ("GET", ["api", "issues", identifier]) => {
                let stored = self.issue(&configuration, identifier).await?;
                issue_response(&stored)?
            }
            ("PATCH", ["api", "issues", identifier]) => {
                self.update(&configuration, identifier, &request, false)
                    .await?
            }
            ("DELETE", ["api", "issues", identifier]) => {
                self.delete(&configuration, identifier, &request).await?
            }
            ("POST", ["api", "issues", identifier, "comments"]) => {
                self.update(&configuration, identifier, &request, true)
                    .await?
            }
            ("GET", ["api", "issues", identifier, "events"]) => {
                self.events(&configuration, identifier).await?
            }
            _ => return Err(ApiError::new(404, "not_found", "Route not found.")),
        };
        ApiResponse::checked(if request.method == "POST" { 201 } else { 200 }, result)
    }

    async fn configuration(&self) -> Result<ProjectConfiguration, ApiError> {
        let stored = self
            .store
            .get_bounded(&self.scope, ".kanbus.yml", MAX_CANONICAL_OBJECT_BYTES)
            .await
            .map_err(storage_error)?
            .ok_or_else(|| {
                ApiError::new(
                    503,
                    "configuration_missing",
                    "Project configuration is missing.",
                )
            })?;
        ReadBudget::default().accept(&stored)?;
        parse_board_configuration(&stored.bytes)
            .map_err(|message| ApiError::new(503, "configuration_invalid", message))
    }

    async fn provision(&self, request: &ApiRequest) -> Result<ApiResponse, ApiError> {
        if !request.principal.provision {
            return Err(forbidden());
        }
        let operation = operation_id(request)?;
        let hash = request_hash(request);
        if let Some(committed) = self
            .store
            .operation(&self.scope, &operation, &hash)
            .await
            .map_err(storage_error)?
        {
            let configuration = parse_board_configuration(&committed.stored.bytes)
                .map_err(|message| ApiError::new(503, "configuration_invalid", message))?;
            return ApiResponse::checked(
                200,
                browser_configuration(&configuration, &request.principal.actor)?,
            );
        }
        let existing = self
            .store
            .get_bounded(&self.scope, ".kanbus.yml", MAX_CANONICAL_OBJECT_BYTES)
            .await
            .map_err(storage_error)?;
        if existing.is_some() {
            return Err(board_exists());
        }
        let bytes = provisioned_configuration_bytes(&request.body)?;
        let configuration = parse_board_configuration(&bytes)
            .map_err(|message| ApiError::new(422, "invalid_configuration", message))?;
        let mutation = Mutation {
            path: ".kanbus.yml".into(),
            condition: WriteCondition::Absent,
            bytes,
            content_type: "application/yaml".into(),
            event_objects: Vec::new(),
            operation_id: operation,
            request_hash: hash,
            fields: BTreeMap::new(),
        };
        self.store
            .commit(&self.scope, &mutation)
            .await
            .map_err(|error| match error {
                StoreError::Conflict => board_exists(),
                other => storage_error(other),
            })?;
        ApiResponse::checked(
            201,
            browser_configuration(&configuration, &request.principal.actor)?,
        )
    }

    async fn issue(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<StoredObject, ApiError> {
        let path = issue_path(configuration, identifier)?;
        let stored = self
            .store
            .get_bounded(&self.scope, &path, MAX_CANONICAL_OBJECT_BYTES)
            .await
            .map_err(storage_error)?
            .ok_or_else(|| ApiError::new(404, "not_found", "Issue not found."))?;
        ReadBudget::default().accept(&stored)?;
        let raw: Value = serde_json::from_slice(&stored.bytes).map_err(|_| {
            ApiError::new(503, "invalid_issue", "Canonical issue is not valid JSON.")
        })?;
        if raw.get("id").and_then(Value::as_str) != Some(identifier) {
            return Err(ApiError::new(
                503,
                "invalid_issue",
                "Canonical issue identity does not match its path.",
            ));
        }
        Ok(stored)
    }

    async fn objects(
        &self,
        prefix: &str,
        budget: &mut ReadBudget,
    ) -> Result<Vec<(String, StoredObject)>, ApiError> {
        let mut result = Vec::new();
        let mut cursor = None;
        loop {
            let page = self
                .store
                .list(&self.scope, prefix, cursor.as_deref(), 100)
                .await
                .map_err(storage_error)?;
            budget.listed_paths = budget.listed_paths.saturating_add(page.paths.len());
            if budget.listed_paths > MAX_CANDIDATES {
                return Err(budget.exceeded("listed_paths"));
            }
            for path in page.paths {
                if !path.ends_with(".json") {
                    continue;
                }
                budget.before_read()?;
                if let Some(object) = self
                    .store
                    .get_bounded(&self.scope, &path, budget.maximum_bytes())
                    .await
                    .map_err(|error| budget.read_error(error))?
                {
                    budget.accept(&object)?;
                    result.push((path, object));
                }
            }
            cursor = page.next_cursor;
            if cursor.is_none() {
                break;
            }
        }
        Ok(result)
    }

    async fn list_issues(
        &self,
        query: &BTreeMap<String, String>,
        selected_projects: Vec<(String, Scope)>,
    ) -> Result<Value, ApiError> {
        let allowed = [
            "type", "status", "assignee", "label", "parent", "search", "sort", "limit", "cursor",
            "fields", "projects", "types",
        ];
        if query.keys().any(|key| !allowed.contains(&key.as_str())) {
            return Err(invalid("Unknown query parameter."));
        }
        let predicates: Vec<FieldPredicate> = query
            .get("fields")
            .map(|value| serde_json::from_str(value))
            .transpose()
            .map_err(|error| invalid(format!("Invalid fields: {error}")))?
            .unwrap_or_default();
        if predicates.len() > MAX_PREDICATES {
            return Err(ReadBudget::default().exceeded("field_predicates"));
        }
        for predicate in &predicates {
            predicate.validate()?;
        }
        let limit = query
            .get("limit")
            .map(|value| value.parse::<usize>())
            .transpose()
            .map_err(|_| invalid("Invalid limit."))?
            .unwrap_or(100);
        if !(1..=100).contains(&limit) {
            return Err(invalid("Limit must be between 1 and 100."));
        }
        let mut bound_query = query.clone();
        bound_query.remove("cursor");
        let fingerprint = format!(
            "{:x}",
            Sha256::digest(
                format!(
                    "{}:{}",
                    selected_projects
                        .iter()
                        .map(|(_, scope)| scope.namespace())
                        .collect::<Vec<_>>()
                        .join(","),
                    serde_json::to_string(&bound_query).unwrap()
                )
                .as_bytes()
            )
        );
        let offset = match query.get("cursor") {
            None => 0,
            Some(cursor) => {
                let bytes = URL_SAFE_NO_PAD
                    .decode(cursor)
                    .map_err(|_| invalid("Invalid cursor."))?;
                let decoded: Cursor =
                    serde_json::from_slice(&bytes).map_err(|_| invalid("Invalid cursor."))?;
                if decoded.query != fingerprint {
                    return Err(invalid("Cursor does not belong to this query."));
                }
                decoded.offset
            }
        };
        if query.contains_key("type") && query.contains_key("types") {
            return Err(invalid("Use type or types, not both."));
        }
        let types: Vec<String> = query
            .get("type")
            .or_else(|| query.get("types"))
            .map(|value| value.split(',').map(str::to_string).collect())
            .unwrap_or_default();
        if types.iter().any(|value| value.is_empty()) {
            return Err(invalid("Issue type selection must not be empty."));
        }
        let candidate_query = CatalogQuery {
            issue_types: types.clone(),
            statuses: query
                .get("status")
                .map(|value| vec![value.clone()])
                .unwrap_or_default(),
        };
        let mut distinct_types = types.clone();
        distinct_types.sort();
        distinct_types.dedup();
        if distinct_types.len() > MAX_PREDICATES
            || selected_projects
                .len()
                .saturating_mul(distinct_types.len().max(1))
                > MAX_STREAMS
        {
            return Err(ReadBudget::default().exceeded("query_streams"));
        }
        let mut budget = ReadBudget::default();
        let mut candidates = Vec::new();
        for (project, scope) in selected_projects {
            let mut scoped = self.clone();
            scoped.namespace = scope.namespace();
            scoped.scope = scope;
            let configuration = scoped.configuration().await?;
            let prefix = format!("{}/issues/", configuration.project_directory);
            let mut cursor = None;
            loop {
                let page = scoped
                    .store
                    .query(&scoped.scope, &candidate_query, cursor.as_deref(), 100)
                    .await
                    .map_err(storage_error)?;
                budget.catalog_requests = budget.catalog_requests.saturating_add(page.requests);
                budget.catalog_candidates_examined = budget
                    .catalog_candidates_examined
                    .saturating_add(page.candidates);
                if budget.catalog_requests > 512 {
                    return Err(budget.exceeded("catalog_requests"));
                }
                if budget.catalog_candidates_examined > 32_000 {
                    return Err(budget.exceeded("catalog_candidates_examined"));
                }
                budget.summaries(page.cards.len())?;
                for card in page.cards {
                    if card.path.starts_with(&prefix) {
                        candidates.push((
                            scoped.clone(),
                            project.clone(),
                            card.path,
                            prefix.clone(),
                        ));
                    }
                }
                cursor = page.next_cursor;
                if cursor.is_none() {
                    break;
                }
            }
        }
        let mut matches = Vec::new();
        for (scoped, project, path, prefix) in candidates {
            budget.before_read()?;
            let Some(stored) = scoped
                .store
                .get_bounded(&scoped.scope, &path, budget.maximum_bytes())
                .await
                .map_err(|error| budget.read_error(error))?
            else {
                continue;
            };
            budget.accept(&stored)?;
            let raw: Value = serde_json::from_slice(&stored.bytes)
                .map_err(|error| ApiError::new(503, "invalid_issue", error.to_string()))?;
            let issue: IssueData = serde_json::from_value(raw.clone())
                .map_err(|error| ApiError::new(503, "invalid_issue", error.to_string()))?;
            if validate_issue_identifier(&issue.identifier).is_err()
                || path != format!("{prefix}{}.json", issue.identifier)
            {
                return Err(ApiError::new(
                    503,
                    "invalid_issue",
                    "Canonical issue identity does not match its path.",
                ));
            }
            if !types.is_empty() && !types.contains(&issue.issue_type) {
                continue;
            }
            let selected = filter_issues(
                vec![issue.clone()],
                query.get("status").map(String::as_str),
                None,
                query.get("assignee").map(String::as_str),
                query.get("label").map(String::as_str),
                query.get("parent").map(String::as_str),
            );
            if search_issues(selected, query.get("search").map(String::as_str)).is_empty()
                || !predicates.iter().all(|predicate| predicate.matches(&raw))
            {
                continue;
            }
            matches.push((issue, raw, stored.revision, project.clone()));
        }
        match query
            .get("sort")
            .map(String::as_str)
            .unwrap_or("updated_at")
        {
            "priority" => matches.sort_by(|a, b| {
                a.0.priority
                    .cmp(&b.0.priority)
                    .then_with(|| a.3.cmp(&b.3))
                    .then_with(|| a.0.identifier.cmp(&b.0.identifier))
            }),
            "updated_at" => matches.sort_by(|a, b| {
                b.0.updated_at
                    .cmp(&a.0.updated_at)
                    .then_with(|| a.3.cmp(&b.3))
                    .then_with(|| a.0.identifier.cmp(&b.0.identifier))
            }),
            _ => return Err(invalid("Invalid sort key.")),
        }
        let next_offset = offset.saturating_add(limit);
        let next_cursor = if next_offset < matches.len() {
            Some(
                URL_SAFE_NO_PAD.encode(
                    serde_json::to_vec(&Cursor {
                        query: fingerprint,
                        offset: next_offset,
                    })
                    .unwrap(),
                ),
            )
        } else {
            None
        };
        let issues: Vec<_> = matches
            .into_iter()
            .skip(offset)
            .take(limit)
            .map(|(_, issue, revision, project)| json!({"issue":issue,"revision":revision,"project":project}))
            .collect();
        Ok(json!({"issues":issues,"next_cursor":next_cursor,"cost":budget}))
    }

    async fn create(
        &self,
        configuration: &ProjectConfiguration,
        request: &ApiRequest,
    ) -> Result<Value, ApiError> {
        let operation_id = operation_id(request)?;
        let fields = mutable_fields(&request.body)?;
        let title = fields
            .get("title")
            .and_then(Value::as_str)
            .filter(|title| !title.trim().is_empty())
            .ok_or_else(|| invalid("A nonempty title is required."))?;
        let issue_type = fields
            .get("type")
            .and_then(Value::as_str)
            .ok_or_else(|| invalid("An issue type is required."))?;
        let identifier = generate_issue_identifier(&IssueIdentifierRequest {
            title: title.into(),
            existing_ids: HashSet::new(),
            prefix: configuration.project_key.clone(),
            requested_id: None,
        })
        .map_err(|error| invalid(error.to_string()))?
        .identifier;
        let timestamp = now_timestamp();
        let mut raw = json!({"id":identifier,"title":title,"description":"","type":issue_type,"status":configuration.initial_status,"priority":configuration.default_priority,"assignee":configuration.assignee,"creator":request.principal.actor,"parent":null,"labels":[],"dependencies":[],"comments":[],"created_at":timestamp,"updated_at":timestamp,"closed_at":null,"custom":{}});
        for (key, value) in fields {
            raw[key] = value.clone();
        }
        let issue = self.validate(configuration, &raw, None).await?;
        let relation_plan = RelationPlan::between(None, &issue);
        let effect = apply_transition_side_effects(&issue, &issue.status, issue.created_at);
        raw["closed_at"] = serde_json::to_value(effect.closed_at).unwrap();
        let event = EventRecord::new(
            &issue.identifier,
            EventType::IssueCreated,
            &request.principal.actor,
            issue_created_payload(&issue),
            timestamp,
        );
        self.attach_planned_relations(configuration, &issue, &relation_plan)
            .await?;
        let committed = self
            .commit(
                configuration,
                raw,
                WriteCondition::Absent,
                operation_id,
                request_hash(request),
                vec![event],
            )
            .await?;
        self.detach_planned_relations(&issue.identifier, &relation_plan)
            .await;
        Ok(committed)
    }

    async fn update(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
        request: &ApiRequest,
        comment: bool,
    ) -> Result<Value, ApiError> {
        let operation_id = operation_id(request)?;
        let expected = request
            .headers
            .get("if-match")
            .filter(|value| !value.is_empty())
            .ok_or_else(|| ApiError::new(428, "revision_required", "If-Match is required."))?
            .trim_matches('"')
            .to_string();
        let stored = self.issue(configuration, identifier).await?;
        if stored.revision.trim_matches('"') != expected.trim_matches('"') {
            return Err(ApiError::new(
                409,
                "revision_conflict",
                "The record changed. Reload it before retrying.",
            ));
        }
        let mut raw: Value =
            serde_json::from_slice(&stored.bytes).map_err(|error| invalid(error.to_string()))?;
        let before: IssueData =
            serde_json::from_value(raw.clone()).map_err(|error| invalid(error.to_string()))?;
        let timestamp = now_timestamp();
        let mut events = Vec::new();
        if comment {
            let fields = request
                .body
                .as_object()
                .ok_or_else(|| invalid("Expected a JSON object."))?;
            if fields.len() != 1 {
                return Err(invalid("Comments accept only text."));
            }
            let text = fields
                .get("text")
                .and_then(Value::as_str)
                .filter(|text| !text.trim().is_empty())
                .ok_or_else(|| invalid("Comment text is required."))?;
            let comment_id = uuid::Uuid::new_v4().to_string();
            let comments = raw
                .get_mut("comments")
                .and_then(Value::as_array_mut)
                .ok_or_else(|| invalid("Issue comments are invalid."))?;
            comments.push(json!({"id":comment_id,"author":request.principal.actor,"text":text,"created_at":timestamp,"comment_type":"default"}));
            events.push(EventRecord::new(
                identifier,
                EventType::CommentAdded,
                &request.principal.actor,
                json!({"comment_id":comment_id,"comment_author":request.principal.actor}),
                timestamp.clone(),
            ));
        } else {
            for (key, value) in mutable_fields(&request.body)? {
                if key == "custom" {
                    let custom = value
                        .as_object()
                        .ok_or_else(|| invalid("Custom values must be an object."))?;
                    let target = raw
                        .get_mut("custom")
                        .and_then(Value::as_object_mut)
                        .ok_or_else(|| invalid("Issue custom values are invalid."))?;
                    for (name, value) in custom {
                        target.insert(name.clone(), value.clone());
                    }
                } else {
                    raw[key] = value.clone();
                }
            }
        }
        raw["updated_at"] = json!(timestamp);
        let after = self.validate(configuration, &raw, Some(&before)).await?;
        let relation_plan = RelationPlan::between(Some(&before), &after);
        if after.status != before.status {
            let effect = apply_transition_side_effects(&before, &after.status, Utc::now());
            raw["closed_at"] = serde_json::to_value(effect.closed_at).unwrap();
            events.push(EventRecord::new(
                identifier,
                EventType::StateTransition,
                &request.principal.actor,
                json!({"from_status":before.status,"to_status":after.status}),
                timestamp.clone(),
            ));
        }
        if !comment {
            let original: Value = serde_json::from_slice(&stored.bytes).unwrap();
            let mut changes = Map::new();
            for (key, value) in raw.as_object().unwrap() {
                if key != "updated_at"
                    && key != "status"
                    && key != "closed_at"
                    && original.get(key) != Some(value)
                {
                    changes.insert(key.clone(), json!({"from":original.get(key),"to":value}));
                }
            }
            if !changes.is_empty() {
                events.push(EventRecord::new(
                    identifier,
                    EventType::FieldUpdated,
                    &request.principal.actor,
                    json!({"changes":changes}),
                    timestamp,
                ));
            }
        }
        self.attach_planned_relations(configuration, &after, &relation_plan)
            .await?;
        let committed = self
            .commit(
                configuration,
                raw,
                WriteCondition::Revision(stored.revision.clone()),
                operation_id,
                request_hash(request),
                events,
            )
            .await?;
        self.detach_planned_relations(&after.identifier, &relation_plan)
            .await;
        Ok(committed)
    }

    async fn validate(
        &self,
        configuration: &ProjectConfiguration,
        raw: &Value,
        before: Option<&IssueData>,
    ) -> Result<IssueData, ApiError> {
        self.validate_mutation_support(configuration).await?;
        self.validate_issue(configuration, raw, before).await
    }

    async fn validate_mutation_support(
        &self,
        configuration: &ProjectConfiguration,
    ) -> Result<(), ApiError> {
        let mut policy_cursor = None;
        let mut policy_budget = ReadBudget::default();
        loop {
            let policies = self
                .store
                .list(
                    &self.scope,
                    &format!("{}/policies/", configuration.project_directory),
                    policy_cursor.as_deref(),
                    100,
                )
                .await
                .map_err(storage_error)?;
            policy_budget.listed_paths = policy_budget
                .listed_paths
                .saturating_add(policies.paths.len());
            if policy_budget.listed_paths > MAX_CANDIDATES {
                return Err(policy_budget.exceeded("listed_paths"));
            }
            if policies.paths.iter().any(|path| path.ends_with(".policy")) {
                return Err(ApiError::new(409,"unsupported_project_policy","This API does not yet execute project policies; mutations are disabled for this project."));
            }
            policy_cursor = policies.next_cursor;
            if policy_cursor.is_none() {
                break;
            }
        }
        if configuration.hooks.enabled
            && (!configuration.hooks.before.is_empty() || !configuration.hooks.after.is_empty())
        {
            return Err(ApiError::new(
                409,
                "unsupported_project_hooks",
                "This API does not execute project hooks; mutations are disabled for this project.",
            ));
        }
        Ok(())
    }

    async fn validate_issue(
        &self,
        configuration: &ProjectConfiguration,
        raw: &Value,
        before: Option<&IssueData>,
    ) -> Result<IssueData, ApiError> {
        let issue: IssueData =
            serde_json::from_value(raw.clone()).map_err(|error| invalid(error.to_string()))?;
        if let Some(previous) = before {
            if previous.issue_type != issue.issue_type
                && (configuration.hierarchy.contains(&previous.issue_type)
                    || configuration.hierarchy.contains(&issue.issue_type))
            {
                return Err(ApiError::new(
                    409,
                    "type_change_unsupported",
                    "Changing an issue to or from a hierarchy type is not supported by this API.",
                ));
            }
        }
        validate_dependency_links(&issue)?;
        if issue.title.trim().is_empty() {
            return Err(invalid("A nonempty title is required."));
        }
        if !configuration.types.contains(&issue.issue_type)
            && !configuration.hierarchy.contains(&issue.issue_type)
        {
            return Err(invalid("Unknown issue type."));
        }
        if issue.priority < 0
            || issue.priority > u8::MAX as i32
            || !configuration
                .priorities
                .contains_key(&(issue.priority as u8))
        {
            return Err(invalid("Invalid priority."));
        }
        validate_status_value(
            configuration,
            &issue.issue_type,
            &issue.status,
            Some(&issue.identifier),
        )
        .map_err(|error| invalid(error.to_string()))?;
        if let Some(before) = before {
            if before.status != issue.status {
                validate_status_transition(
                    configuration,
                    &issue.issue_type,
                    &before.status,
                    &issue.status,
                )
                .map_err(|error| invalid(error.to_string()))?;
            }
        }
        if issue.parent.as_deref() == Some(issue.identifier.as_str()) {
            return Err(invalid("An issue cannot parent itself."));
        }
        Ok(issue)
    }

    async fn delete(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
        request: &ApiRequest,
    ) -> Result<Value, ApiError> {
        if !request.body.is_null() {
            return Err(invalid("DELETE does not accept a request body."));
        }
        let expected = request
            .headers
            .get("if-match")
            .filter(|revision| !revision.is_empty())
            .ok_or_else(|| ApiError::new(428, "revision_required", "If-Match is required."))?
            .trim_matches('"')
            .to_string();
        self.validate_mutation_support(configuration).await?;
        let stored = self.issue(configuration, identifier).await?;
        if stored.revision.trim_matches('"') != expected.trim_matches('"') {
            return Err(storage_error(StoreError::Conflict));
        }
        let issue: IssueData =
            serde_json::from_slice(&stored.bytes).map_err(|error| invalid(error.to_string()))?;
        self.mark_relations_deleted(configuration, identifier)
            .await?;
        if let Err(error) = self
            .ensure_no_live_references(configuration, identifier)
            .await
        {
            self.clear_relations_deleted(identifier).await;
            return Err(error);
        }
        let event = EventRecord::new(
            identifier,
            EventType::IssueDeleted,
            &request.principal.actor,
            issue_deleted_payload(&issue),
            now_timestamp(),
        );
        let deletion = DeleteMutation {
            path: issue_path(configuration, identifier)?,
            expected_revision: stored.revision.clone(),
            event_objects: vec![event_object(configuration, &event)?],
            operation_id: operation_id(request)?,
            request_hash: request_hash(request),
        };
        let result = match self.store.delete(&self.scope, &deletion).await {
            Ok(result) => result,
            Err(error) => {
                self.clear_relations_deleted(identifier).await;
                return Err(storage_error(error));
            }
        };
        self.remove_relations_record(identifier).await;
        Ok(json!({"deleted":true,"issue_id":identifier,"catalog_pending":result.repair_pending}))
    }

    async fn commit(
        &self,
        configuration: &ProjectConfiguration,
        raw: Value,
        condition: WriteCondition,
        operation_id: String,
        request_hash: String,
        events: Vec<EventRecord>,
    ) -> Result<Value, ApiError> {
        let identifier = raw["id"].as_str().unwrap();
        let event_objects = events
            .iter()
            .map(|event| event_object(configuration, event))
            .collect::<Result<Vec<_>, _>>()?;
        let mut fields = BTreeMap::new();
        for name in [
            "id",
            "type",
            "status",
            "priority",
            "assignee",
            "parent",
            "created_at",
            "updated_at",
        ] {
            if let Some(value) = raw.get(name) {
                fields.insert(name.to_string(), value.clone());
            }
        }
        let bytes = json_bytes(&raw);
        if bytes.len() > MAX_CANONICAL_OBJECT_BYTES {
            return Err(ReadBudget::default().exceeded("mutation_bytes"));
        }
        let mutation = Mutation {
            path: issue_path(configuration, identifier)?,
            condition,
            bytes,
            content_type: "application/json".into(),
            event_objects,
            operation_id,
            request_hash,
            fields,
        };
        let committed = self
            .store
            .commit(&self.scope, &mutation)
            .await
            .map_err(storage_error)?;
        let mut response = issue_response(&committed.stored)?;
        response["catalog_pending"] = json!(committed.repair_pending);
        Ok(response)
    }

    async fn events(
        &self,
        configuration: &ProjectConfiguration,
        identifier: &str,
    ) -> Result<Value, ApiError> {
        issue_path(configuration, identifier)?;
        let mut events = Vec::new();
        let mut budget = ReadBudget::default();
        for (_, object) in self
            .objects(
                &format!("{}/events/", configuration.project_directory),
                &mut budget,
            )
            .await?
        {
            let value: Value = serde_json::from_slice(&object.bytes)
                .map_err(|error| invalid(error.to_string()))?;
            if value["issue_id"].as_str() == Some(identifier) {
                events.push(value);
            }
        }
        events.sort_by(|a, b| {
            a["occurred_at"]
                .as_str()
                .cmp(&b["occurred_at"].as_str())
                .then_with(|| a["event_id"].as_str().cmp(&b["event_id"].as_str()))
        });
        if events.is_empty() {
            self.issue(configuration, identifier).await?;
        }
        Ok(json!({"issue_id":identifier,"events":events,"next_before":null,"cost":budget}))
    }
}

fn event_object(
    configuration: &ProjectConfiguration,
    event: &EventRecord,
) -> Result<EventObject, ApiError> {
    let bytes = json_bytes(event);
    if bytes.len() > MAX_CANONICAL_OBJECT_BYTES {
        return Err(ReadBudget::default().exceeded("event_bytes"));
    }
    Ok(EventObject {
        path: format!(
            "{}/events/{}",
            configuration.project_directory,
            event_filename(&event.occurred_at, &event.event_id)
        ),
        bytes,
        content_type: "application/json".into(),
    })
}

fn json_bytes(value: &impl Serialize) -> Vec<u8> {
    let mut bytes = serde_json::to_vec_pretty(value).expect("JSON data is serializable");
    bytes.push(b'\n');
    bytes
}

fn issue_response(stored: &StoredObject) -> Result<Value, ApiError> {
    let issue: Value =
        serde_json::from_slice(&stored.bytes).map_err(|error| invalid(error.to_string()))?;
    Ok(json!({"issue":issue,"revision":stored.revision}))
}

fn safe_relative_path(path: &str) -> Result<(), ApiError> {
    if path.is_empty()
        || path.split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || part.contains('\\')
                || part.contains(':')
        })
    {
        return Err(invalid("Project directory must be a safe relative path."));
    }
    Ok(())
}

fn issue_path(configuration: &ProjectConfiguration, identifier: &str) -> Result<String, ApiError> {
    validate_issue_identifier(identifier)?;
    Ok(format!(
        "{}/issues/{identifier}.json",
        configuration.project_directory
    ))
}

fn validate_issue_identifier(identifier: &str) -> Result<(), ApiError> {
    if identifier.is_empty()
        || matches!(identifier, "." | "..")
        || !identifier.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.')
        })
    {
        return Err(invalid("A full issue identifier is required."));
    }
    Ok(())
}

fn mutable_fields(body: &Value) -> Result<&Map<String, Value>, ApiError> {
    let fields = body
        .as_object()
        .ok_or_else(|| invalid("Expected a JSON object."))?;
    let allowed = [
        "title",
        "description",
        "type",
        "status",
        "priority",
        "assignee",
        "parent",
        "dependencies",
        "labels",
        "custom",
    ];
    if fields.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err(invalid("Request contains a protected or unknown field."));
    }
    Ok(fields)
}

const ALLOWED_DEPENDENCY_TYPES: [&str; 2] = ["blocked-by", "relates-to"];

fn validate_dependency_links(issue: &IssueData) -> Result<(), ApiError> {
    for link in &issue.dependencies {
        if !ALLOWED_DEPENDENCY_TYPES.contains(&link.dependency_type.as_str()) {
            return Err(invalid("Invalid dependency type."));
        }
        if link.target == issue.identifier {
            return Err(invalid("An issue cannot depend on itself."));
        }
        validate_issue_identifier(&link.target)?;
        if link.dependency_type == "blocked-by" && issue.parent.as_deref() == Some(&link.target) {
            return Err(invalid("An issue cannot be blocked by its parent."));
        }
    }
    Ok(())
}

fn operation_id(request: &ApiRequest) -> Result<String, ApiError> {
    let value = request
        .headers
        .get("x-operation-id")
        .ok_or_else(|| invalid("X-Operation-Id is required."))?;
    uuid::Uuid::parse_str(value).map_err(|_| invalid("X-Operation-Id must be a UUID."))?;
    Ok(value.clone())
}

#[derive(Serialize, Deserialize)]
struct Cursor {
    query: String,
    offset: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct FieldPredicate {
    field: String,
    operator: String,
    value: Value,
}

impl FieldPredicate {
    fn validate(&self) -> Result<(), ApiError> {
        if !self.field.starts_with("custom.")
            || self.field.split('.').any(|part| {
                part.is_empty()
                    || !part
                        .chars()
                        .all(|character| character.is_ascii_alphanumeric() || character == '_')
            })
        {
            return Err(invalid("Field paths must name custom scalar fields."));
        }
        if !["eq", "lt", "lte", "gt", "gte"].contains(&self.operator.as_str())
            || self.value.is_object()
            || self.value.is_array()
        {
            return Err(invalid("Invalid field predicate."));
        }
        Ok(())
    }
    fn matches(&self, raw: &Value) -> bool {
        let mut current = raw;
        for segment in self.field.split('.') {
            let Some(value) = current.get(segment) else {
                return false;
            };
            current = value;
        }
        if self.operator == "eq" {
            return if current.is_number() && self.value.is_number() {
                compare_numbers(current, &self.value) == Some(std::cmp::Ordering::Equal)
            } else {
                current == &self.value
            };
        }
        let ordering = match (current, &self.value) {
            (Value::String(a), Value::String(b)) => Some(a.cmp(b)),
            (Value::Number(_), Value::Number(_)) => compare_numbers(current, &self.value),
            _ => None,
        };
        ordering.is_some_and(|order| match self.operator.as_str() {
            "lt" => order.is_lt(),
            "lte" => order.is_le(),
            "gt" => order.is_gt(),
            "gte" => order.is_ge(),
            _ => false,
        })
    }
}

fn request_hash(request: &ApiRequest) -> String {
    format!("{:x}", Sha256::digest(json!({"method":request.method,"path":request.path,"body":request.body,"actor":request.principal.actor,"revision":request.headers.get("if-match")}).to_string().as_bytes()))
}

fn browser_configuration(
    configuration: &ProjectConfiguration,
    actor: &str,
) -> Result<Value, ApiError> {
    let serialized =
        serde_json::to_value(configuration).map_err(|error| invalid(error.to_string()))?;
    let mut safe = Map::new();
    for key in [
        "project_key",
        "project_directory",
        "name",
        "hierarchy",
        "types",
        "workflows",
        "transition_labels",
        "initial_status",
        "priorities",
        "default_priority",
        "assignee",
        "time_zone",
        "statuses",
        "categories",
        "sort_order",
        "type_colors",
    ] {
        if let Some(value) = serialized.get(key) {
            safe.insert(key.into(), value.clone());
        }
    }
    safe.insert("actor_id".into(), json!(actor));
    Ok(Value::Object(safe))
}
