# Lifecycle Hooks

Lifecycle hooks are a first-class Kanbus integration surface for running project-defined logic on command lifecycle boundaries.

The hook engine is implemented with behavior parity in Python and Rust CLIs.

## Core model

- `HookPhase`: `before` or `after`
- `HookEvent`: normalized lifecycle event name (see catalog below)
- `HookInvocation`: canonical JSON payload delivered to hooks
- `HookResult`: execution outcome metadata (success, timeout, exit code, duration, message)
- `HookHandler`: execution contract (external command handler in v1)

## Event catalog (v1)

Mutating operations:

- `issue.create`
- `issue.update`
- `issue.close`
- `issue.delete`
- `issue.comment`
- `issue.dependency`
- `issue.promote`
- `issue.localize`

Read operations:

- `issue.show`
- `issue.list`
- `issue.ready`

## Runtime semantics

- Hooks run at CLI lifecycle boundaries in both native and Beads compatibility modes.
- Before-hooks on mutating operations are fail-closed by default.
- After-hooks are non-blocking observers.
- External hooks receive JSON payload via `stdin`.
- Per-hook controls: `blocking`, `timeout_ms`, `cwd`, and `env`.

Global disable controls:

- CLI flag: `--no-hooks`
- Environment variable: `KANBUS_NO_HOOKS=1`

## Configuration (`.kanbus.yml`)

```yaml
hooks:
  enabled: true
  run_in_beads_mode: true
  default_timeout_ms: 5000
  before:
    issue.update:
      - id: validate-update
        command: ["./hooks/validate-update.sh"]
        timeout_ms: 1200
  after:
    issue.create:
      - id: notify-created
        command: ["./hooks/notify-created.sh"]
        env:
          WEBHOOK_URL: "https://example.invalid/hooks"
```

Hook entry fields:

- `id` (required)
- `command` (required argv list)
- `blocking` (optional)
- `timeout_ms` (optional)
- `cwd` (optional)
- `env` (optional map of string->string)

Validation checks:

- unknown events are rejected
- empty event hook lists are rejected
- duplicate hook IDs are rejected per phase/event
- command and `cwd` paths are validated by `kbs hooks validate`

## Invocation payload contract

All hooks receive a stable envelope:

```json
{
  "schema_version": "kanbus.hooks.v1",
  "phase": "after",
  "event": "issue.create",
  "timestamp": "2026-03-08T16:31:44.021Z",
  "actor": "dev@example.com",
  "mode": {
    "beads_mode": false,
    "project_root": "/repo",
    "working_directory": "/repo",
    "runtime": "python|rust"
  },
  "operation": {}
}
```

`operation` includes event-specific context (identifiers, filters, before/after issue snapshots when available).

## Policy guidance alignment

Policy guidance now runs through the lifecycle hook engine as a built-in provider.

- Preserves existing policy DSL and guidance semantics.
- Fires on post-operation events where policy guidance already applied (`create`, `update`, `close`, `delete`, `show`, `list`, `ready`).
- `--no-guidance` and `KANBUS_NO_GUIDANCE` suppress policy guidance only.
- External project hooks remain active unless hooks are globally disabled.

## CLI operations

```bash
# inspect lifecycle hooks
kbs hooks list

# validate configuration and executable paths
kbs hooks validate

# disable all hooks for one command
kbs --no-hooks list

# disable all hooks for a shell session
KANBUS_NO_HOOKS=1 kbs list
```
