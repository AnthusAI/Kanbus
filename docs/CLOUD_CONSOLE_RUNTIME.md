# Cloud Console Runtime

This document defines cloud runtime behavior for the Lambda-backed `kbsc` console API.

## Endpoints

Tenant-scoped API routes use:

- `/{account}/{project}/api/config`
- `/{account}/{project}/api/issues`
- `/{account}/{project}/api/issues/{id}`
- `/{account}/{project}/api/events`
- `/{account}/{project}/api/events/realtime`
- `/{account}/{project}/api/realtime/bootstrap`
- `/{account}/{project}/api/auth/bootstrap`
- `/api/auth/bootstrap`

## Realtime Bootstrap Contract

`GET /{account}/{project}/api/realtime/bootstrap`

Returns JSON:

- `mode`: realtime mode (`mqtt_iot`)
- `region`: AWS region used for IoT WebSocket signing
- `iot_endpoint`: AWS IoT data endpoint hostname
- `iot_wss_url`: MQTT-over-WSS URL derived from endpoint (`wss://<endpoint>/mqtt`)
- `topic`: tenant topic (`projects/{account}/{project}/events`)
- `account`: resolved account segment from route
- `project`: resolved project segment from route

Required environment variables:

- `KANBUS_IOT_DATA_ENDPOINT`
- `AWS_REGION` (or `AWS_DEFAULT_REGION`)

If required variables are missing, the endpoint returns `500` with an error payload.

## Auth Bootstrap Contract

`GET /{account}/{project}/api/auth/bootstrap` (tenant-scoped)
`GET /api/auth/bootstrap` (global/callback-safe)

Returns JSON with:

- `mode`: `none` (local) or `cognito_pkce` (cloud)
- `cognito_domain_url`
- `cognito_client_id`
- `cognito_redirect_uri`
- `cognito_logout_uri`
- `cognito_issuer`
- `identity_pool_id`
- `tenant_account_claim_key` and `tenant_project_claim_key`

Cloud mode requires tenant claim parity (`custom:account`, `custom:project`) for protected tenant routes.

## Tenant Model

Current cloud tenancy is route + claim scoped:

- Tenant identity comes from URL: `/{account}/{project}/...`
- Access is allowed only when Cognito claims match route:
  - `custom:account == {account}`
  - `custom:project == {project}`
- A user is currently single-tenant in one session because claims hold one account/project pair.

Practical implications:

- Root route (`/dev/`) has no tenant context and is not sufficient for data access.
- Use tenant route URLs directly, for example:
  - `/dev/anthus/kanbus/`

## How A Tenant Project Exists

There is no separate tenant registry yet. A tenant project exists when `<account>/<project>` is used and data is synced/written.

For Git-backed cloud projects:

1. Browser/API calls use tenant route `/{account}/{project}`.
2. Webhook ingress receives tenant headers:
   - `X-Kanbus-Account`
   - `X-Kanbus-Project`
3. Sync worker clones/syncs repo to EFS:
   - `/mnt/data/{account}/{project}/repo`
4. Console APIs read project data from EFS and publish realtime events to:
   - `projects/{account}/{project}/events`

## Multi-Tenant User Roadmap

Current v1 supports one tenant mapping per user (single `custom:account` + `custom:project`).

To support one user across many projects/accounts, add:

- tenant membership source (group mapping or membership table),
- `GET /api/tenants` discovery endpoint,
- explicit tenant switch UX in console,
- authorizer/API checks against membership set (not single claim pair).

## Operator Runbook (v1)

### Create a New Cloud Tenant Project

There is no tenant registry table in v1. A tenant project is created by syncing a repo
into the tenant path on EFS and then serving it from the tenant route.

1. Pick tenant coordinates: `<account>` and `<project>`.
2. Ensure webhook delivery includes:
   - `X-Kanbus-Account: <account>`
   - `X-Kanbus-Project: <project>`
3. Trigger a sync (GitHub push webhook or manual sync path) so worker materializes:
   - `/mnt/data/<account>/<project>/repo`
4. Open the tenant URL:
   - `/dev/<account>/<project>/`

If repo sync succeeds, the project exists operationally and APIs can serve data.

### Grant Browser Access (Cognito)

Browser auth is Cognito Hosted UI with tenant claim parity checks.

1. Create/update Cognito user attributes:
   - `custom:account=<account>`
   - `custom:project=<project>`
2. User signs in through Hosted UI.
3. API and realtime access is allowed only if route tenant matches claims.
4. Claim mismatch returns `403` for tenant-scoped API calls.

Current v1 constraint: one account/project pair per user session.

### Grant CLI MQTT Access (API Token + Custom Authorizer)

CLI auth is non-OAuth API token via IoT custom authorizer.

1. Admin user mints token:
   - `kbs cloud token create --base-url <api_base> --id-token <admin_id_token> --account <account> --project <project> --scopes subscribe --days 90`
2. For mutation clients that must publish, include publish scope:
   - `--scopes publish,subscribe`
3. Distribute token value securely (shown once at creation).
4. Revoke when needed:
   - `kbs cloud token revoke --base-url <api_base> --id-token <admin_id_token> --token-id <token_id>`

### Two-Mac MQTT Realtime Validation

Use this to verify shared cloud realtime between two machines and external consumers.

On both Macs:

```bash
export KANBUS_REALTIME_TRANSPORT=mqtt
export KANBUS_REALTIME_BROKER="mqtts://<iot-endpoint>:443"
export KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME="kanbus-mqtt-token-dev"
export KANBUS_REALTIME_MQTT_API_TOKEN="<tenant_token>"
```

Mac A (observer):

```bash
kbsc --host 0.0.0.0 --port 4242
# optional raw stream observer:
kbs gossip watch --print
```

Mac B (mutator):

```bash
kbs create "MQTT cross-mac test issue" --type task --parent <epic_id>
kbs update <issue_id> --status in_progress
kbs comment <issue_id> "cross-mac realtime validation"
```

Expected result:

- Mac A `kbsc` board updates without local UDS dependency on Mac B.
- Any watcher on same tenant topic receives matching `issue.mutated` events.
- If MQTT is unavailable but `kbs` and `kbsc` run on same host, local UDS path still carries updates.

## SSE Fallback Behavior

`/api/events/realtime` is currently a Lambda compatibility alias to `/api/events`.

Current fallback stream behavior:

- Initial snapshot is emitted immediately as SSE `data:` payload.
- Server checks for snapshot changes every 15 seconds.
- No-op intervals emit no update payloads.
- Connection uses standard SSE headers:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`

## Client Reconnect Guidance

For cloud clients:

- Attempt MQTT-over-WSS first using `/api/realtime/bootstrap`.
- If MQTT connect/subscribe fails, fall back to `/api/events/realtime` SSE.
- SSE fallback in cloud carries `access_token` query auth so browser `EventSource` can connect.
- Treat SSE as bounded and reconnect-safe.
- On `error`, allow browser/EventSource reconnect behavior to re-establish stream.

## Verification

Lambda route and realtime bootstrap tests live in:

- `rust/src/bin/console_lambda.rs`

Run:

```bash
cd rust
cargo test --bin console_lambda
```
