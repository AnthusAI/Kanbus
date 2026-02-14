# CLI Reference

This reference describes the intended Kanbus CLI for the first release. It is based on the current specification and will be kept in parity with both implementations.

## Global Flags

All commands support:

- `--json` Emit machine-readable JSON output
- `--help` Show command help

## Setup

### `kanbus init`

Initialize a Kanbus project in the current git repository.

```bash
kanbus init [--local]
```

Flags:
- `--local` Create a `project-local/` sibling directory for personal issues

### `kanbus setup agents`

Ensure `AGENTS.md` contains the Kanbus project-management section and refresh `CONTRIBUTING_AGENT.md`.

```bash
kanbus setup agents [--force]
```

Flags:
- `--force` Overwrite the Kanbus section without prompting

Notes:
- Run this after you update Kanbus templates or configuration so agent guidance stays current.
- This command only updates documentation and guard files. It does not modify issue data.

## Issue CRUD

### `kanbus create`

Create a new issue.

```bash
kanbus create <title> [options]
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
kanbus create "Implement OAuth2 flow" --type task --priority 1 --label auth
```

### `kanbus show`

Show issue details, dependencies, and comments.

```bash
kanbus show <id>
```

### `kanbus update`

Update issue fields.

```bash
kanbus update <id> [options]
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
kanbus update kanbus-a1b2c3 --status in_progress --assignee "you@example.com"
```

### `kanbus close`

Close an issue (shortcut for `--status closed`).

```bash
kanbus close <id> [--comment <text>]
```

### `kanbus delete`

Delete an issue (removes the file).

```bash
kanbus delete <id>
```

## Queries

### `kanbus list`

List issues with optional filters. Uses the index daemon by default.

```bash
kanbus list [filters]
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
kanbus list --status open --sort priority --limit 10
```

## Daemon

### `kanbus daemon-status`

Report daemon status.

```bash
kanbus daemon-status
```

### `kanbus daemon-stop`

Stop the daemon process.

```bash
kanbus daemon-stop
```

### `kanbus ready`

List open issues with no open blockers.

```bash
kanbus ready
```

### `kanbus blocked`

List issues in blocked status.

```bash
kanbus blocked
```

### `kanbus search`

Full-text search across titles and descriptions.

```bash
kanbus search <text>
```

## Dependencies

### `kanbus dep add`

Add a dependency.

```bash
kanbus dep add <id> --blocked-by <target-id>
kanbus dep add <id> --relates-to <target-id>
```

### `kanbus dep remove`

Remove a dependency.

```bash
kanbus dep remove <id> <target-id>
```

### `kanbus dep tree`

Display the dependency tree for an issue.

```bash
kanbus dep tree <id>
```

## Comments

### `kanbus comment`

Add a comment to an issue.

```bash
kanbus comment <id> <text>
```

## Migration

### `kanbus migrate`

Migrate Beads issues into Kanbus.

```bash
kanbus migrate
```

## Diagnostics

### `kanbus doctor`

Run environment diagnostics.

```bash
kanbus doctor
```

### `kanbus --version`

Show the Kanbus version.

```bash
kanbus --version
```

## Wiki

### `kanbus wiki render`

Render a wiki page with live interpolated data.

```bash
kanbus wiki render <page>
```

### `kanbus wiki list`

List available wiki pages.

```bash
kanbus wiki list
```

## Maintenance

### `kanbus validate`

Validate project integrity.

```bash
kanbus validate
```

### `kanbus stats`

Display project overview statistics.

```bash
kanbus stats
```
