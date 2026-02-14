# Configuration Reference

Taskulus projects are configured via `taskulus.yml`. This file defines the issue hierarchy, types, workflows, and default values used by the CLI and validators.

## File location

```
taskulus.yml
```

## Full schema

```yaml
# Project identity
prefix: "tsk"

# Issue type hierarchy (strict ordering, top to bottom)
hierarchy:
  - initiative
  - epic
  - task
  - sub-task

# Non-hierarchical types (cannot have children)
types:
  - bug
  - story
  - chore

# Workflow state machines (per type, with default fallback)
workflows:
  default:
    open: [in_progress, closed, deferred]
    in_progress: [open, blocked, closed]
    blocked: [in_progress, closed]
    closed: [open]
    deferred: [open, closed]
  epic:
    open: [in_progress, closed]
    in_progress: [open, closed]
    closed: [open]

# Initial status for new issues
initial_status: open

# Priority levels (0 = highest)
priorities:
  0: critical
  1: high
  2: medium
  3: low
  4: trivial

# Default priority for new issues
default_priority: 2

# Enable Beads compatibility mode by default
beads_compatibility: false
```

## Field reference

### `prefix` (string, required)

Prefix for issue IDs. Each ID is `prefix-<6hex>`.

### `hierarchy` (list of strings, required)

Defines a strict parent-child ordering. Parents can only have children of the next type in the list. The last type cannot have children.

### `types` (list of strings, required)

Non-hierarchical types. These may have a hierarchical parent, but cannot have children.

### `workflows` (map of workflow definitions, required)

Defines allowed status transitions per issue type. `default` is required and used as a fallback when a type-specific workflow is not present.

### `initial_status` (string, required)

Status assigned to newly created issues.

### `priorities` (map of integer to string, required)

Human-readable names for priority levels. Lower numbers indicate higher priority.

### `default_priority` (integer, required)

Priority assigned to new issues when not explicitly provided.

### `beads_compatibility` (boolean, optional)

Whether CLI commands default to Beads compatibility mode when `--beads` is not provided.
Defaults to `false`.

## Validation rules

- `hierarchy` must be non-empty.
- `types` must not overlap with `hierarchy`.
- `workflows.default` must exist.
- `initial_status` must exist in the workflow for the issue type (or default).
- `default_priority` must be a key in `priorities`.
- No duplicate type names across `hierarchy` and `types`.

## Examples

### Software team workflow

```yaml
prefix: "tsk"
hierarchy:
  - initiative
  - epic
  - task
  - sub-task
types:
  - bug
  - story
  - chore
workflows:
  default:
    open: [in_progress, closed, deferred]
    in_progress: [open, blocked, closed]
    blocked: [in_progress, closed]
    closed: [open]
    deferred: [open, closed]
initial_status: open
priorities:
  0: critical
  1: high
  2: medium
  3: low
  4: trivial
default_priority: 2
```

### Customer support queue

```yaml
prefix: "sup"
hierarchy:
  - queue
  - ticket
types:
  - bug
workflows:
  default:
    new: [triaged, closed]
    triaged: [in_progress, closed]
    in_progress: [waiting_on_customer, closed]
    waiting_on_customer: [in_progress, closed]
    closed: [new]
initial_status: new
priorities:
  0: urgent
  1: high
  2: normal
  3: low
default_priority: 2
```

### Content production pipeline

```yaml
prefix: "cnt"
hierarchy:
  - initiative
  - campaign
  - asset
types:
  - request
workflows:
  default:
    planned: [drafting, canceled]
    drafting: [review, canceled]
    review: [approved, changes_requested]
    changes_requested: [drafting, canceled]
    approved: [published]
    published: [archived]
    canceled: []
    archived: []
initial_status: planned
priorities:
  0: highest
  1: high
  2: normal
  3: low
default_priority: 2
```
