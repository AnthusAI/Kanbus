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
