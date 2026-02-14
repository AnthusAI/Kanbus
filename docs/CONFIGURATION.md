# Kanbus Configuration (Python + Rust)

Kanbus uses a single configuration file to define project identity, hierarchy, workflows, and priorities. The same schema and behaviors apply to both implementations.

## Location

```
kanbus.yml
```

The file must exist; there is no fallback path. A missing file is a hard error with a clear message.

## Loading semantics (dotyaml parity)

1. Load `.env` (unless disabled), setting variables only when they are not already defined.
2. Parse `kanbus.yml`, interpolating `{{ VAR|default }}` expressions from the environment.
3. Flatten the resulting config into environment variables with the `KANBUS_` prefix (nested keys joined by underscores, lists as comma-separated strings, booleans as `true`/`false`, null as empty string).
4. Never override an environment variable that is already set unless `override=true` is explicitly requested.

These rules mirror the Python `dotyaml` package and must be matched in the Rust crate. citeturn0search3

## Schema (required fields)

```yaml
project_key: "KAN"              # 2–6 uppercase letters; used as issue prefix
hierarchy:                       # fixed; user must not change
  - initiative
  - epic
  - issue
  - subtask
issue_types:                     # non-hierarchical types
  - bug
  - story
  - chore
workflows:                       # state machines
  default:
    open: [in_progress, closed, deferred]
    in_progress: [open, blocked, closed]
    blocked: [in_progress, closed]
    closed: [open]
    deferred: [open, closed]
workflow_bindings:               # required; every type maps to a workflow
  bug: default
  story: default
  chore: default
initial_status: open             # must exist in the bound workflow
priorities:                      # canonical, ordered list (highest first)
  - critical
  - high
  - medium
  - low
  - trivial
default_priority: medium         # must be in priorities
priority_import_aliases:         # optional mapping from external → canonical
  P0: critical
  P1: high
  P2: medium
  P3: low
priority_accept_unmapped: true   # allow unmapped on import, block on create/update
data_dir: .kanbus              # optional; single location for caches
timezone: America/New_York       # optional; IANA tz
date_format: RFC3339             # optional; defaults to RFC3339
```

## Validation rules

- `project_key` is 2–6 uppercase letters; used as prefix for new IDs.
- `hierarchy` is fixed to `initiative > epic > issue > subtask`; config must fail if altered.
- Every `issue_type` must have a `workflow_binding`; no default fallback.
- All states referenced in workflows must be reachable; transitions are explicit only.
- `initial_status` must appear in the workflow bound to the issue type.
- `priorities` is an ordered list; `default_priority` must be one of them.
- Unknown top-level keys are errors (extra fields forbidden).
- Only one configuration file is read; no backward-compatible search paths.

## Priority handling behaviors

- **Import/read:** accept any priority string; flag as external when not in `priorities`.
- **Create/update:** must use canonical priorities; otherwise fail.
- **Transform/save (e.g., Beads import):** apply `priority_import_aliases`; if unmapped and `priority_accept_unmapped` is false, fail; if true, store the external label.

## Workflow behaviors

- Status transitions must follow the bound workflow; any transition not listed is rejected.
- Type-specific workflows override default by binding; absence of a binding is an error at load time.

## Environment integration

- Prefix for exported env vars is fixed to `KANBUS_`.
- `.env` loading is enabled by default; disable with a loader flag (CLI option to be defined in both implementations).
- `override=true` is an opt-in flag to let YAML values overwrite existing env vars; default is non-overriding. citeturn0search3

## Examples

### Default software project

```yaml
project_key: "KAN"
issue_types: [bug, story, chore]
workflow_bindings:
  bug: default
  story: default
  chore: default
initial_status: open
priorities: [critical, high, medium, low, trivial]
default_priority: medium
priority_import_aliases:
  P0: critical
  P1: high
  P2: medium
  P3: low
priority_accept_unmapped: true
```

### Beads import mapping

```yaml
project_key: "BDX"
issue_types: [bug, task]
workflow_bindings:
  bug: default
  task: default
priorities: [urgent, high, normal, low]
default_priority: normal
priority_import_aliases:
  P0: urgent
  P1: high
  P2: normal
  P3: low
priority_accept_unmapped: false
```
