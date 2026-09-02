# CLI Reference

This reference describes the intended Kanbus CLI for the first release. It is based on the current specification and will be kept in parity with both implementations. Rust installs `kbs` with identical subcommands.

## Global Flags

All commands support:

- `--json` Emit machine-readable JSON output
- `--help` Show command help
- `--version` Show CLI version (exempt from `kanbus-version` checks)

## Project CLI version requirement

Repositories may declare a minimum Kanbus CLI version in a root file named `kanbus-version`. The file contains a single line with a semantic version core (`MAJOR.MINOR.PATCH`), for example:

```
0.19.1
```

When present, every CLI command (except `--help`, `--version`, `init`, `setup`, and `repair`) compares the running CLI version against this requirement before loading project data. Git-describe suffixes on the running version (for example `0.18.3-29-g36a5204`) use only the leading `MAJOR.MINOR.PATCH` portion. Rust builds that cannot see a `kanbus-rust-*` tag (shallow clones, crates.io) fall back to the Cargo package version so the running CLI remains comparable. If the running CLI is too old, the command exits with code 1 and prints an upgrade message. Missing or unreadable files are handled as follows:

- Missing file: skip the check
- Empty or invalid file: fail with a parse error before project commands run

Upgrade an outdated Rust CLI with:

```bash
cargo install kanbus --locked --force
```

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
- `--agent-platform <id>` Agent platform (see Agent metadata)
- `--agent-model <id>` Model identifier
- `--agent-name <name>` Optional session or bot display name
- `--agent-settings <json>` JSON object of runtime settings

Example:

```bash
kanbus create "Implement OAuth2 flow" --type task --priority 1 --label auth
```

Example with agent metadata:

```bash
kanbus create "Agent task" --type task \
  --agent-platform cursor --agent-model composer-2.5 \
  --agent-settings '{"thinking_level":"high"}'
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

Note: Agent metadata is not supported on `update`. Issue `agent` is set at `create` only and cannot be changed afterward. Use `comment` with `--agent-*` for per-action provenance.

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
- `--limit <n>` Limit number of results (default: 0, no limit)
- `--all` Show all issues (same as `--limit 0`; cannot combine with `--limit`)
- `--full-ids` Show full issue keys even in single-project context

Example:

```bash
kanbus list --status open --sort priority --limit 10
kanbus list --parent kanbus-a1b2c3
kanbus list --all
```

### `kanbus commit`

Commit `project/issues/` changes to git.

```bash
kanbus commit
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

### `kanbus dep`

Manage issue dependencies.

```bash
kanbus dep <id> blocked-by <target-id>
kanbus dep <id> relates-to <target-id>
kanbus dep <id> remove blocked-by <target-id>
kanbus dep <id> remove relates-to <target-id>
kanbus dep tree <id> [--depth N] [--format FORMAT]
```

## Agent metadata

Optional provenance metadata records which AI platform, model, and runtime settings produced an issue or comment. Metadata is stored in native Kanbus issue JSON, included in event payloads when present, and displayed in CLI and console output only when present.

### CLI flags

| Flag | Field | Commands |
| --- | --- | --- |
| `--agent-platform <id>` | `platform` | `create`, `comment` |
| `--agent-model <id>` | `model` | `create`, `comment` |
| `--agent-name <name>` | `name` | `create`, `comment` |
| `--agent-settings <json>` | `settings` | `create`, `comment` |

`update` does not accept agent flags. Issue `agent` is create-only and immutable.

### Environment variables

When a flag is omitted, Kanbus reads these environment variables (flags override env):

- `KANBUS_AGENT_PLATFORM`
- `KANBUS_AGENT_MODEL`
- `KANBUS_AGENT_SETTINGS` — JSON object string
- `KANBUS_AGENT_NAME`

Empty or whitespace-only environment values are ignored. Platform and model must both be present or both absent.

### Platform validation

Platform values are lowercased and must match `^[a-z0-9_-]{1,64}$`.

Canonical platform identifiers (prefer these):

| Platform | Typical use |
| --- | --- |
| `cursor` | Cursor agents |
| `codex` | OpenAI Codex |
| `claude_code` | Claude Code |
| `antigravity` | Antigravity |

Other valid lowercase identifiers are accepted; storage is not a closed enum.

### Settings

`--agent-settings` and `KANBUS_AGENT_SETTINGS` accept a JSON object string. Recommended keys:

- `temperature` — model temperature
- `thinking_level` — reasoning depth (for example `off`, `low`, `medium`, `high`)
- `max_output_tokens` — positive integer output limit

Other non-secret keys are accepted (for example `speed`, `reasoning_effort`). Kanbus rejects keys whose names match `api_key`, `token`, `secret`, `password`, or `credential` (case-insensitive). Never store credentials in agent metadata.

The serialized `agent` block is limited to 2 KB.

### JSON shape

When present:

```json
{
  "platform": "cursor",
  "model": "composer-2.5",
  "name": "cloud-agent",
  "settings": {
    "thinking_level": "high"
  }
}
```

Omit the `agent` key entirely when absent. Omit `settings` when empty.

### Beads compatibility

In Beads compatibility mode (`--beads` or `beads_compatibility: true`), agent flags and environment defaults that would produce metadata fail with:

```
agent metadata requires native Kanbus issue storage
```

### Common errors

- `agent metadata requires both platform and model`
- `invalid agent platform`
- `invalid agent settings JSON: ...`
- `agent settings must not contain secret-like keys`
- `agent metadata requires native Kanbus issue storage`

## Comments

### `kanbus comment`

Add a comment to an issue.

```bash
kanbus comment <id> <text> [options]
```

Options:
- `--agent-platform <id>` Agent platform (see Agent metadata)
- `--agent-model <id>` Model identifier
- `--agent-name <name>` Optional session or bot display name
- `--agent-settings <json>` JSON object of runtime settings

When agent flags are omitted, `KANBUS_AGENT_*` environment variables apply.

Example:

```bash
kanbus comment kanbus-abc "Shipped fix" --agent-platform codex --agent-model gpt-5
```

## Synchronization

### `kanbus github dependabot pull`

Pull Dependabot alerts from GitHub Security into Kanbus.

```bash
kanbus github dependabot pull [--dry-run] [--repo <owner/repo>] [--min-severity <critical|high|medium|low>] [--state <open|fixed|dismissed|auto_dismissed>] [--parent-epic <id>]
```

Requires `GITHUB_TOKEN` or `GH_TOKEN`.
Short alias: `kanbus gh dependabot pull`.

## Migration

### `kanbus migrate`

Migrate Beads issues into Kanbus.

```bash
kanbus migrate
kanbus migrate --into-existing
```

`--into-existing` imports Beads issues into an already initialized Kanbus
project and is safe to re-run.

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

### `kanbus commit`

Commit `project/issues/` changes to git.

```bash
kanbus commit
```

## Realtime Gossip + Overlay

### `kanbus gossip broker`

Run a local UDS broker.

```bash
kanbus gossip broker [--socket <path>]
```

### `kanbus gossip watch`

Watch gossip notifications and update the overlay cache.

```bash
kanbus gossip watch [--project <label>] [--transport auto|uds|mqtt] [--broker auto|off|mqtt://...|mqtts://...] [--autostart|--no-autostart] [--keepalive|--no-keepalive]
kanbus gossip watch [..] [--print]
```

### `kanbus overlay gc`

Sweep overlay cache entries.

```bash
kanbus overlay gc [--project <label>] [--all]
```

### `kanbus overlay reconcile`

Reconcile speculative overlay entries against canonical issue files and optionally prune converged fields.

```bash
kanbus overlay reconcile [--project <label>] [--all] [--prune] [--dry-run]
```

### `kanbus overlay install-hooks`

Install git hooks to run overlay reconcile + GC after merges/checkouts.

```bash
kanbus overlay install-hooks
```

## Deprecated console controls

The legacy CLI-to-console control channel has been removed. These commands now fail with a migration hint while control messaging is moved to pub/sub:

```bash
kanbus console focus|unfocus|view|search|maximize|restore|close-detail|toggle-settings|reload|set-setting|collapse-column|expand-column|select
kanbus create --focus
```
