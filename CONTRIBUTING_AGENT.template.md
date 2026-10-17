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

## Console UI Control: Real-Time Collaboration

When the user is actively watching the Kanbus console UI (typically at http://localhost:4242), you can programmatically control the interface to guide their attention and coordinate work in real-time.

### The Focus Command

The `kbs console focus` command immediately highlights an issue on the board, opens it in the detail panel, and filters to show only that issue and its descendants. This happens with sub-100ms latency via Unix socket and SSE notifications.

```bash
kbs console focus <issue-id>
```

### When to Use Real-Time Control

Use `kbs console focus` proactively to:
- **Direct attention after creating important work**: Show new epics or critical tasks immediately
- **Demonstrate updates**: Let the user see changes as they happen
- **Coordinate during collaboration**: Show what you're working on in real-time
- **Provide context**: Help the user understand issue relationships and structure

### Example: Creating and Focusing on an Epic

When you create a new epic with sub-tasks, immediately focus on it to show the user:

```bash
# Create the epic
kbs create "Implement authentication system" --type epic --description "Add JWT-based authentication with login, logout, and token refresh"

# The system returns: ID: tskl-auth

# Create sub-tasks
kbs create "Design authentication flow" --parent tskl-auth --type task
kbs create "Implement JWT generation" --parent tskl-auth --type task
kbs create "Add login endpoint" --parent tskl-auth --type task
kbs create "Add logout endpoint" --parent tskl-auth --type task

# NOW show the user the complete structure
kbs console focus tskl-auth
```

The user immediately sees the epic with all 4 sub-tasks on their board, understanding the full scope of what you've planned.

### Example: Tracking Progress in Real-Time

As you work through tasks, keep the user informed by focusing on what you're doing:

```bash
# Start working on the first task
kbs update tskl-auth.1 --status in_progress --assignee agent
kbs console focus tskl-auth.1

# User now sees you're working on "Design authentication flow"

# Complete it and move to the next
kbs close tskl-auth.1
kbs update tskl-auth.2 --status in_progress
kbs console focus tskl-auth.2

# User sees the completion and your shift to JWT generation
```

### Example: Showing Complex Relationships

When working with nested hierarchies, use focus to show structure:

```bash
# After creating a deep hierarchy
kbs create "Frontend overhaul" --type epic
# Returns: tskl-frontend

kbs create "Redesign dashboard" --parent tskl-frontend --type story
# Returns: tskl-frontend.1

kbs create "Update header component" --parent tskl-frontend.1 --type task
kbs create "Add metrics widgets" --parent tskl-frontend.1 --type task
kbs create "Improve responsive layout" --parent tskl-frontend.1 --type task

# Show the entire tree structure
kbs console focus tskl-frontend

# Now zoom in to show just the dashboard story and its tasks
kbs console focus tskl-frontend.1
```

### Example: Debugging with Focus

When investigating bugs, use focus to show the issue context:

```bash
# User reports a bug related to authentication
kbs create "Login fails with expired tokens" --type bug --parent tskl-auth

# Show them you're investigating by focusing on the bug in context
kbs console focus tskl-auth
# Now they see the bug alongside the original authentication epic

# After fixing
kbs close tskl-auth.5
kbs console focus tskl-auth
# Show the epic with the bug now closed
```

### Best Practices for Real-Time Control

1. **Focus after creation**: Always focus on newly created epics so the user sees the structure
2. **Focus when starting work**: When you update an issue to in_progress, focus on it
3. **Focus on parents after completion**: When closing a task, focus on its parent to show progress
4. **Don't over-focus**: Only focus when it genuinely helps the user understand what's happening
5. **Narrate your focus**: Briefly explain why you're focusing, e.g., "Let me show you the structure I've created"

### Future Commands (Planned in tskl-m59)

Additional UI control commands are being implemented:
- `kbs console unfocus` - Clear focus and return to full board view
- `kbs console view <mode>` - Switch between initiatives/epics/issues views
- `kbs console search <query>` - Set search filter
- `kbs console maximize` - Maximize the detail panel
- `kbs console close-detail` - Close the detail panel

Check `kbs show tskl-m59` for current implementation status.

