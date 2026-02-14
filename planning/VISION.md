# Taskulus: Vision & Specification

## What Is This?

Taskulus is a git-backed project management system that stores all data as plain files in a repository. It replaces external tools like Jira and Confluence with two integrated subsystems:

1. **Issue Tracker** - Individual JSON files per issue, with configurable types, strict hierarchy, workflow state machines, and cross-issue dependencies
2. **Wiki** - Markdown files with Jinja2 template interpolation that query live issue data, providing narrative context ("the forest") around individual tasks ("the trees")

Both are accessed through a single CLI tool: `tsk`.

## Why Does This Exist?

This project was inspired by [Beads](https://github.com/steveyegge/beads), a git-backed issue tracker written in Go. Beads validates the core idea (issues versioned alongside code), but its implementation has significant complexity problems:

- **JSONL format**: All issues in one file leads to merge conflicts when multiple branches touch different issues
- **SQLite indexing server**: A daemon process with RPC, auto-sync, auto-import, and 42 migration files just to keep a cache in sync with the source files
- **Schema bloat**: 130+ fields per issue, far beyond what most projects need

Taskulus simplifies radically:

| Problem in Beads | Taskulus Solution |
|-----------------|-------------------|
| JSONL merge conflicts | One JSON file per issue |
| SQLite + daemon + RPC | In-memory index, scan files on startup |
| Hidden `.beads/` directory | Visible `project/` directory, human-browsable |
| 130+ fields | ~15 core fields + open `custom` map |
| Go-only implementation | Python + Rust, sharing identical behavior specs |
| No planning documents | Jinja2-powered wiki for live planning docs |

## Core Design Principles

1. **Files are the database.** There is no separate storage layer. The JSON files in `project/issues/` are the source of truth. We index them into memory on demand.
2. **Human-readable by default.** The `project/` directory is visible (not hidden), uses pretty-printed JSON, and can be browsed in any file explorer or text editor.
3. **Minimal required schema, open extensibility.** A small set of canonical fields that every issue has, plus a `custom` map where any project can store whatever it needs.
4. **Two implementations, one spec.** Python for easy installation in Python environments (`pip install taskulus`). Rust for maximum performance (`cargo install taskulus`). Both pass the same shared behavior test suite and read/write the same files.
5. **The spec is the artifact.** Neither implementation is primary. The shared behavior specifications are the source of truth. Both implementations are first-class.

---

## Project Directory Structure

When a user runs `tsk init` in their repository, this is created:

```
project/                          # Visible, human-browsable. Name configurable.
  taskulus.yml                    # Types, workflows, hierarchy, project settings
  issues/                         # One JSON file per issue
    tsk-a1b2c3.json
    tsk-d4e5f6.json
  wiki/                           # Jinja2 markdown templates
    index.md                      # Wiki entry point
  .cache/                         # Gitignored. Shared index cache.
    index.json

.taskulus.yml                    # Repo root marker (points to project directory)
```

The `.taskulus.yml` root marker allows the CLI to find the project directory from any subdirectory:

```yaml
project_directory: project
```

The directory name is configurable via `tsk init --dir <name>`.

---

## Configuration

**File:** `taskulus.yml`

```yaml
# Project identity
prefix: "tsk"                     # ID prefix for issues: tsk-a1b2c3

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
```

### Hierarchy Rules (Strict Enforcement)

The `hierarchy` list defines a strict parent-child ordering. This is enforced, not advisory.

| Parent Type | Allowed Child Types |
|-------------|-------------------|
| initiative | epic |
| epic | task |
| task | sub-task |
| sub-task | *(none - cannot have children)* |

Additional rules:
- Non-hierarchical types (`bug`, `story`, `chore`) may have a parent of any hierarchical type, but cannot themselves have children
- Issues without a parent can be any type (standalone tasks are valid)
- Reparenting validates the new relationship against these rules

### Workflow State Machines

Each issue type can have its own workflow, or fall back to `default`. A workflow is a directed graph where keys are statuses and values are lists of statuses you can transition to from that state.

For example, in the default workflow above:
- From `open` you can go to `in_progress`, `closed`, or `deferred`
- From `open` you CANNOT go directly to `blocked` (that's an invalid transition)
- From `closed` you can only go to `open` (reopen)

The CLI validates every status transition against the workflow before writing.

---

## Issue Data Model

**File:** `project/issues/{id}.json` (pretty-printed, 2-space indent)

```json
{
  "id": "tsk-a1b2c3",
  "title": "Implement OAuth2 authorization flow",
  "description": "Markdown description.\n\nCan be multi-line.",
  "type": "task",
  "status": "open",
  "priority": 2,
  "assignee": null,
  "creator": "ryan@example.com",
  "parent": "tsk-d4e5f6",
  "labels": ["auth", "backend"],
  "dependencies": [
    {"target": "tsk-g7h8i9", "type": "blocked-by"},
    {"target": "tsk-j0k1l2", "type": "relates-to"}
  ],
  "comments": [
    {
      "author": "ryan@example.com",
      "text": "Investigating OAuth library options.",
      "created_at": "2025-02-10T14:30:00Z"
    }
  ],
  "created_at": "2025-02-10T12:00:00Z",
  "updated_at": "2025-02-10T14:30:00Z",
  "closed_at": null,
  "custom": {}
}
```

### Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | yes | generated | `{prefix}-{6 hex chars}` |
| `title` | string | yes | - | Short summary |
| `description` | string | no | `""` | Markdown body |
| `type` | string | yes | `"task"` | Must be in `hierarchy` or `types` list from config |
| `status` | string | yes | from config `initial_status` | Must be valid in the issue's workflow |
| `priority` | int | yes | from config `default_priority` | 0-4, lower number = higher priority |
| `assignee` | string | no | `null` | Free-form identifier (email, username, etc.) |
| `creator` | string | no | `null` | Who created the issue |
| `parent` | string | no | `null` | ID of parent issue (hierarchy strictly enforced) |
| `labels` | string[] | no | `[]` | Freeform tags for categorization |
| `dependencies` | Dependency[] | no | `[]` | Outbound dependency links (see Dependencies section) |
| `comments` | Comment[] | no | `[]` | Flat list, ordered by `created_at` |
| `created_at` | ISO 8601 UTC | yes | current time | Set on creation, never changes |
| `updated_at` | ISO 8601 UTC | yes | current time | Updated on any mutation |
| `closed_at` | ISO 8601 UTC | no | `null` | Set when status becomes `closed`, cleared on reopen |
| `custom` | object | no | `{}` | Arbitrary key-value pairs for project-specific fields |

### ID Generation

1. Compute SHA256 of: `title + ISO 8601 timestamp + 8 cryptographically random bytes`
2. Take first 6 hex characters of the hash
3. Prefix with the project's configured prefix: `tsk-a1b2c3`
4. Check for collision against existing files in `project/issues/`; regenerate with new random bytes if collision occurs
5. 6 hex characters = 16.7 million possibilities, sufficient for any single project

### Why JSON, Not YAML

JSON was chosen over YAML for issue files because:
- No implicit type coercion (YAML turns `NO` into `false`, `1.0` into a float, etc.)
- Safer for machine-written data (issues are primarily written by the CLI, not hand-edited)
- Pretty-printed JSON with 2-space indent is readable enough for human inspection
- Both Python and Rust have fast, reliable JSON parsers with no edge cases

---

## Dependencies

### Dependency Types

| Type | Meaning | Workflow Impact |
|------|---------|-----------------|
| `blocked-by` | This issue cannot proceed until the target issue is closed | Determines which issues are "ready" |
| `relates-to` | Informational link between related issues | No workflow impact |

### Storage Convention

Dependencies are stored as **outbound references** on the dependent issue. Only one direction is stored on disk. The in-memory index computes reverse links at scan time.

Example: If issue `tsk-a1b2c3` contains `{"target": "tsk-g7h8i9", "type": "blocked-by"}`, then:
- On disk: `tsk-a1b2c3.json` records that it is blocked by `tsk-g7h8i9`
- In the index: `tsk-g7h8i9` is computed to **block** `tsk-a1b2c3`

This avoids redundant storage and the possibility of the two directions getting out of sync.

### Cycle Detection

Adding a `blocked-by` dependency must not create a cycle in the blocked-by directed graph. The CLI performs cycle detection (DFS/BFS on the blocked-by graph) before writing. Example: if A is blocked-by B and B is blocked-by C, adding C blocked-by A is rejected with an error.

### The "Ready" Query

An issue is **ready** when ALL of the following are true:
1. Its status is `open`
2. None of its `blocked-by` targets have a status other than `closed`

This is one of the most important queries in the system. It answers: "What can I work on next?"

---

## Workflow State Machine

### Transition Validation

Every status change is validated:
1. Look up the workflow for the issue's `type` in `taskulus.yml`
2. If no type-specific workflow exists, use the `default` workflow
3. Verify the new status appears in the allowed transitions list for the current status
4. If not allowed, reject with error: `"invalid transition from '{current}' to '{new}' for type '{type}'"`

### Automatic Side Effects

| Transition | Side Effect |
|-----------|-------------|
| Any status -> `closed` | Set `closed_at` to current UTC timestamp |
| `closed` -> any status | Clear `closed_at` to `null` |
| `--claim` flag on update | Atomically set `assignee` to current user AND transition status to `in_progress` |

### Validation on Every Write

Every time an issue file is written (create, update, close, dep add, etc.), the following are validated:
- Status is valid in the issue's workflow
- Parent-child hierarchy is valid per the strict rules
- No cycles exist in the blocked-by dependency graph
- All referenced issue IDs (parent, dependency targets) correspond to existing issue files

---

## Wiki System

### The Problem It Solves

An issue tracker gives you individual tasks (trees), but no way to see the big picture (forest). Planning documents go stale because updating them is manual effort separate from updating issue status. Agents working from a task list lack strategic context about why tasks exist, how workstreams relate, and what to prioritize when things conflict.

The wiki solves this by embedding live issue data into human-written narrative documents. The narrative (strategy, context, rationale) is written by humans and stays stable. The data (issue counts, status tables, blocked items) updates automatically because it's queried from the issue files at render time.

### How It Works

Wiki files in `project/wiki/` are Markdown files containing Jinja2 template syntax. The `tsk wiki render <page>` command:
1. Loads the in-memory issue index
2. Passes it as template context to the Jinja2 engine
3. Renders the template, replacing `{{ }}` expressions and `{% %}` blocks with live data
4. Outputs the resulting Markdown

### Template Engines

| Implementation | Library | Notes |
|----------------|---------|-------|
| Python | Jinja2 | The original, native Python library |
| Rust | MiniJinja | Created by Armin Ronacher, the same person who created Jinja2. Designed for syntax compatibility. |

Both support the same core syntax: `{{ expr }}`, `{% for %}`, `{% if %}`, filters, etc.

### Template Context Functions

These functions are available in all wiki templates:

#### `query(**filters)` -> list of issues

Returns issues matching all provided filters (AND logic).

```jinja2
{% for issue in query(type="task", status="open", sort="priority") %}
- **[{{ issue.id }}]** {{ issue.title }} (P{{ issue.priority }})
{% endfor %}
```

**Filter parameters** (all optional):
- `type` - exact match on issue type
- `status` - exact match on status
- `priority` - exact match on priority (int)
- `priority_lte` - priority <= value
- `priority_gte` - priority >= value
- `assignee` - exact match on assignee
- `label` - issue has this label
- `parent` - exact match on parent issue ID
- `sort` - field name to sort by; prefix with `-` for descending (e.g., `"-updated_at"`)
- `limit` - maximum number of results (int)

#### `count(**filters)` -> int

Same filters as `query()`, returns the count instead of the list.

```jinja2
There are {{ count(status="open", type="bug") }} open bugs.
```

#### `issue(id)` -> issue or None

Fetch a single issue by its ID.

```jinja2
{% set epic = issue("tsk-d4e5f6") %}
## {{ epic.title }}
{{ count(parent=epic.id, status="closed") }}/{{ count(parent=epic.id) }} tasks complete
```

#### `children(id)` -> list of issues

Returns all direct children of an issue (issues whose `parent` field matches the given ID).

#### `blocked_by(id)` -> list of issues

Returns all issues that are blocking the given issue (the targets of its `blocked-by` dependencies).

#### `blocks(id)` -> list of issues

Returns all issues that the given issue blocks (computed from reverse dependency index).

### Example Wiki Page

```markdown
# Q1 Sprint Plan

## Strategy
We're prioritizing reliability over new features this quarter.
See [reliability initiative](reliability.md) for the full rationale.

## Active Work
{% for issue in query(status="in_progress", sort="priority") %}
- **[{{ issue.id }}]** {{ issue.title }} (P{{ issue.priority }}{% if issue.assignee %}, {{ issue.assignee }}{% endif %})
{% endfor %}

## Blocked
{% for issue in query(status="blocked") %}
- **[{{ issue.id }}]** {{ issue.title }} -- blocked by: {% for b in blocked_by(issue.id) %}[{{ b.id }}] {% endfor %}
{% endfor %}

## Summary
| Status | Count |
|--------|-------|
| Open | {{ count(status="open") }} |
| In Progress | {{ count(status="in_progress") }} |
| Blocked | {{ count(status="blocked") }} |
| Closed | {{ count(status="closed") }} |
```

### Agent Workflow Integration

The intended workflow for AI agents:
1. Human writes planning wiki pages with strategic context + dynamic issue queries
2. Human references wiki pages in `AGENTS.md`: "Run `tsk wiki render project/wiki/sprint-plan.md` to understand current priorities before starting work"
3. Agent runs the render command and receives a fully interpolated briefing document
4. Agent understands not just what tasks exist, but why they exist and how they relate

### Cross-Linking

Wiki pages can link to:
- Other wiki pages: `[page title](other-page.md)` (standard Markdown links)
- Issues: `[tsk-a1b2c3]` (the render command can optionally resolve these to include the issue title)

---

## Index & Cache

### In-Memory Index

On every CLI invocation, the index is built (or loaded from cache):

1. Read all `project/issues/*.json` files
2. Parse each into an Issue struct/object
3. Build lookup maps:
   - `by_id`: ID -> Issue (hash map)
   - `by_status`: status string -> list of Issues
   - `by_type`: type string -> list of Issues
   - `by_parent`: parent ID -> list of child Issues
   - `by_label`: label string -> list of Issues
   - `reverse_deps`: target ID -> list of (source ID, reverse type) pairs
4. Validate referential integrity: no dangling parent references, no dangling dependency targets, no hierarchy violations

### Cache File

**File:** `project/.cache/index.json` (must be gitignored)

```json
{
  "version": 1,
  "built_at": "2025-02-10T12:00:00Z",
  "file_mtimes": {
    "tsk-a1b2c3.json": 1707567600.123,
    "tsk-d4e5f6.json": 1707567601.456
  },
  "issues": [ ... ],
  "reverse_deps": { ... }
}
```

### Cache Invalidation Logic

```
1. Does the cache file exist?
   NO  -> full rebuild, write cache
   YES -> continue

2. readdir + stat all files in project/issues/

3. Does the file list AND all mtimes match the cache?
   YES -> load index from cache (fast path, sub-millisecond)
   NO  -> full rebuild, write cache
```

### Local Indexing Daemon (Optional)

Taskulus may run a local resident daemon to keep an in-memory index warm between CLI invocations.
The daemon is an optimization only; JSON issue files remain the source of truth.

Daemon lifecycle:
- The daemon starts on-demand (first CLI call that elects to use it) and exits when idle.
- The daemon owns no authoritative state; it can be restarted at any time without data loss.

Daemon availability behavior (explicit):
- If a local daemon is running, the CLI requests the index via IPC.
- If the daemon is unavailable, the CLI performs a direct on-disk scan and proceeds normally.
- This is intentional product behavior, not a fallback to a secondary data source.

### Performance Characteristics

- **Cold start (no cache, 1000 issues):** ~10-50ms on SSD (readdir + open/read/close each file + JSON parse)
- **Warm start (valid cache):** sub-millisecond (one readdir + stats + one cache file read)
- **The cache format is shared between Python and Rust.** Either implementation can read a cache file written by the other.

No compaction: closed issues remain as files indefinitely. The cache keeps queries fast regardless of issue count.

---

## CLI Interface

### Command Reference

```
SETUP
  tsk init [--dir <name>]              Initialize project/ structure in current repo

ISSUE CRUD
  tsk create <title> [options]         Create a new issue
  tsk show <id>                        Show issue details, deps, and comments
  tsk update <id> [options]            Update issue fields
  tsk close <id> [--comment <text>]    Close an issue (shortcut for --status closed)
  tsk delete <id>                      Delete issue (removes the file)

QUERIES
  tsk list [filters]                   List issues with optional filters
  tsk ready                            List open issues with no open blockers
  tsk blocked                          List issues in blocked status
  tsk search <text>                    Full-text search across titles and descriptions

DEPENDENCIES
  tsk dep add <id> --blocked-by <tid>  Add a blocked-by dependency
  tsk dep add <id> --relates-to <tid>  Add a relates-to dependency
  tsk dep remove <id> <target-id>      Remove a dependency
  tsk dep tree <id>                    Display the dependency tree for an issue

COMMENTS
  tsk comment <id> <text>              Add a comment to an issue

WIKI
  tsk wiki render <page>               Render a wiki page with live interpolated data
  tsk wiki list                        List all wiki pages

MAINTENANCE
  tsk validate                         Check all issues for integrity errors
  tsk stats                            Display project overview statistics
```

### `tsk create` Options

```
--type <type>           Issue type (default: task)
--priority <0-4>        Priority (default: from config default_priority)
--assignee <name>       Assign to someone
--parent <id>           Set parent issue (hierarchy validated)
--label <label>         Add a label (can be repeated)
--blocked-by <id>       Add a blocked-by dependency (can be repeated)
--description <text>    Set description body (use - to read from stdin)
```

### `tsk update` Options

```
--status <status>       Transition status (validated against workflow)
--priority <0-4>        Change priority
--assignee <name>       Change assignee
--claim                 Atomic: set assignee to current user + status to in_progress
--title <text>          Change title
--add-label <label>     Add a label
--remove-label <label>  Remove a label
```

### `tsk list` Filters

```
--type <type>           Filter by issue type
--status <status>       Filter by status
--priority <n>          Filter by exact priority
--assignee <name>       Filter by assignee
--label <label>         Filter by label
--parent <id>           Filter by parent issue
--sort <field>          Sort by field (prefix - for descending)
--limit <n>             Limit number of results
```

### Output Formats

All commands support `--json` for structured JSON output, intended for agent consumption. The default output is human-readable formatted text.

---

## Behavior Specifications

### Philosophy

The shared behavior spec suite is the **single source of truth** for what Taskulus does. It is not a test suite for one implementation that the other copies -- it is the contract that both implementations independently fulfill.

### Test Case Structure

Each test case is a directory containing a YAML definition and input files:

```
specs/
  test-cases/
    issue-crud/
      create-basic/
        test.yaml                     # Test definition
        input/                        # Initial state
          config.yaml
      create-with-parent/
        test.yaml
        input/
          config.yaml
          issues/
            tsk-parent.json
    workflow/
      valid-transition/
        test.yaml
        input/
          config.yaml
          issues/
            tsk-test01.json           # An issue in "open" status
      invalid-transition/
        test.yaml
        input/
          config.yaml
          issues/
            tsk-test01.json
    dependencies/
      blocked-by-basic/
        ...
      cycle-detection/
        ...
      ready-query/
        ...
    hierarchy/
      valid-parent-child/
        ...
      invalid-parent-child/
        ...
    wiki/
      render-query/
        test.yaml
        input/
          config.yaml
          issues/
            tsk-task1.json
            tsk-task2.json
          wiki/
            test.md
```

### test.yaml Format

```yaml
# A test that expects success
description: "Creating a basic task assigns correct default values"
command: ["create", "New Task", "--type", "task"]
expect:
  exit_code: 0
  stdout_contains: ["tsk-"]
  issues_created: 1
  created_issue:
    title: "New Task"
    type: "task"
    status: "open"
    priority: 2
```

```yaml
# A test that expects failure
description: "Cannot transition from open directly to blocked"
command: ["update", "tsk-test01", "--status", "blocked"]
expect:
  exit_code: 1
  stderr_contains: ["invalid transition"]
  issue:
    id: "tsk-test01"
    status: "open"              # Unchanged
```

### Test Runner Contract

Each implementation provides a spec runner that:
1. Creates a temporary directory
2. Copies the test case's `input/` files into the correct project structure
3. Executes the specified command against that project
4. Asserts: exit code, stdout/stderr content, and resulting issue file states
5. Reports pass/fail per test case

---

## Repository Layout

```
Taskulus/
  planning/                           # This directory - vision and planning docs
    VISION.md                         # This document
  specs/                              # Shared behavior specifications
    test-cases/                       # Test case directories (see above)
    fixtures/                         # Reusable input fixtures
  python/                             # Python implementation
    src/
      taskulus/
        __init__.py
        cli.py                        # CLI entry point (Click)
        models.py                     # Dataclasses: Issue, Config, Dependency, Comment
        index.py                      # In-memory index builder + cache read/write
        wiki.py                       # Jinja2 wiki rendering
        workflows.py                  # State machine transition validation
        ids.py                        # Hash-based ID generation
    tests/
      test_spec_runner.py             # Runs the shared behavior specs
      test_*.py                       # Python-specific unit tests
    pyproject.toml
  rust/                               # Rust implementation
    src/
      main.rs
      cli.rs                          # CLI entry point (Clap)
      models.rs                       # Structs: Issue, Config, Dependency, Comment
      index.rs                        # In-memory index builder + cache read/write
      wiki.rs                         # MiniJinja wiki rendering
      workflows.rs                    # State machine transition validation
      ids.rs                          # Hash-based ID generation
    tests/
      spec_runner.rs                  # Runs the shared behavior specs
    Cargo.toml
  README.md
```

### Key Library Choices

| Component | Python | Rust |
|-----------|--------|------|
| CLI framework | Click | Clap |
| JSON parsing | stdlib `json` | serde + serde_json |
| YAML parsing | PyYAML or ruamel.yaml | serde_yaml |
| Template engine | Jinja2 | MiniJinja |
| Hashing | stdlib `hashlib` | sha2 crate |
| Testing | behave | cargo test |

---

## Implementation Phases

### Phase 1: Foundation (both implementations in parallel)

1. Repository setup: directory structure, pyproject.toml, Cargo.toml, shared specs directory
2. Data model: Issue, Config, Dependency, Comment types with JSON serialization/deserialization
3. ID generation: SHA256-based with collision detection
4. File I/O: read/write pretty-printed JSON issue files, read YAML config
5. Index: scan `project/issues/`, build in-memory lookups, cache read/write with mtime invalidation
6. Workflow: state machine transition validation against config
7. Hierarchy: strict parent-child type validation
8. Dependencies: add/remove `blocked-by` and `relates-to`, cycle detection in blocked-by graph
9. CLI commands: `init`, `create`, `show`, `update`, `close`, `delete`, `list`, `ready`, `blocked`, `dep add`, `dep remove`, `dep tree`, `comment`
10. Behavior specs: test cases covering all of the above

### Phase 2: Wiki

11. Wiki rendering engine using Jinja2 (Python) / MiniJinja (Rust)
12. Template context functions: `query`, `count`, `issue`, `children`, `blocked_by`, `blocks`
13. CLI commands: `wiki render`, `wiki list`
14. Behavior specs: wiki rendering test cases

### Phase 3: Polish

15. Full-text search: `tsk search` across titles and descriptions
16. Validation: `tsk validate` for comprehensive integrity checking
17. Statistics: `tsk stats` for project overview
18. VS Code extension: live wiki preview with interpolated data in the editor

---

## Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Issue file format | JSON (pretty-printed) | No implicit typing gotchas (YAML turns `NO` into `false`), machine-safe, readable when pretty-printed |
| One file per issue | Yes | Merge conflicts only happen when two branches modify the same issue, which is a real conflict |
| Project directory | `project/` (visible, not hidden) | Human-browsable, not hidden infrastructure. Name is configurable. |
| Hierarchy enforcement | Strict | Initiative > Epic > Task > Sub-Task. Prevents misuse. Non-hierarchical types are separate. |
| CLI command name | `tsk` | Short, evokes "task", unlikely to conflict with existing tools |
| Wiki template syntax | Jinja2 | Well-known syntax. Python has native Jinja2, Rust has MiniJinja (by the same author). |
| Indexing | In-memory, scan on startup | Eliminates the entire SQLite/daemon/RPC/sync layer that dominates Beads' complexity |
| Cache | Shared JSON file, mtime-based invalidation | Simple, either implementation can read the other's cache. Gitignored. |
| Compaction | None | Closed issues stay as files. Cache handles query performance. Simplicity wins. |
| Dependency storage | Outbound only on disk | Store `blocked-by` on the dependent issue. Index computes reverse `blocks` links at scan time. |
| Dual implementation | Python + Rust, shared specs | Python for easy pip install. Rust for performance. Specs are the source of truth, not either codebase. |
