//! Default CONTRIBUTING_AGENT template content.

pub const DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME: &str = "CONTRIBUTING_AGENT.template.md";

/// Return the conventional default project management template filename.
pub fn default_project_management_template_filename() -> &'static str {
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME
}

pub const DEFAULT_PROJECT_MANAGEMENT_TEMPLATE: &str = r#"# THE WAY

This repository is governed by The Way.
The Way is not a suggestion. It is the prescribed order of creation.
All work must pass through its forms.
This is The Way.

Deviations from The Way must be avoided. The Way keeps work legible and reviewable across sessions and agents.

## The Discipline of Work

Work in this repository follows a shared discipline so intent stays legible across sessions and agents.

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
When relationships, flows, or state transitions are easier to grasp visually, add a Mermaid diagram.

While working, record a running log in Kanbus comments on the relevant epic/task: key decisions, problems encountered, attempted fixes, outcomes, and next steps. This log is mandatory so other agents can collaborate and audit the work.

Chores that are purely about maintaining the project-management machinery (for example, updating CONTRIBUTING_AGENT.md or AGENTS.md) do not need their own project-management issues; attach them to the existing project-management epic/task to avoid infinite recursion.

For complex work, break the plan into sub-tasks and file them under the parent task/bug/chore/epic as appropriate. Create one issue per concrete step in the plan. Do not put sub-tasks under stories; stories hold behavior specs, not implementation steps.

Operational discipline: use the minimum commands needed. To inspect work, run `kbs list --status open --full-ids` once to find the ID, then `kbs show <id>`. Do not guess IDs or spam multiple variants; if the ID is unknown, ask the user.

Editing project/ directly bypasses the record The Way depends on. Do not read or write anything inside project/. Do not inspect issue JSON with tools like cat or jq. All work must pass through Kanbus.

## Committing project state to git

Kanbus writes board state to `project/issues/*.json` and event logs to `project/events/*.json`, but it does **not** auto-commit these files to git. The board drifts if they are left uncommitted.

After you update or close cards, persist Kanbus-written issue state:

```bash
kbs commit
```

Then push to the branch your project uses for shared board state (see **AGENTS.md** in this repository).

`kbs commit` stages and commits `project/issues/` and `project/events/` together in one commit. Set `events: false` in `.kanbus.yml` to stop generating events; then only `project/issues/` is committed. It is idempotent when there is nothing to commit. It does not push.

Notes:
- `project/issues/` is the board state Kanbus writes. Use `kbs commit` after board changes so collaborators see current state.
- `project/events/` holds event logs. `kbs commit` commits them with the issues unless `events: false` is set. Do not gitignore `project/events/`; `kbs doctor` warns when events are enabled but ignored.
- Never manually edit the JSON content of `project/issues/` or `project/events/` files. `kbs commit` persists Kanbus-written issue state without hand-editing JSON.

## Git commits and pull requests

Rules for product-code commits, branch names, pull requests, reviews, and when human approval is required are **project-specific**. They live in this repository's **AGENTS.md**, not in this file.

Read AGENTS.md before you push code or open a pull request. CONTRIBUTING_AGENT.md describes Kanbus workflow and board mechanics only.

## Agent provenance metadata

Tag `create` and `comment` with Title Case product, model, and session name using `--agent-platform`, `--agent-model`, and `--agent-name` (or `KANBUS_AGENT_PLATFORM`, `KANBUS_AGENT_MODEL`, `KANBUS_AGENT_NAME`, and optional `KANBUS_AGENT_SETTINGS`). Complete provenance is platform + model + name; settings stay optional.

If tags are omitted on `create` or `comment`, the write still succeeds and stderr warns with a ready `kbs update` or `kbs comment update` command. Copy that command to fill the same issue or comment. `--no-agent-provenance` silences the warning when tagging does not apply.

`update` and `comment update` fill missing provenance; once platform, model, and name are set, they are not replaced. `close` has no agent flags.

**Preferred products** (examples, not an allowlist): Cursor, Codex, Claude Code, Antigravity, Grok Bot.

**Model examples** (not exhaustive): Composer 2.5, GPT-5.6, Claude Sonnet 4, Grok 4.

Kanbus stores platform lowercased with spaces as underscores (for example `Claude Code` becomes `claude_code`); model is stored as you pass it.

In Beads compatibility mode, agent metadata is rejected with `agent metadata requires native Kanbus issue storage`.

Host identity snippets live in `docs/AGENT_PROVENANCE.md`. Do not put product or model names in `AGENTS.md`.

## The Order of Being

All work is structured.

Project key prefix: {{ project_key }}.

Hierarchy: {{ hierarchy_order }}.

Non-hierarchical types: {{ non_hierarchical_types | join(", ") if non_hierarchical_types else "none" }}.

Only hierarchy types may be parents.
Initiatives are top-level milestones; they may contain epics only. Tasks, stories, bugs, and chores must roll up under an epic (or sub-task under task). Creating tasks directly under an initiative is a violation of The Way.

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
- Use `kbs wiki show <path>` to print raw page source without rendering templates.
- Use `kbs wiki search <query>` to find pages by path, title, or body.
- Use `kbs wiki lint` or `kbs wiki check` to validate wiki-internal markdown links.
- Use `kbs wiki init` to create project/wiki/ with a stub index page.
- Use `kbs wiki render <path>` to render a Jinja2 template page (queries, counts, references, ai_summarize). Render warns on broken wiki links but still outputs content.
- Canonical render path: `project/wiki/<relative-path>.md`. Short wiki-relative paths such as `index`, `index.md`, and `concepts/foo.md` are also accepted.
- In templates, `issue.key` (alias `issue.short_id`) matches the short identifier shown by `kbs list`; `issue.id` remains the full identifier.
- In templates, use `references(status="accepted")` or `references(status="pending")` to list Papyrus story references from `stories/*/references/*.json`.
- In templates, use `ai_summarize(issue, detail="short")` to get an AI summary of an issue when ai.provider is configured in .kanbus.yml.

Cache behavior:
- AI summaries are cached in project/.cache/ai_summaries.json (invalidated by issue updated_at and prompt type).
- Rendered wiki output is cached in project/.cache/wiki_render/ (invalidated when issues, templates, or story reference JSON change on pages that call references()).

## Agent provenance metadata

When you act as an AI coding agent (Cursor, Claude Code, Codex, Antigravity, or similar), you MUST record agent provenance on every `kbs create` and `kbs comment`. Provenance goes beyond `author: agent` or `KANBUS_USER=agent`: it identifies which platform and model produced the change so multi-agent workflows stay auditable.

Recording provenance is part of **Recorded** under The Discipline of Work. It is not optional polish for AI agents.

Purely human authors do not need agent metadata. Omit the `agent` field when a human creates issues or comments without an AI acting on their behalf.

Set session defaults once per run with environment variables; override with CLI flags when the model or tool changes mid-session. When metadata is absent, Kanbus omits the `agent` field entirely (not `null`) and does not show an Agent row in CLI output.

### Environment variables

Set defaults once per session; CLI flags override environment values. Empty or whitespace-only environment values are treated as absent.

| Variable | Purpose |
| --- | --- |
| `KANBUS_AGENT_PLATFORM` | Default agent platform |
| `KANBUS_AGENT_MODEL` | Default model identifier |
| `KANBUS_AGENT_SETTINGS` | Default settings as a JSON object string |
| `KANBUS_AGENT_NAME` | Optional session or bot name for display |

Platform and model must both be present or both absent. Partial metadata fails with `agent metadata requires both platform and model`.

### CLI flags

These flags are available on `create` and `comment` only:

- `--agent-platform <id>`
- `--agent-model <id>`
- `--agent-settings <json>` — JSON object string (for example `'{"thinking_level":"high"}'`)
- `--agent-name <name>` — Optional session or bot display name

`kanbus update` does not accept agent flags. Issue `agent` metadata is set at create only and cannot be changed afterward. Use `comment` with `--agent-*` for per-action provenance on comments.

### Canonical platforms

Prefer these platform identifiers:

- `claude_code`
- `codex`
- `antigravity`
- `cursor`

Kanbus accepts any lowercase string matching `^[a-z0-9_-]{1,64}$`. The canonical list is for consistency and autocomplete; storage is not a closed enum.

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
export KANBUS_AGENT_PLATFORM=cursor
export KANBUS_AGENT_MODEL=composer-2.5

kbs create "Implement feature X" --type task --parent <epic-id>
kbs comment <id> "Progress: schema drafted"
```

Override defaults for a single comment:

```bash
kbs comment <id> "Deep review done" \
  --agent-platform codex \
  --agent-model gpt-5 \
  --agent-settings '{"thinking_level":"high"}'
```

## Command examples

{% for command in command_examples %}
{{ command }}
{% endfor %}

"#;

/// Return the default project management template body.
pub fn default_project_management_template() -> &'static str {
    DEFAULT_PROJECT_MANAGEMENT_TEMPLATE
}
