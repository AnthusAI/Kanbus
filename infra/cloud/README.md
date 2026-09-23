# Kanbus Cloud Foundation (Python CDK)

This CDK app provisions the v1 cloud foundation for the Kanbus console backend:

- VPC with public and isolated subnets (no NAT Gateway)
- EFS for tenant data (`/mnt/data/{account}/{project}`)
- S3 sync tarball bucket with 7-day lifecycle (S3 bridge between git sync and EFS)
- Rust Lambda container runtime (`console_lambda`)
- Regional REST API Gateway proxying to Lambda
- Cognito User Pool + Identity Pool foundation
- Cognito Hosted UI PKCE bootstrap outputs for browser login UX
- API Gateway Cognito authorizer on proxy methods
- IoT IAM policy scaffolding for tenant-scoped topics via principal tags
- DynamoDB-backed MQTT API token registry
- IoT Core custom authorizer for CLI MQTT API-token auth
- GitHub webhook ingress Lambda (`/internal/webhooks/github/{account}/{project}`) + SQS + DLQ
- Git sync Lambda (non-VPC, GitHub clone/fetch, uploads tarball to S3)
- EFS writer Lambda (VPC-isolated, extracts S3 tarball to EFS, writes S3 completion marker)
- Sync notify Lambda (non-VPC, publishes IoT events from completion markers)
- Token admin Lambda API (`/api/tokens`) for create/list/revoke
- AWS IoT Data endpoint discovery output

## Prerequisites

- Python 3.11 in the `py311` conda env
- Node.js + CDK CLI (`npx cdk` is fine)
- AWS credentials for the target account/profile

## Install dependencies

```bash
cd infra/cloud
conda run -n py311 python -m pip install -r requirements.txt
```

## Synthesize

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk synth
```

## Deploy

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk deploy
```

## Useful context overrides

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk synth \
  -c stack_name=KanbusCloudFoundation \
  -c env_name=dev \
  -c account=123456789012 \
  -c region=us-east-1
```

## Disposable coordination integration stack

For full remote Python/Rust coordination tests, select the small isolated stack by name:

```bash
cd infra/cloud
npx cdk synth \
  -c stack_name=KanbusCoordinationIntegration \
  -c env_name=coordination-it
```

Deploy it to the test account with the `anthus` profile when ready:

```bash
AWS_PROFILE=anthus npx cdk deploy \
  -c stack_name=KanbusCoordinationIntegration \
  -c env_name=coordination-it
```

The stack contains Cognito (immutable `custom:account` and `custom:project` claims), a
Cognito-authorized REST API with direct DynamoDB lease operations and token-admin routes,
the MQTT token table and generated pepper, the two MQTT token Lambdas, and an IoT custom
authorizer. It does not create the console foundation's VPC, EFS, S3, queues, or console
runtime. `CoordinationLeaseApiBaseUrl` is the API stage root; clients append
`api/coordination/leases/{resource}`. `MqttTokenAuthorizerName` and
`IotDataEndpointAddress` provide the remaining MQTT connection settings.
The test workers must use the token's tenant-scoped topic
`projects/{account}/{project}/events`; the integration harness takes those two
scope values explicitly and configures that topic without writing credentials
to the fixture repository.

Harness outputs are `CoordinationLeaseApiBaseUrl` (API stage root), `UserPoolId`,
`UserPoolClientId`, `UserPoolIssuerUrl`, `IotDataEndpointAddress`,
`MqttTokenAuthorizerName`, `MqttTokenTableName`, and `CoordinationLeaseTableName`.

Lease methods read tenant scope only from Cognito `custom:account` and `custom:project`
claims. If either claim is missing or empty, the request template emits a deliberately
invalid DynamoDB request without a table name or key, so DynamoDB cannot read or mutate a
row; the integration response maps that guard path to HTTP 403 `tenant scope missing`.

All stack-owned stateful resources use `RemovalPolicy.DESTROY` where supported. When the
remote test run is complete, delete the isolated resources with the same context:

```bash
AWS_PROFILE=anthus npx cdk destroy \
  -c stack_name=KanbusCoordinationIntegration \
  -c env_name=coordination-it
```

CloudFormation deletes the disposable user pool and token/lease tables with the stack.
Secrets Manager may keep the deleted pepper in its recovery window before final erasure.

## Production coordination stack

The production-only coordination stack deploys the MQTT token registry/custom IoT
authorizer and hard mutex API without the console VPC, EFS, or S3 resources. Production
tables enable point-in-time recovery, and the user pool, tables, authorizer, and pepper
are retained if the stack is removed or replaced.

Synthesize and deploy it separately from the disposable integration stack:

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk synth \
  -c stack_name=KanbusCoordinationProduction \
  -c env_name=prod \
  -c account=335163751677 \
  -c region=us-east-1 \
  -a '/path/to/python app.py'

AWS_PROFILE=anthus npx cdk deploy KanbusCoordinationProduction \
  -c stack_name=KanbusCoordinationProduction \
  -c env_name=prod \
  -c account=335163751677 \
  -c region=us-east-1 \
  -a '/path/to/python app.py'
```

This stack has its own Cognito user pool and MQTT token registry. It does not reuse the
dev authorizer or token table. Record its outputs in the deployment secret manager; issue
router clients need the API base URL, user-pool IDs, IoT endpoint, authorizer name, and
tenant scope. Do not put MQTT or mutex credentials in the project configuration.

## Outputs

- `ApiBaseUrl`
- `UserPoolId`
- `UserPoolClientId`
- `UserPoolIssuerUrl`
- `IdentityPoolId`
- `UserPoolHostedUiBaseUrl`
- `IotDataEndpointAddress`
- `MqttTokenAuthorizerName`
- `MqttTokenTableName`
- `CoordinationLeaseApiBaseUrl`
- `CoordinationLeaseTableName`
- `TenantEfsFileSystemId`
- `TenantEfsAccessPointId`
- `TenantEfsMountPath`
- `TenantRootTemplate`
- `SyncQueueUrl`
- `SyncQueueArn`
- `SyncDlqArn`
- `SyncBucketName`
- `SyncBucketArn`

## Tenant isolation note

The authenticated identity role includes IoT subscribe/receive permissions scoped to:

- `projects/${aws:PrincipalTag/account}/${aws:PrincipalTag/project}/events`

This is intentional scaffolding for strict tenant isolation. In v1, your identity provider
mapping flow must set `account` and `project` principal tags for authenticated sessions.

Hosted UI + identity pool principal tag mapping now uses Cognito custom attributes:

- `custom:account`
- `custom:project`

Current limitation: one user currently maps to one tenant pair (`account` + `project`) per session.
Supporting one user across multiple tenants requires a membership-based authorization model
instead of single-value claim parity.

## Mutex lease API prototype

The stack exposes a hard mutex API at:

- POST {CoordinationLeaseApiBaseUrl}api/coordination/leases/{resource} to acquire
- PUT {CoordinationLeaseApiBaseUrl}api/coordination/leases/{resource} to renew
- DELETE {CoordinationLeaseApiBaseUrl}api/coordination/leases/{resource} to release
- GET {CoordinationLeaseApiBaseUrl}api/coordination/leases/{resource} to inspect

Every route uses the existing Cognito User Pool authorizer. Clients send the Cognito JWT as
Authorization: Bearer <token>; they do not need AWS account credentials. Tenant scope is
derived only from the trusted custom:account and custom:project authorizer claims. The
resource name comes from the path. The API rejects requests whose token lacks either tenant
claim and never accepts tenant scope in the request body.

The DynamoDB key encodes account and project into the partition key and the resource into the
sort key. Base64 encoding keeps the separator unambiguous. Lease rows contain owner,
claim_id, revision, claimed_at, expires_at, plus the tenant/resource values used by
the API. revision is copied exactly from the acquire request; the issue router owns its
logical monotonic revision/fencing protocol. claimed_at and expires_at are server-generated
Unix epoch seconds. DynamoDB TTL is enabled on expires_at itself, so cleanup is asynchronous;
the API checks expires_at against server request time synchronously on acquire, renew,
release, and inspect. Renew adds the requested duration to the currently stored expiration.

Request bodies are JSON and reject unknown fields:

    POST  {"owner":"router-a","claim_id":"claim-001","revision":7,"ttl_seconds":300}
    PUT   {"owner":"router-a","claim_id":"claim-001","extend_seconds":120}
    DELETE {"owner":"router-a","claim_id":"claim-001"}
    GET   no body

Acquire returns 201 and a normalized JSON lease object. A live contention returns 409
with {"error":"lease already held"}. Renew returns 200; release returns 204; inspect
returns 200 for a live lease. Renew and release return 403 with
{"error":"lease owner mismatch"} when a different owner or claim ID holds a live lease.
Missing or expired leases return 404 with {"error":"no live lease"} for renew, release,
and inspect. Lease responses contain resource, owner, claim_id, revision,
claimed_at, and expires_at; timestamps are numeric Unix epoch seconds for client
normalization to RFC3339.

The lease table stores only the current live row per tenant/resource. It does not write
Kanbus event history or retain claim/release records. API Gateway integrates directly with
DynamoDB UpdateItem, DeleteItem, and GetItem; no Lambda or AppSync function sits in the
lease request path. Its service role has only GetItem, UpdateItem, and DeleteItem on the
lease table.

For renew and release, API Gateway uses DynamoDB ReturnValuesOnConditionCheckFailure to
distinguish a live lease owned by another claimant (403) from a missing/expired row (404).
API Gateway response mapping overrides the status for an expired row found before
asynchronous TTL deletion. Requests use REST API VTL templates and require
Content-Type: application/json for body-bearing methods. The API Gateway request models
cap acquire and renewal durations at 86,400 seconds.

## Webhook sync note

Webhook ingress expects:

- `POST /internal/webhooks/github/{account}/{project}`
- `X-GitHub-Event: push`
- `X-Hub-Signature-256` HMAC header

Tenant coordinates come from the URL path only. GitHub cannot send custom Kanbus headers.

The stack provisions a Secrets Manager secret and passes its ARN to webhook ingress.
Rotate this secret and configure GitHub webhook delivery to use the same value.

Example payload URL for tenant `anthus/kanbus`:

- `{ApiBaseUrl}internal/webhooks/github/anthus/kanbus`

## How tenant projects are created in v1

There is no central tenant registry resource yet. A tenant project becomes active when the
tuple `<account>/<project>` is used and synced.

- Tenant route/API usage is `/{account}/{project}/...`.
- Webhook ingress uses path-scoped URL `/internal/webhooks/github/{account}/{project}`.
- Sync git Lambda clones/syncs the webhook repo URL into a tarball and uploads to S3:
  - `{account}/{project}/{sha}.tar.gz`
- EFS writer Lambda extracts the tarball to:
  - `/mnt/data/{account}/{project}/repo`

This means cloud project existence is currently operationally defined by EFS presence and sync history.

## Automated pre-acceptance validation

Use the cloud validation runner before human acceptance or UX review:

```bash
AWS_PROFILE=anthus \
KANBUS_TEST_ADMIN_USERNAME=<admin-user> \
KANBUS_TEST_ADMIN_PASSWORD=<admin-pass> \
KANBUS_TEST_TENANT_USERNAME=<tenant-user> \
KANBUS_TEST_TENANT_PASSWORD=<tenant-pass> \
KANBUS_TEST_MISMATCH_USERNAME=<mismatch-user> \
KANBUS_TEST_MISMATCH_PASSWORD=<mismatch-pass> \
scripts/cloud/validate_preacceptance.sh
```

Artifacts are written to:

- `artifacts/cloud-validation/<timestamp>/gate-*.log`
- `artifacts/cloud-validation/<timestamp>/responses/*`
- `artifacts/cloud-validation/<timestamp>/cloudwatch/*`
- `artifacts/cloud-validation/<timestamp>/summary.json`

The script enforces gates in order:

1. Environment/stack preflight.
2. Static/build checks.
3. Unauthenticated API/auth contracts.
4. Authenticated tenant isolation + SSE endpoint.
5. Token admin + authorizer + CLI parity.
6. Webhook -> SQS -> git sync Lambda -> S3 tarball -> EFS writer -> S3 marker -> sync notify -> IoT event.
7. Browser realtime hard gate (MQTT primary, no SSE-only pass).

## Cross-Mac realtime operator flow

Detailed runtime/auth/tenant operations are documented in:

- `docs/CLOUD_CONSOLE_RUNTIME.md` (Operator Runbook section)

That runbook includes:

- how a new `<account>/<project>` becomes active on EFS,
- Cognito claim mapping for browser access,
- CLI MQTT API-token lifecycle (create/list/revoke),
- exact two-Mac MQTT validation commands.
