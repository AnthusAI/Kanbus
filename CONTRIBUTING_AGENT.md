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

Project key prefix: kbs.

Hierarchy: initiative -> epic -> task -> sub-task.

Non-hierarchical types: bug, story, chore, event.

Only hierarchy types may be parents.

Permitted relationships are fixed and not to be altered.

Allowed parent-child relationships:

- epic can have parent initiative.

- task can have parent epic.

- sub-task can have parent task.

- bug, story, chore, event can have parent initiative, epic, task.


Structure is not bureaucracy. Structure is memory.


## The Cognitive Framework

There is one discipline.

Outside-in Behavior-Driven Design.

The specification is the product.
Production code exists only to make a failing specification pass.

This is the first principle.

Non-negotiable laws:
- Begin with intent, not internals.
- Describe behavior in English.
- Translate behavior into Gherkin.
- Run it and watch it fail.
- Write only the code required to make it pass.
- All behavior must be specified.
- No specification may be red.
- Specifications describe observable behavior only.
- Specifications must not describe internal structure.

If behavior cannot be observed, it is not behavior.

## Roles in the Order

Epics define purpose and completion.

Stories define behavior. They contain Gherkin. They define what must happen.

Tasks and sub-tasks define implementation. They may not invent behavior beyond the specification.

Bugs restore violated behavior.

Chores maintain the ground on which behavior stands.

## The Rite of Gherkin

Every story must contain a Gherkin form.

Minimum structure:
```gherkin
Feature:
  Scenario:
    Given
    When
    Then
```

This is required.

Without this form, there is no alignment between intent and implementation.

## The Outside-In Ritual

When asked to add or change behavior, follow this sequence. It is not optional.
1. Clarify intent in English.
Capture role, capability, benefit.
Use: As a <role>, I want <capability>, so that <benefit>.
Confirm what is not included.
2. Create the epic and stories in Kanbus.
Record intent and Definition of Done.
3. Write executable specifications before any production code.
4. Run the specifications and confirm they fail.
5. Write the smallest code necessary to pass.
6. Refactor only while all specifications remain green.
7. Record progress. Close only when complete.

Skipping steps undermines the process.

## Coverage

100% specification coverage is mandatory.

Every behavior must be specified.
Every specification must pass.

Green is peace. Red is unfinished.

## Example: Hello World

Even the smallest program must pass through The Way.

No code precedes intent.
No intent precedes recording.
No implementation precedes failure.

The smallest program is still subject to discipline.

User request: "Please create a Hello World program."

1. Interview the stakeholder before any code
Ask why they want it and capture the intent in plain English.
Example prompts:
- Who is the audience for Hello World?
- What environment or language should it run in?
- What output is required and where should it appear?
- What is out of scope?

2. Convert intent into a user story (before any code)
Example:
As a new user, I want a Hello World program, so that I can verify the toolchain works.

3. Create an epic for the milestone and record the story

```bash
kbs create "Hello World program" --type epic
```

Example output (capture the ID):
```
ID: kanbus-1a2b3c
```

Record the intent on the epic:
```bash
kbs comment kanbus-1a2b3c "As a new user, I want a Hello World program, so that I can verify the toolchain works."
```

4. Create a story for the behavior and include Gherkin (before any code)

```bash
kbs create "Prints Hello World to stdout" --type story --parent kanbus-1a2b3c
```

Example output (capture the story ID):
```
ID: kanbus-4d5e6f
```

Attach the Gherkin acceptance criteria:
```bash
kbs comment kanbus-4d5e6f "Feature: Hello World
  Scenario: Run the program
    Given a configured environment
    When I run the program
    Then it prints \"Hello, world\" to stdout"
```

5. Run the Gherkin and confirm it fails (before any production code)
Run the behavior tests in the repo and confirm the new scenario fails for the right reason.

6. Implement the minimum code to pass, then refactor
Write the smallest change that makes the Gherkin scenario pass.
Refactor only while all specs remain green.

## Git Flow

Branches have fixed roles.

- `develop` is the continuous-integration branch. Merge accepted, green work there as soon as it is ready.
- `main` is the release branch. Releases, including semantic-release, run only from `main`. A merge to `develop` is not a production release.
- Feature branches start from `develop` and return to it through a pull request. They are short-lived: do not park completed work on a feature branch waiting for `main`.
- Promote `develop` to `main` when you intend a release, not as the daily integration path.
- Hotfix branches start from `main`, fix an urgent defect, and merge to `main` and back to `develop`.

Open pull requests against `develop` for product work. Merge them there as soon as review is addressed and CI is green.

Project management does not need a pull request. Kanbus issues, comments, status changes and `project/wiki` pages are committed on `develop` and pushed, with no feature branch, pull request or review loop. Do not mix board files into a product pull request; land the board on `develop` first.

Never commit product code directly to `main` or `develop`.
Name the Kanbus issue in the branch name or the pull request description so code stays linked to intent.
Branch naming, review, release and approval rules in this repository's AGENTS.md take precedence over this section.

## Semantic Release Alignment

Issue types map directly to release categories.


- bug -> fix

- story -> feat

- chore -> chore

- event -> chore


Release notes are a record, not commentary.


## Status and Priority

Statuses and workflows are fixed. They exist to maintain order.

Initial status: open.
Status changes must follow the workflow transitions below.
Workflow selection: use a workflow named after the issue type when present; otherwise use the default workflow.


default workflow:


- Discovery -> open, backlog

- backlog -> open, closed

- blocked -> in_progress, closed, backlog

- closed -> open, backlog

- in_progress -> open, review, blocked, closed, backlog

- open -> in_progress, closed, backlog

- review -> in_progress, closed




epic workflow:


- closed -> open

- in_progress -> open, review, closed

- open -> in_progress, closed

- review -> in_progress, closed




Priorities are:


- 0 -- critical

- 1 -- high

- 2 -- medium

- 3 -- low

- 4 -- trivial

Default is 2 (medium).

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


kanbus create "Plan the roadmap" --type initiative

kanbus create "Release v1" --type epic --parent <initiative-id>

kanbus create "Implement feature" --type task --parent <epic-id>

kanbus create "Fix crash on launch" --type bug --priority 0 --parent <epic-id>

kanbus update <id> --status in_progress --assignee "you@example.com"

kanbus update <id> --status blocked

kanbus comment <id> "Progress note"

kanbus list --status open

kanbus close <id> --comment "Summary of the change"

