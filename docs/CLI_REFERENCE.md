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

Notes:
- If no `OPENAI_API_KEY` is found (shell environment, `~/.kanbus.env`, or project `.env`), `init` prints a stderr hint: `Hint: no OPENAI_API_KEY found. Run "kbs setup ai" to store one in ~/.kanbus.env.`

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

### `kanbus setup ai`

Store an LLM API key once per user, so compaction, right-now summaries, standup rollups, and
wiki summarization work in every project without a per-project `.env`.

```bash
kbs setup ai [--key VALUE] [--from-stdin] [--variable NAME] [--status]
```

Flags:
- `--key VALUE` Pass the key value directly. The value may land in shell history; prefer the interactive prompt or `--from-stdin`.
- `--from-stdin` Read the key from the first line of stdin, e.g. `pbpaste | kbs setup ai --from-stdin` or `op read ... | kbs setup ai --from-stdin`.
- `--variable NAME` Store a different variable (default `OPENAI_API_KEY`), e.g. `ANTHROPIC_API_KEY` for `anthropic/...` models on the Python LiteLLM path.
- `--status` Print `OPENAI_API_KEY: <source>` (`process environment`, `~/.kanbus.env`, `project .env`, or `not set`) followed by the lookup order. Never prints the key itself.

With no flags in an interactive terminal, prompts for the key with hidden input. Works outside a
project — no `.kanbus.yml` needed.

On success, prints: `Saved OPENAI_API_KEY to ~/.kanbus.env (mode 600). A project .env or your shell environment can override it per project.`

Run non-interactively with no key provided fails with: `no key provided; pass --key, --from-stdin, or run interactively`.

Precedence when resolving a key at runtime: shell environment, then `~/.kanbus.env`, then the
project `.env` file.

`kbs setup ai` is a friendlier shortcut for `kbs setup env OPENAI_API_KEY` (or another variable
via `--variable`); see `kanbus setup env` below for the general-purpose command.

### `kanbus setup env`

Store or inspect any environment variable in `~/.kanbus.env`, machine-wide. `kbs setup ai` is
built on this command, specialized for the LLM API key.

```bash
kbs setup env NAME [--value VALUE] [--from-stdin] [--status]
```

Arguments:
- `NAME` Required. The environment variable name, matching `^[A-Z][A-Z0-9_]*$`. Fails otherwise with `invalid variable name: <name>`.

Flags:
- `--value VALUE` Pass the value directly.
- `--from-stdin` Read the value from the first line of stdin.
- `--status` Print `NAME: <source>` (`process environment`, `~/.kanbus.env`, `project .env`, or `not set`) followed by the lookup order. When not set, a third line prompts: `Run 'kbs setup env NAME' (or 'kanbus setup env NAME') to store one in ~/.kanbus.env.`

Value source precedence when saving: `--value`, then `--from-stdin` (first line), then a hidden
interactive prompt. Non-interactive with none of these fails with: `no value provided; pass
--value, --from-stdin, or run interactively`.

Writes or updates the `NAME=...` line in `~/.kanbus.env` (mode `600`), preserving other lines. On
success, prints: `Saved NAME to ~/.kanbus.env (mode 600). A project .env or your shell environment can override it per project.`

Works outside a project — no `.kanbus.yml` needed.

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
- `--agent-platform <name>` Agent product name (Title Case; see Agent metadata)
- `--agent-model <name>` Model name (Title Case)
- `--agent-name <name>` Session or bot display name (required for complete provenance)
- `--agent-settings <json>` JSON object of runtime settings

Example:

```bash
kanbus create "Implement OAuth2 flow" --type task --priority 1 --label auth
```

Example with agent metadata:

```bash
kanbus create "Agent task" --type task \
  --agent-platform "Cursor" --agent-model "Composer 2.5" --agent-name "Cloud Agent" \
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
- `--agent-platform <name>` Agent product name (Title Case; see Agent metadata)
- `--agent-model <name>` Model name (Title Case)
- `--agent-name <name>` Session or bot display name (required for complete provenance)
- `--agent-settings <json>` JSON object of runtime settings

Note: Incomplete provenance on `create` and `comment` warns with a one-step `kbs update` or `kbs comment update` command. Those commands set `agent` when it is missing. Complete metadata is not replaced.

Example:

```bash
kanbus update kanbus-a1b2c3 --status in_progress --assignee "you@example.com"
```

### `kanbus close`

Close an issue (shortcut for `--status closed`).

```bash
kanbus close <id> [--comment <text>]
```

With `--comment`, Kanbus records a normal issue comment before it attempts the
close transition. If the comment is invalid, the issue is unchanged. If the
comment succeeds but closing is rejected, the comment remains and the issue
keeps its prior status.

### `kanbus delete`

Delete an issue (removes the file).

```bash
kanbus delete <id>
```

## Issue Router

The optional Issue Router dispatches labeled issue packages through the configured agent adapter (Codex or OpenCode). See the [Issue Router operator guide](ISSUE_ROUTER_OPERATOR_GUIDE.md) for configuration and recovery, and the [Issue Router design](ISSUE_ROUTER_DESIGN.md) for exact planning, result, and lifecycle contracts.

```bash
kanbus router plan [--json]
kanbus router run --once
kanbus router run --watch
kanbus router pause
kanbus router resume
kanbus router hold --class <name>
kanbus router hold --provider-profile <name>
kanbus router unhold --class <name>
kanbus router unhold --provider-profile <name>
kanbus router status
kanbus router cancel <package-id>
kanbus router stop
```

`plan --json` prints a stable, two-space indented plan object. `run` requires exactly one of `--once` or `--watch`; `--once` processes at most the first eligible package and exits. `--watch` reconciles immediately, then polls router state and GitHub pull request state at `router.watch_interval` (default `30s`). The current watcher does not subscribe to MQTT for early wake-ups.

`hold` and `unhold` require exactly one of `--class <name>` or `--provider-profile <name>`. Pause, resume, holds, and watch state are local to the current clone; their router events are published for audit, but another clone does not inherit the effective control state. `stop` targets the local watch process and lets its active adapter call finish before exit. The Rust executable is available as both `kanbus` and `kbs`; the Python executable is `kanbus`.

The router publishes event history and router-owned issue status records to `refs/heads/kanbus/router-state` through an isolated hidden worktree. A usable `origin` is needed to share that branch with other clones. Checkpoint and artifact references are recorded in router history, but the current implementation does not separately push those refs or arbitrary artifact objects to `origin`; see the [Issue Router design](ISSUE_ROUTER_DESIGN.md) for details. Router commands fail with exit code 2 and `error: issue router is not configured` when the project has no `router:` block.

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

In human-readable output, every configured status that has no issues in the
result gets a marker line after the issue rows, in configuration order:

```
T open   - open   P2 Title
T closed - closed P2 Title
Backlog: (empty)
In Progress: (empty)
Blocked: (empty)
```

The marker lines follow the current filters: with `--type`, only statuses in
that type's workflow appear, and columns that have at least one listed issue
get no marker line. `--porcelain` (machine-readable output) and beads
compatibility mode never print marker lines.

### `kanbus standup`

Generate on-demand standup reports from right-now summaries (fail-closed; no placeholder text).

```bash
kbs standup [issue-ids...] \
  [--profile meeting-script|director-brief] \
  [--window rolling|calendar] \
  [--lookback 24h|8h|1d|...] \
  [--skip-weekends|--no-skip-weekends] \
  [--rollup flat|project|tree] \
  [--json]
```

- **`--window`**: `rolling` (duration lookback) or `calendar` (calendar-day buckets in `standup.timezone`).
- **`--lookback`**: Rolling duration string (`8h`, `24h`, `1d` sugar for 24h). Ignored for calendar completed-day selection except as configured lookback metadata.
- **`--skip-weekends` / `--no-skip-weekends`**: Calendar only. On Monday with skip enabled, completed bucket includes Friday–Sunday; otherwise previous calendar day only. No-op when `--window rolling`.
- Profile defaults: `meeting-script` uses calendar + skip weekends; `director-brief` inherits global rolling + 24h. CLI flags override config and profile.
- **Default fact feed** (no issue IDs): congregation scope (`in_progress` and `blocked`, cap 30).
- **`--rollup`**: `flat` (per-leaf bullets), `project` (one labeled bullet per project with bottom-up LLM rollup of right-now facts), or `tree` (nested by hierarchy with upward rollup on parents when children differ). When omitted: `project` for `virtual_projects` boards; `flat` for single-project board-wide; `tree` for explicit scoped issue IDs.
- **Project labels** (congregation / `virtual_projects`): bracket prefixes use one canonical display name per partition — `virtual_projects.<key>.display_name` when set, else congregation `name` for the primary board, else the partition key. Issue `project_label` metadata is normalized so the same board never appears under two labels in one report.
- **Close-out** section (both profiles): merged-but-open WIP, ready-to-close, external blocks, and a narrow stale WIP class (finishable phrasing such as waiting on review/deploy, no recent descendant activity). Capped at six bullets, prioritized for actionability. Likely questions skip issues already listed in Close-out.
- **director-brief Momentum** uses the same `--rollup` resolution as meeting-script Today (including congregation default `project`).
- **Yesterday**: emits `No completions yesterday.` when empty.

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

### Blocked issues

List issues in blocked status.

```bash
kanbus list --status blocked
```

### Searching

Full-text search across titles, descriptions, and comments.

```bash
kanbus list --search <text>
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

Tag `create` and `comment` with Title Case product, model, and session name (`--agent-platform`, `--agent-model`, `--agent-name`, or matching `KANBUS_AGENT_*` defaults). That is the expected path for agent provenance. Settings (`--agent-settings`) stay optional. If provenance is incomplete, the write still succeeds and stderr warns with a ready `kbs update` or `kbs comment update` command. Native Kanbus issue JSON stores the `agent` block when present; event payloads include it when present. CLI and console output omit the Agent row when metadata is absent — that is display behavior, not permission to skip tagging. Platform and model without a session name still store and display an Agent row, and still warn that provenance is incomplete.

### CLI flags

| Flag | Field | Commands |
| --- | --- | --- |
| `--agent-platform <name>` | `platform` | `create`, `comment`, `update`, `comment update` |
| `--agent-model <name>` | `model` | `create`, `comment`, `update`, `comment update` |
| `--agent-name <name>` | `name` | `create`, `comment`, `update`, `comment update` |
| `--agent-settings <json>` | `settings` | `create`, `comment`, `update`, `comment update` |

`update` and `comment update` set `agent` only when the issue or comment is missing complete provenance (platform, model, and name). Complete metadata is not replaced. `close` does not accept agent flags.

On `create` and `comment`, incomplete provenance warns on stderr with a ready `kbs update` or `kbs comment update` command. Use `--no-agent-provenance` to silence the warning when tagging does not apply.

### Environment variables

When a flag is omitted, Kanbus reads these environment variables (flags override env):

- `KANBUS_AGENT_PLATFORM`
- `KANBUS_AGENT_MODEL`
- `KANBUS_AGENT_SETTINGS` — JSON object string
- `KANBUS_AGENT_NAME`

Empty or whitespace-only environment values are ignored. Platform and model must both be present or both absent.

### Product and model names

Pass **Title Case** product and model names on the CLI (for example `Cursor`, `Claude Code`, `Composer 2.5`). Do not use a separate slug or identifier as the input convention.

Kanbus stores `platform` lowercased with spaces replaced by underscores (for example `Claude Code` becomes `claude_code`). `model` is stored as you provide it. After that normalization, `platform` must match `^[a-z0-9_-]{1,64}$` (a storage charset check, not a product allowlist).

**Preferred products** (examples, not a closed enum): Cursor, Codex, Claude Code, Antigravity, Grok Bot.

**Model examples** (not exhaustive): Composer 2.5, GPT-5.6, Claude Sonnet 4, Grok 4.

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
  "model": "Composer 2.5",
  "name": "Cloud Agent",
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
- `invalid agent platform` — stored platform failed the charset check after lowercasing and spaces-to-underscores (`^[a-z0-9_-]{1,64}$`)
- `invalid agent settings JSON: ...`
- `agent settings must not contain secret-like keys`
- `agent metadata requires native Kanbus issue storage`
- `agent metadata is already set`

Maintainer setup for host instructions and environment defaults: [Agent Provenance](AGENT_PROVENANCE.md).

## Comments

### `kanbus comment`

Add a comment to an issue.

```bash
kanbus comment <id> <text> [options]
```

Options:
- `--agent-platform <name>` Agent product name (Title Case; see Agent metadata)
- `--agent-model <name>` Model name (Title Case)
- `--agent-name <name>` Session or bot display name (required for complete provenance)
- `--agent-settings <json>` JSON object of runtime settings

When agent flags are omitted, `KANBUS_AGENT_*` environment variables apply.

Example:

```bash
kanbus comment kanbus-abc "Shipped fix" \
  --agent-platform "Codex" --agent-model "GPT-5.6" --agent-name "Cloud Agent"
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

## Methodologies

### `kanbus methodology list`

List the methodologies configured in `.kanbus.yml`, then the built-ins that are not active.

```bash
kanbus methodology list
```

Each line is `<marker> <name> (<source>) <title>`. `*` marks an active methodology and `-` a built-in that is not active. The source is `built-in` or `bundle <folder>`.

### `kanbus methodology show`

Print a methodology's guidance, rendered with the project's template variables.

```bash
kanbus methodology show <name>
```

Works for configured methodologies and for built-ins that are not active. An unknown name fails with the built-in names.

### `kanbus methodology run`

Run a tool that a configured methodology bundle declares.

```bash
kanbus methodology run <methodology> <tool> [args...]
```

The tool runs from the repository root with `KANBUS_METHODOLOGY_DIRECTORY` set to the bundle folder. Arguments pass through unchanged, and a non-zero exit fails the command. See [Methodologies](METHODOLOGIES.md).

## Diagnostics

### `kanbus doctor`

Run environment diagnostics.

```bash
kanbus doctor
```

Output includes an AI credentials line, e.g. `ai credentials: OPENAI_API_KEY from ~/.kanbus.env`,
or `ai credentials: OPENAI_API_KEY not set (run kbs setup ai)` when no key is configured.

It also lists the active methodologies (`methodologies: bdd, git-flow`), fails when one cannot be loaded or rendered, and prints a warning when `CONTRIBUTING_AGENT.md` differs from what the configured methodologies generate.

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
kanbus wiki render <page> --json
```

- `--json` Emit JSON with `path` and `rendered` fields (warnings stay on stderr)

### `kanbus wiki list`

List available wiki pages.

```bash
kanbus wiki list
kanbus wiki list --json
kanbus wiki list --limit 10
```

- `--json` Emit JSON with `count` and `pages` fields
- `--limit <n>` Cap output to n pages after sorting (0 for no limit)

### `kanbus wiki search`

Search wiki pages by path, title, and body.

```bash
kanbus wiki search <query>
kanbus wiki search <query> --json
kanbus wiki search <query> --limit 5
```

- `--json` Emit JSON with `query`, `count`, and `pages` fields (zero matches: `count` 0, not `0 results`)
- `--limit <n>` Cap output to n matches after sorting (0 for no limit)

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

## Complete command index

Every command and option accepted by the CLI, generated from the command definitions by `tools/generate_cli_reference.py` and checked in CI. The prose sections above explain behavior; this index is the exhaustive list. `kbs` accepts the same commands.

<!-- BEGIN GENERATED: command-index -->
<!-- Generated by tools/generate_cli_reference.py; do not edit by hand. -->

### `kanbus bulk`

Bulk issue operations.

#### `kanbus bulk update`

Update multiple issues selected by IDs and/or filters.

- `--id` `TEXT`
- `--where-type` `TEXT`
- `--where-status` `TEXT`
- `--set-status` `TEXT`
- `--set-assignee` `TEXT`
- `--no-validate`

### `kanbus close`

Close an issue.

- `IDENTIFIER` (argument)
- `--comment` `TEXT`: Add a comment before closing.

### `kanbus comment`

Add a comment to an issue.

- `[TOKENS]...` (argument)
- `--body-file` `FILENAME`
- `--no-validate`
- `--agent-platform` `TEXT`
- `--agent-model` `TEXT`
- `--agent-name` `TEXT`
- `--agent-settings` `TEXT`
- `--no-agent-provenance`: Do not warn when agent provenance is incomplete. See CONTRIBUTING_AGENT.md.

### `kanbus commit`

Commit board state (issues and events) to git.

### `kanbus console`

Console-related utilities.

#### `kanbus console close-detail`

Deprecated console command.

#### `kanbus console collapse`

Deprecated console command.

- `COLUMN` (argument)

#### `kanbus console collapse-column`

Deprecated console command.

- `COLUMN` (argument)

#### `kanbus console expand`

Deprecated console command.

- `COLUMN` (argument)

#### `kanbus console expand-column`

Deprecated console command.

- `COLUMN` (argument)

#### `kanbus console focus`

Focus on an issue and its descendants in the console.

- `IDENTIFIER` (argument)
- `--comment` `TEXT`: Comment ID to scroll to.

#### `kanbus console get`

Query a specific piece of console UI state.

##### `kanbus console get focus`

Print the currently focused issue ID, or 'none'.

##### `kanbus console get search`

Print the active search query, or 'none'.

##### `kanbus console get view`

Print the current view mode, or 'none'.

#### `kanbus console maximize`

Deprecated console command.

#### `kanbus console now`

Emit JSON issues for the Now panel with JIT right-now summaries.

#### `kanbus console reload`

Deprecated console command.

#### `kanbus console restore`

Deprecated console command.

#### `kanbus console screenshot`

Capture a PNG screenshot of the console board.

- `--output`, `-o` `TEXT`: Output PNG path (default: kanbus-board.png in the current directory).
- `--mode` `TEXT`: Appearance mode for the board (light or dark). Defaults to light for reproducible captures. Default: `light`.
- `--view` `TEXT`: Board type filter. Use all for every issue type (console ?type=all).
- `--expand-all`: Expand every collapsed status column before capture.
- `--expand` `TEXT`: Expand a status column before capture (repeatable).
- `--collapse` `TEXT`: Collapse a status column before capture (repeatable).

#### `kanbus console search`

Set or clear the search query in the console.

- `[QUERY]` (argument)
- `--clear`: Clear the active search query.

#### `kanbus console select`

Deprecated console command.

- `IDENTIFIER` (argument)

#### `kanbus console set-setting`

Deprecated console command.

- `KEY` (argument)
- `VALUE` (argument)

#### `kanbus console snapshot`

Emit a JSON snapshot for the console.

#### `kanbus console standup`

Emit a JSON standup report for the console API.

- `--request-json` `TEXT`: Standup request JSON. When omitted, JSON is read from stdin.

#### `kanbus console status`

Print a human-readable summary of the current console UI state.

#### `kanbus console toggle-settings`

Deprecated console command.

#### `kanbus console unfocus`

Clear the current focus filter in the console.

#### `kanbus console view`

Switch the console to a different view mode.

- `{initiatives|epics|issues}` (argument)

### `kanbus coordination`

Manage soft coordination leases.

#### `kanbus coordination claim`

Record a durable soft claim and announce it over MQTT when available.

- `--resource` `TEXT`: Resource to claim.
- `--owner` `TEXT`: Stable worker identifier.
- `--claim-id` `TEXT`: Unique claim identifier.
- `--revision` `INTEGER RANGE`: Positive fencing revision for hard mutex providers. Default: `1`.

#### `kanbus coordination inspect`

Inspect a resource's derived soft coordination lease.

- `--resource` `TEXT`: Resource to inspect.

#### `kanbus coordination publish-result`

Publish an artifact reference only when its logical revision is current.

- `--resource` `TEXT`: Logical resource being published.
- `--revision` `INTEGER RANGE`: Positive logical task revision.
- `--artifact` `TEXT`: Artifact reference to publish.

#### `kanbus coordination release`

Release the current soft lease and publish the visibility change.

- `--resource` `TEXT`: Resource to release.
- `--owner` `TEXT`: Current lease owner.
- `--claim-id` `TEXT`: Current claim identifier.

#### `kanbus coordination renew`

Extend the current winning soft lease.

- `--resource` `TEXT`: Resource to renew.
- `--owner` `TEXT`: Current lease owner.
- `--claim-id` `TEXT`: Current claim identifier.
- `--extend` `TEXT`: Duration to add to the current expiry (for example 120s).

### `kanbus cost`

Report LLM usage costs.

- `--days` `INTEGER`: Number of days to aggregate over.

### `kanbus create`

Create a new issue in the current project.

- `[TITLE]...` (argument)
- `--type` `TEXT`
- `--priority` `INTEGER`
- `--assignee` `TEXT`
- `--parent` `TEXT`
- `--label` `TEXT`
- `--description` `TEXT`
- `--local`
- `--id` `TEXT`: Explicitly specify the issue ID
- `--focus`: Deprecated. UI control commands are temporarily unavailable.
- `--no-validate`
- `--agent-platform` `TEXT`
- `--agent-model` `TEXT`
- `--agent-name` `TEXT`
- `--agent-settings` `TEXT`
- `--no-agent-provenance`: Do not warn when agent provenance is incomplete. See CONTRIBUTING_AGENT.md.

### `kanbus daemon-status`

Report daemon status.

### `kanbus daemon-stop`

Stop the daemon process.

### `kanbus delete`

Delete an issue and its event history.

- `IDENTIFIER` (argument)
- `--yes`
- `--recursive`

### `kanbus dep`

Manage issue dependencies.

- `[ARGS]...` (argument)

### `kanbus doctor`

Run environment diagnostics for Kanbus.

### `kanbus edit`

File edit commands mirroring the Anthropic text editor tool.

#### `kanbus edit create`

Create a new file with the given content.

- `PATH` (argument)
- `--file-text` `TEXT`

#### `kanbus edit insert`

Insert text after the given line number (0 = beginning).

- `PATH` (argument)
- `--insert-line` `INTEGER`
- `--insert-text` `TEXT`

#### `kanbus edit str-replace`

Replace exact text in file (must match exactly one location).

- `PATH` (argument)
- `--old-str` `TEXT`
- `--new-str` `TEXT`

#### `kanbus edit view`

View file contents or list directory.

- `PATH` (argument)
- `--view-range` `INTEGER...`: Start and end line numbers (1-indexed; -1 for end).

### `kanbus gh`

Alias for GitHub security synchronization commands.

#### `kanbus gh dependabot`

Dependabot synchronization commands.

##### `kanbus gh dependabot pull`

Pull Dependabot alerts from GitHub into Kanbus.

- `--dry-run`: Show what would be done without writing files.
- `--repo` `TEXT`: Override GitHub repository slug (owner/repo).
- `--min-severity` `TEXT`: Override minimum severity (critical, high, medium, low).
- `--state` `TEXT`: Override Dependabot alert state filter.
- `--parent-epic` `TEXT`: Override parent epic issue ID to attach findings to.

### `kanbus github`

GitHub security synchronization commands.

#### `kanbus github dependabot`

Dependabot synchronization commands.

##### `kanbus github dependabot pull`

Pull Dependabot alerts from GitHub into Kanbus.

- `--dry-run`: Show what would be done without writing files.
- `--repo` `TEXT`: Override GitHub repository slug (owner/repo).
- `--min-severity` `TEXT`: Override minimum severity (critical, high, medium, low).
- `--state` `TEXT`: Override Dependabot alert state filter.
- `--parent-epic` `TEXT`: Override parent epic issue ID to attach findings to.

### `kanbus gossip`

Realtime gossip commands.

#### `kanbus gossip broker`

Run a local UDS gossip broker.

- `--socket` `PATH`

#### `kanbus gossip watch`

Watch gossip notifications and update overlay cache.

- `--project` `TEXT`
- `--transport` `TEXT`
- `--broker` `TEXT`
- `--autostart`, `--no-autostart`
- `--keepalive`, `--no-keepalive`
- `--print`, `--no-print`: Print each received envelope as JSON (NDJSON) to stdout.

### `kanbus hooks`

Inspect and validate lifecycle hook configuration.

#### `kanbus hooks list`

List configured hooks and built-in providers.

#### `kanbus hooks validate`

Validate hook commands, IDs, and event bindings.

### `kanbus init`

Initialize a Kanbus project in the current repository.

- `--local`

### `kanbus jira`

Jira synchronization commands.

#### `kanbus jira pull`

Pull issues from Jira into Kanbus.

- `--dry-run`: Show what would be done without writing files.

### `kanbus lifecycle`

Issue lifecycle management commands.

#### `kanbus lifecycle compact`

Batch compact (summarize) issues based on lifecycle policies.

- `--all`: Process all eligible issues.
- `--query` `TEXT`: Filter issues by query.
- `--dry-run`: Show which issues would be compacted without mutating.
- `--archived-only`: Only compact archived issues (closed > 30 days).
- `--max-items` `INTEGER`: Limit number of issues to compact.

### `kanbus list`

List issues in the current project.

- `--status` `TEXT`
- `--type` `TEXT`
- `--assignee` `TEXT`
- `--label` `TEXT`
- `--parent` `TEXT`
- `--sort` `TEXT`
- `--search` `TEXT`
- `--project` `TEXT`: Filter by project label.
- `--no-local`
- `--local-only`
- `--limit` `INTEGER`: Maximum issues to display (0 for no limit).
- `--all`: Show all issues (same as --limit 0).
- `--porcelain`: Plain, non-colorized output for machine parsing.
- `--full-ids`: Show full issue keys even in single-project context.

### `kanbus localize`

Move a shared issue into project-local.

- `IDENTIFIER` (argument)

### `kanbus methodology`

Work with the methodologies configured in .kanbus.yml.

#### `kanbus methodology list`

List the configured methodologies, then the built-ins that are not active.

#### `kanbus methodology run`

Run a tool declared by a configured methodology bundle, from the repository root.

- `METHODOLOGY` (argument)
- `TOOL` (argument)
- `[ARGS]...` (argument)

#### `kanbus methodology show`

Show the rendered guidance of a methodology.

- `METHODOLOGY` (argument)

### `kanbus migrate`

Migrate Beads issues into Kanbus.

- `--into-existing`: Import Beads issues into an already initialized project. Repeatable: re-runs and overwrites matching issue JSON files.

### `kanbus move`

Move an issue to a different issue type.

- `IDENTIFIER` (argument)
- `ISSUE_TYPE` (argument)
- `--status` `TEXT`
- `--no-validate`

### `kanbus now`

List recently-updated issues with right-now summaries.

- `[ISSUE_IDS]...` (argument)
- `--limit` `INTEGER`
- `--all`
- `--list`
- `--no-recursive`
- `--expanded`
- `--collapsed`
- `--raw`
- `--yaml`
- `--json`
- `--text`
- `--status` `TEXT`: Status filter. Default: in_progress. Use all for every status.
- `--purge`: Clear right_now_summary and right_now_updated_at across the board.

### `kanbus overlay`

Overlay cache commands.

#### `kanbus overlay gc`

Sweep overlay cache entries.

- `--project` `TEXT`
- `--all`

#### `kanbus overlay install-hooks`

Install git hooks to run overlay gc after git operations.

#### `kanbus overlay reconcile`

Reconcile overlay cache entries against canonical issue files.

- `--project` `TEXT`
- `--all`
- `--prune`
- `--dry-run`

### `kanbus policy`

Policy management commands.

#### `kanbus policy check`

Check policies against an issue.

- `IDENTIFIER` (argument)

#### `kanbus policy guide`

Run policy guidance against an issue without enforcing blocks.

- `IDENTIFIER` (argument)

#### `kanbus policy list`

List all loaded policy files.

#### `kanbus policy steps`

List available policy steps.

- `--category` `TEXT`: Filter by category (given, when, then).
- `--search` `TEXT`: Filter by search term.

#### `kanbus policy validate`

Validate all policy files for syntax errors.

### `kanbus promote`

Promote a local issue to the shared project.

- `IDENTIFIER` (argument)

### `kanbus ready`

List issues that are ready (not blocked).

- `--no-local`
- `--local-only`

### `kanbus rekey`

Rename a project key and all issue IDs.

- `NEW_KEY` (argument)
- `--dry-run`: Print planned changes without modifying files

### `kanbus repair`

Repair a broken project structure.

- `--yes`

### `kanbus router`

Plan, run, and control the deterministic Issue Router.

#### `kanbus router cancel`

Request cancellation for an active package and preserve its checkpoint.

- `ISSUE_ID` (argument)

#### `kanbus router hold`

Hold new starts for exactly one configured route.

- `--class` `TEXT`
- `--provider-profile` `TEXT`

#### `kanbus router pause`

Pause new router starts and persist the control event.

#### `kanbus router plan`

Show which routed packages can start and why others are deferred.

- `--json`: Print the stable JSON plan.

#### `kanbus router recover`

Surface an orphaned or paused agent run without losing its evidence.

- `ISSUE_ID` (argument)
- `--json`: Print saved run metadata as JSON.

#### `kanbus router resume`

Resume scheduling without changing route holds.

#### `kanbus router run`

Run one package or continuously reconcile the project board.

- `--once`: Run one scheduler pass.
- `--watch`: Keep reconciling until stopped.

#### `kanbus router status`

Show scheduler state, active package count, and sorted route holds.

#### `kanbus router stop`

Stop future scheduler starts after the current package finishes.

#### `kanbus router unhold`

Release a hold for exactly one configured route.

- `--class` `TEXT`
- `--provider-profile` `TEXT`

### `kanbus setup`

Setup utilities for Kanbus.

#### `kanbus setup agents`

Ensure AGENTS.md contains Kanbus instructions.

- `--force`

#### `kanbus setup ai`

Store or inspect a user-level AI credential in ~/.kanbus.env.

- `--key` `TEXT`: API key value. Prefer the interactive prompt or --from-stdin so the key does not land in shell history.
- `--from-stdin`: Read the key from the first line of standard input.
- `--variable` `TEXT`: Environment variable name to store. Default: `OPENAI_API_KEY`.
- `--status`: Report where the key currently resolves from. Never prints the key.

#### `kanbus setup env`

Store or inspect any user-level Kanbus environment value in ~/.kanbus.env.

- `NAME` (argument)
- `--value` `TEXT`: Value to store. Prefer the interactive prompt or --from-stdin so the value does not land in shell history.
- `--from-stdin`: Read the value from the first line of standard input.
- `--status`: Report where the value currently resolves from. Never prints the value.

### `kanbus show`

Show details for an issue.

- `IDENTIFIER` (argument)
- `--json`
- `--raw`: Show raw issue data without summary interception

### `kanbus snyk`

Snyk vulnerability synchronization commands.

#### `kanbus snyk pull`

Pull vulnerabilities from Snyk into Kanbus.

- `--dry-run`: Show what would be done without writing files.
- `--min-severity` `TEXT`: Override minimum severity (critical, high, medium, low).
- `--org-id` `TEXT`: Override Snyk org ID.
- `--parent-epic` `TEXT`: Override parent epic issue ID to attach bugs to.

### `kanbus standup`

Generate on-demand standup reports from right-now facts.

- `[ISSUE_IDS]...` (argument)
- `--profile` `TEXT`: Standup profile: meeting-script or director-brief (default: meeting-script).
- `--window` `[rolling|calendar]`: Standup window mode: rolling or calendar.
- `--lookback` `TEXT`: Rolling lookback duration (for example 24h or 1d).
- `--skip-weekends`
- `--no-skip-weekends`
- `--json`
- `--no-recursive`
- `--rollup` `[flat|project|tree]`: Today rollup: flat, project (multi-board default), or tree.

### `kanbus stats`

Report project statistics.

### `kanbus summarize`

Summarize an issue using AI.

- `IDENTIFIER` (argument)
- `--dry-run`: Print the summary without saving to issue.

### `kanbus update`

Update an existing issue.

- `IDENTIFIER` (argument)
- `--title` `TEXT`
- `--description` `TEXT`
- `--status` `TEXT`
- `--priority` `INTEGER`
- `--assignee` `TEXT`
- `--parent` `TEXT`
- `--add-label` `TEXT`
- `--remove-label` `TEXT`
- `--set-labels` `TEXT`
- `--claim`
- `--no-validate`
- `--agent-platform` `TEXT`
- `--agent-model` `TEXT`
- `--agent-name` `TEXT`
- `--agent-settings` `TEXT`

### `kanbus validate`

Validate project integrity.

### `kanbus wiki`

Manage wiki pages.

#### `kanbus wiki check`

Validate the wiki tree (alias for wiki lint).

#### `kanbus wiki init`

Create the wiki directory and a stub index page.

#### `kanbus wiki lint`

Validate wiki-internal markdown links across the wiki tree.

#### `kanbus wiki list`

List wiki pages.

- `--json`
- `--limit` `INTEGER`: Maximum pages to display (0 for no limit).

#### `kanbus wiki render`

Render a wiki page.

- `PAGE` (argument)
- `--json`
- `--html`

#### `kanbus wiki search`

Search wiki pages by path, title, and body.

- `QUERY` (argument)
- `--json`
- `--limit` `INTEGER`: Maximum pages to display (0 for no limit).

#### `kanbus wiki show`

Show raw wiki page source without rendering templates.

- `PAGE` (argument)
<!-- END GENERATED: command-index -->
