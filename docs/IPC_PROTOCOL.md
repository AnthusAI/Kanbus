# IPC Protocol

This document defines the client-daemon protocol for Kanbus just-in-time indexing.
It is the shared contract that both Python and Rust implementations must enforce.

## Transport

- JSON over a local IPC socket
- UTF-8 encoded
- One JSON object per line (newline-delimited)

## Versioning

Protocol versions are `MAJOR.MINOR` (for example, `1.0`).

Compatibility rules:
- If the major version differs, the daemon must reject the request.
- If the major version matches and the client minor version is less than or equal to the daemon minor version, the request is accepted.
- If the major version matches and the client minor version is greater than the daemon minor version, the daemon must reject the request.

## Request Envelope

```json
{
  "protocol_version": "1.0",
  "request_id": "req-01",
  "action": "index.build",
  "payload": {
    "project_root": "/path/to/repo",
    "force_rebuild": false
  }
}
```

Fields:
- `protocol_version` (string, required): Client protocol version.
- `request_id` (string, required): Client-generated identifier for correlation.
- `action` (string, required): Operation identifier (for example, `index.build`).
- `payload` (object, required): Action-specific input.

## Response Envelope

```json
{
  "protocol_version": "1.0",
  "request_id": "req-01",
  "status": "ok",
  "result": {
    "index_version": "2026-02-11T00:00:00Z"
  }
}
```

Fields:
- `protocol_version` (string, required): Daemon protocol version.
- `request_id` (string, required): Echo of the request ID.
- `status` (string, required): `ok` or `error`.
- `result` (object, required on success): Action-specific output.
- `error` (object, required on error): Error description.

## Error Contract

```json
{
  "protocol_version": "1.0",
  "request_id": "req-01",
  "status": "error",
  "error": {
    "code": "protocol_version_mismatch",
    "message": "Client version 2.0 is not supported by daemon 1.0",
    "details": {
      "client_version": "2.0",
      "daemon_version": "1.0"
    }
  }
}
```

Required error fields:
- `code` (string): Machine-readable error code.
- `message` (string): Human-readable error summary.
- `details` (object): Structured context for debugging.

Standard error codes:
- `protocol_version_mismatch`
- `protocol_version_unsupported`
- `invalid_request`
- `unknown_action`
- `internal_error`

## Validation Rules

Both implementations must:
- Reject requests missing required fields.
- Enforce version compatibility rules.
- Echo `request_id` in all responses.
- Return a structured error response for all failures.
