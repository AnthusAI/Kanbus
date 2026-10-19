# THE WAY

This repository is governed by The Way.
The Way is not a suggestion. It is the prescribed order of creation.
All work must pass through its forms.
This is The Way.

Deviations from The Way must be avoided. The Way keeps work legible and reviewable across sessions and agents.

## The Discipline of Work

Kanbus is the instrument of record. Nothing exists until it is named there.

Work begins in declaration, not in code.
Code without declaration is disorder.

Every change must be:
- Named.
- Described.
- Specified.
- Proven.
- Recorded.

If it is not recorded, it did not happen.

Use Markdown in issue descriptions and comments whenever it helps make the intent clearer.

You are strongly encouraged to illustrate your issue descriptions with diagrams.  When relationships, flows, or state transitions are easier to grasp visually, add a PlantUML, D2 or Mermaid diagram.  The system supports them all, and you can use the best tool for communicating the idea.  Be sure to use vertically-oriented layouts for diagrams since these issues will be presented in narrow viewports.

Diagrams must use fenced code blocks with the appropriate language identifier:
```mermaid
```plantuml
```d2

Direct file system access is strictly forbidden:
- Do not edit project/issues/ or project/events/ directly; use Kanbus for issues and events
- You may edit project/wiki/ (e.g. Markdown) directly
- Do not read issue JSON with tools like cat, jq, or grep
- Do not inspect the file system structure for issues or events
- All work on issues and events must pass through the kbs command

## Committing project state to git

Kanbus writes board state to `project/issues/*.json` and event logs to `project/events/*.json`, but it does **not** auto-commit these files to git. The board drifts if they are left uncommitted.

After you update or close cards, persist Kanbus-written issue state:

```bash
kbs commit
```

Then push to the branch your project uses for shared board state (see **AGENTS.md** in this repository).

`kbs commit` stages and commits `project/issues/` only. It is idempotent when there is nothing to commit. It does not push.

Notes:
- `project/issues/` is the board state Kanbus writes. Use `kbs commit` after board changes so collaborators see current state.
- `project/events/` holds event logs. `kbs commit` does not commit events. Commit events manually if your project tracks them in git.
- Never manually edit the JSON content of `project/issues/` or `project/events/` files. `kbs commit` persists Kanbus-written issue state without hand-editing JSON.

## Git commits and pull requests

Rules for product-code commits, branch names, pull requests, reviews, and when human approval is required are **project-specific**. They live in this repository's **AGENTS.md**, not in this file.

Read AGENTS.md before you push code or open a pull request. CONTRIBUTING_AGENT.md describes Kanbus workflow and board mechanics only.

## Running Kanbus (Do This Exactly)

CRITICAL: Always run Kanbus from the repository root so it can find `.kanbus.yml`.
Running from subdirectories will fail.

Preferred command:

```bash
kbs <command> [args...]
```

Example:

```bash
kbs create "My epic" --type epic --description "..."
```

Fallback (only if kbs is not available):

```bash
python -m kanbus.cli <command> [args...]
```

NOTE: The kbs command is strongly preferred. Only use Python fallback if kbs is unavailable.

## Right-now WIP (`kbs now`)

On demand, agents can read current WIP from the board without waiting for compaction hooks:

```bash
kbs now                  # whole-project tree (default cap 30 in-progress issues)
kbs now --list           # flat list with right-now summaries
kbs now --json --list    # JSON flat list (includes priority and status)
kbs now kbs-abc          # focused: issue kbs-abc and descendants
kbs now kbs-abc --no-recursive   # that issue only
```

Scoped `kbs now <id>` is for self-directed focus. Whole-project reinjection after coding-agent compaction uses the same JSON payload without issue identifiers; see [docs/AGENT_COMPACTION_RIGHT_NOW.md](docs/AGENT_COMPACTION_RIGHT_NOW.md).

## Agent provenance metadata

When you create issues or post comments as an AI agent, tag the write with Title Case **product**, **model**, and **session name** using `--agent-platform`, `--agent-model`, and `--agent-name` (or matching `KANBUS_AGENT_*` defaults). That records which platform, model, and runtime produced the change beyond `author: agent` or `KANBUS_USER=agent`, and helps distinguish Cursor, Codex, Claude Code, Antigravity, and Grok Bot in multi-agent workflows.

**Complete provenance** is platform + model + name. Settings (`--agent-settings`, `KANBUS_AGENT_SETTINGS`) stay optional.

If you omit tags on `create` or `comment`, the command still succeeds. Kanbus prints a warning on stderr with a ready `kbs update` or `kbs comment update` command. Copy that command to fill the same issue or comment. Use `--no-agent-provenance` when tagging does not apply and you want to silence the warning.

`update` and `comment update` accept `--agent-*` to fill missing tags. Once platform, model, and name are all set, they are not replaced. `close` does not take agent flags.

### Environment variables

Set defaults once per session; CLI flags override environment values. Empty or whitespace-only environment values are treated as absent.

| Variable | Purpose |
| --- | --- |
| `KANBUS_AGENT_PLATFORM` | Default agent product name |
| `KANBUS_AGENT_MODEL` | Default model name |
| `KANBUS_AGENT_SETTINGS` | Default settings as a JSON object string |
| `KANBUS_AGENT_NAME` | Session or bot name (required for complete provenance) |

Platform and model must both be present or both absent. Partial metadata fails with `agent metadata requires both platform and model`.

### CLI flags

These flags are available on `create`, `comment`, `update`, and `comment update`:

- `--agent-platform <name>` — Coding agent product name
- `--agent-model <name>` — Model name
- `--agent-settings <json>` — JSON object string (for example `'{"thinking_level":"high"}'`)
- `--agent-name <name>` — Session or bot label for this run (required for complete provenance; not the product name)

### Product and model names

Use plain **product names** and **model names** in Title Case. Pass the same names you would use in a handoff note. Do not invent a separate slug or identifier.

- **Platform** (`--agent-platform`, `KANBUS_AGENT_PLATFORM`): the coding agent product (for example Cursor, Codex).
- **Model** (`--agent-model`, `KANBUS_AGENT_MODEL`): the model the product is running (for example Composer 2.5, GPT-5.6).

Kanbus normalizes platform for storage (lowercase; spaces become underscores). Model is stored as you provide it. Kanbus does not enforce a fixed allowlist; the lists below are for consistency only.

**Preferred products** — use when they match your environment:

- Cursor
- Codex
- Claude Code
- Antigravity
- Grok Bot

If yours is not listed, use a short Title Case product name anyway.

**Model names** — prefer the official name from your host. When you choose the string yourself, use Title Case and conventional vendor punctuation. Examples (not exhaustive):

- Composer 2.5
- GPT-5.6
- Claude Sonnet 4
- Grok 4

**Session name** (`--agent-name`, `KANBUS_AGENT_NAME`): label for this run or bot (for example `Cloud Agent`, `bugbot`). Required for complete provenance. This identifies the session, not the product.

Host-specific instruction snippets (Cursor, Claude Code, Codex, Antigravity, Grok Bot) live in `docs/AGENT_PROVENANCE.md` and on the Kanb.us Agent Provenance page. Do not put product or model names in shared `AGENTS.md`.

### Settings

`--agent-settings` and `KANBUS_AGENT_SETTINGS` accept a JSON object. Recommended keys:

- `temperature` — model temperature (for example `0.7`)
- `thinking_level` — reasoning depth (for example `off`, `low`, `medium`, `high`)
- `max_output_tokens` — positive integer output limit

Other non-secret keys are accepted (for example `speed`, `reasoning_effort`). Kanbus does not enforce a closed allowlist of settings keys.

**No secrets:** Never store API keys, tokens, passwords, or credentials in agent metadata. Keys whose names match `api_key`, `token`, `secret`, `password`, or `credential` (case-insensitive) are rejected with `agent settings must not contain secret-like keys`. Keep credentials in your agent host environment instead.

The serialized `agent` block is limited to 2 KB.

### Beads compatibility

In Beads compatibility mode (`--beads` or `beads_compatibility: true` in `.kanbus.yml`), agent flags and environment defaults that would produce metadata are rejected:

```
agent metadata requires native Kanbus issue storage
```

Use native Kanbus issue storage when you need agent provenance.

### Example workflow

```bash
export KANBUS_AGENT_PLATFORM="Cursor"
export KANBUS_AGENT_MODEL="Composer 2.5"
export KANBUS_AGENT_NAME="Cloud Agent"

kbs create "Implement feature X" --type task --parent <epic-id>
kbs comment <id> "Progress: schema drafted"
```

Override defaults for a single comment:

```bash
kbs comment <id> "Deep review done" \
  --agent-platform "Codex" \
  --agent-model "GPT-5.6" \
  --agent-name "Cloud Agent" \
  --agent-settings '{"thinking_level":"high"}'
```

## The Order of Being

All work is structured.

Project key prefix: {{ project_key }}.

Hierarchy: {{ hierarchy_order }}.

Non-hierarchical types: {{ non_hierarchical_types | join(", ") if non_hierarchical_types else "none" }}.

Only hierarchy types may be parents.

Permitted relationships are fixed and not to be altered.

Allowed parent-child relationships:
{% for rule in parent_child_rules %}
- {{ rule }}
{% endfor %}

Structure is not bureaucracy. Structure is memory.

{% for methodology in methodologies %}
{{ methodology.content }}
{% endfor %}

## Status and Priority

Statuses and workflows are fixed. They exist to maintain order.

Initial status: {{ initial_status }}.
Status changes must follow the workflow transitions below.
Workflow selection: use a workflow named after the issue type when present; otherwise use the default workflow.

{% for workflow in workflows %}
{{ workflow.name }} workflow:
{% if workflow.statuses %}
{% for status in workflow.statuses %}
- {{ status.name }} -> {{ status.transitions | join(", ") if status.transitions else "none" }}
{% endfor %}
{% else %}
- No statuses defined.
{% endif %}

{% endfor %}
Priorities are:

{% for priority in priorities %}
- {{ priority.value }} -- {{ priority.name }}
{% endfor %}
Default is {{ default_priority_value }} ({{ default_priority_name }}).

Severity is not emotion. It is signal.

## Wiki Workflow

The wiki lives under project/wiki/. You may edit Markdown files there directly.

When to use the wiki:
- Add and edit project/wiki/*.md for reports, status pages, and documentation.
- Use `kbs wiki list` to discover wiki pages.
- Use `kbs wiki render <path>` to render a Jinja2 template page (queries, counts, ai_summarize).
- In templates, use `ai_summarize(issue, detail="short")` to get an AI summary of an issue when ai.provider is configured in .kanbus.yml.

Cache behavior:
- AI summaries are cached in project/.cache/ai_summaries.json (invalidated by issue updated_at and prompt type).
- Rendered wiki output is cached in project/.cache/wiki_render/ (invalidated when issues or templates change).

## Command examples

{% for command in command_examples %}
{{ command }}
{% endfor %}

