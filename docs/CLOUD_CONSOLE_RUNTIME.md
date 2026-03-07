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
