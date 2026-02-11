# CLI Reference

This reference describes the intended Taskulus CLI for the first release. It is based on the current specification and will be kept in parity with both implementations.

## Global Flags

All commands support:

- `--json` Emit machine-readable JSON output
- `--help` Show command help

## Setup

### `tsk init`

Initialize a Taskulus project in the current git repository.

```bash
tsk init [--dir <name>]
```

Flags:
- `--dir <name>` Project directory name (default: `project`)

## Issue CRUD

### `tsk create`

Create a new issue.

```bash
tsk create <title> [options]
```

Options:
- `--type <type>` Issue type (default: `task`)
- `--priority <0-4>` Priority (default: from config)
- `--assignee <name>` Assign to someone
- `--parent <id>` Set parent issue
- `--label <label>` Add a label (repeatable)
- `--blocked-by <id>` Add a blocked-by dependency (repeatable)
- `--description <text>` Set description body (use `-` to read from stdin)

Example:

```bash
tsk create "Implement OAuth2 flow" --type task --priority 1 --label auth
```

### `tsk show`

Show issue details, dependencies, and comments.

```bash
tsk show <id>
```

### `tsk update`

Update issue fields.

```bash
tsk update <id> [options]
```

Options:
- `--status <status>` Transition status
- `--priority <0-4>` Change priority
- `--assignee <name>` Change assignee
- `--claim` Set assignee to current user and status to `in_progress`
- `--title <text>` Change title
- `--add-label <label>` Add a label
- `--remove-label <label>` Remove a label

Example:

```bash
tsk update tsk-a1b2c3 --status in_progress --assignee "you@example.com"
```

### `tsk close`

Close an issue (shortcut for `--status closed`).

```bash
tsk close <id> [--comment <text>]
```

### `tsk delete`

Delete an issue (removes the file).

```bash
tsk delete <id>
```

## Queries

### `tsk list`

List issues with optional filters. Uses the index daemon by default.

```bash
tsk list [filters]
```

Filters:
- `--type <type>` Filter by issue type
- `--status <status>` Filter by status
- `--priority <n>` Filter by exact priority
- `--assignee <name>` Filter by assignee
- `--label <label>` Filter by label
- `--parent <id>` Filter by parent issue
- `--sort <field>` Sort by field (prefix `-` for descending)
- `--limit <n>` Limit number of results

Example:

```bash
tsk list --status open --sort priority --limit 10
```

## Daemon

### `tsk daemon-status`

Report daemon status.

```bash
tsk daemon-status
```

### `tsk daemon-stop`

Stop the daemon process.

```bash
tsk daemon-stop
```

### `tsk ready`

List open issues with no open blockers.

```bash
tsk ready
```

### `tsk blocked`

List issues in blocked status.

```bash
tsk blocked
```

### `tsk search`

Full-text search across titles and descriptions.

```bash
tsk search <text>
```

## Dependencies

### `tsk dep add`

Add a dependency.

```bash
tsk dep add <id> --blocked-by <target-id>
tsk dep add <id> --relates-to <target-id>
```

### `tsk dep remove`

Remove a dependency.

```bash
tsk dep remove <id> <target-id>
```

### `tsk dep tree`

Display the dependency tree for an issue.

```bash
tsk dep tree <id>
```

## Comments

### `tsk comment`

Add a comment to an issue.

```bash
tsk comment <id> <text>
```

## Migration

### `tsk migrate`

Migrate Beads issues into Taskulus.

```bash
tsk migrate
```

## Wiki

### `tsk wiki render`

Render a wiki page with live interpolated data.

```bash
tsk wiki render <page>
```

### `tsk wiki list`

List available wiki pages.

```bash
tsk wiki list
```

## Maintenance

### `tsk validate`

Validate project integrity.

```bash
tsk validate
```

### `tsk stats`

Display project overview statistics.

```bash
tsk stats
```
