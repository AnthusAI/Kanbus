# Agent compaction and right-now elicitation

Coding agents compact conversation history when context windows fill. After compaction, board awareness and in-flight work can disappear from the session. Kanbus addresses this with **just-in-time (JIT) short programmatic guidance**: a compact reminder of current WIP pulled from the Kanbus board at the moment it is needed.

This page covers **coding-agent compaction hooks** that reinject Kanbus context. It is separate from [Lifecycle Hooks](LIFECYCLE_HOOKS.md), which are Kanbus CLI issue lifecycle hooks (`issue.create`, `issue.update`, and so on) configured in `.kanbus.yml`.

## Rationale

Long static system prompts are brittle. They go stale, consume context budget, and cannot reflect what changed five minutes ago on the board.

The [AnthusAI/Elicitation-Guidance](https://github.com/AnthusAI/Elicitation-Guidance) thesis asks whether **short, tool-authored hints** beat one long system prompt for reliability and orchestration. Kanbus right-now summaries are that hint surface: programmatic, current, and scoped to what matters now.

Do not copy shared hook snippets between projects as a substitute for this pattern. Each repository should call its own Kanbus board and format its own reminder.

## Two intentional modes

Ryan designed two complementary paths. Both are first-class; neither replaces the other.

### Mode A: whole-project WIP after compaction (automatic)

When a coding agent compacts context, a hook wrapper calls:

```bash
kbs now --json --list
```

(or `kanbus now --json --list`)

Rules:

- **No issue identifiers** on the command. Compaction reinjection is always whole-project WIP, capped at the default limit (30 most recently updated in-progress issues).
- The hook formats a **short reminder** from the JSON payload (see below). Do not dump raw `kbs now --list` text: the flat text render omits status and priority, which agents need for triage.
- The wrapper **soft-fails**: if `kbs` errors or times out, the agent session continues. Only the hook wrapper applies soft-fail; the CLI itself is unchanged.

### Mode B: on-demand focused WIP (agent-initiated)

Agents can run `kbs now` at any time for self-scoped context:

```bash
kbs now                    # whole-project tree (default cap)
kbs now --list             # flat list
kbs now --json --list      # machine-readable flat list
kbs now kbs-abc            # issue kbs-abc and descendants
kbs now kbs-abc --list     # flat descendants only
kbs now kbs-abc --no-recursive   # that issue only
```

Use on-demand `kbs now <id>` when the agent is working a pinned epic or task and wants focused WIP without whole-board noise. This mode is **separate from compaction reinjection** and works on every platform (including Cursor and Antigravity, which cannot reinject post-compact).

See [CLI Reference](CLI_REFERENCE.md) for full `kbs now` options.

## Preferred compaction payload

Stable hook contract:

```bash
kbs now --json --list
```

Each JSON item includes:

| Field | Purpose |
| --- | --- |
| `id` | Issue key |
| `title` | Issue title |
| `type` | Issue type |
| `status` | Workflow status |
| `priority` | Numeric priority (0-4) |
| `updated_at` | RFC3339 timestamp |
| `right_now_summary` | One-sentence WIP summary (or `null`) |
| `parent` | Parent issue key (or `null`) |

Format a compact reminder for injection, for example:

```text
Kanbus WIP (whole project, capped):

- [P1][in_progress] kbs-abc: Ship compaction docs — JSON payload spec landed.
- [P2][in_progress] kbs-def: Add Claude Code example — hook script in review.
```

Prefer formatting from JSON so **priority and status** appear in every line. The behavior contract is defined in `features/agent/compaction_right_now_payload.feature`.

## Soft-fail requirement

Compaction hooks must never block an agent session.

Hook wrappers should:

1. Run `kbs` from the repository root (where `.kanbus.yml` lives).
2. Apply a short timeout (for example 5 seconds).
3. On any failure (non-zero exit, timeout, invalid JSON), exit **0** with empty or minimal stdout.
4. Never propagate `kbs` non-zero exits to the hook process in a way that stops the agent.

The Kanbus CLI may still exit non-zero on real errors; only the **wrapper** swallows failures.

## Platform matrix

Capabilities differ by host. Do not claim post-compact reinject where the platform cannot do it.

| Platform | Post-compact reinject | v1 approach | Docs |
| --- | --- | --- | --- |
| **Claude Code** | Yes (SessionStart `compact`) | Hook calls `kbs now --json --list`, formats reminder | [Claude Code hooks guide](https://code.claude.com/docs/en/hooks-guide) |
| **Cursor** | **No** | On-demand `kbs now` in AGENTS.md; optional `preCompact` nudge only | [Cursor hooks](https://cursor.com/docs/hooks) |
| **Codex** | Yes (SessionStart source `compact`) | Same payload as Claude Code; concrete example planned | [Codex hooks](https://learn.chatgpt.com/docs/hooks) |
| **Antigravity** | **No** | On-demand `kbs now` only; do not use PreInvocation every-turn inject | [Antigravity IDE hooks](https://antigravity.google/docs/ide/hooks/) |

### Claude Code (first concrete example)

Use a **SessionStart** hook with matcher **`compact`** in `.claude/settings.json`. Plain text on stdout is injected into Claude's context after compaction.

**Do not use PreCompact or PostCompact** for reinjection. Those events observe compaction; they are not the documented reinject path. Use SessionStart `compact` instead.

Output options:

- **Plain text stdout** (recommended first): Claude Code adds stdout to context. See the [example](claude-code-compaction-right-now/README.md).
- **JSON `hookSpecificOutput.additionalContext`**: supported in docs, but historically unreliable for the `compact` matcher. Track [anthropics/claude-code#15174](https://github.com/anthropics/claude-code/issues/15174) and [anthropics/claude-code#28305](https://github.com/anthropics/claude-code/issues/28305). Prefer plain text stdout until your Claude Code version behaves consistently.

Example settings fragment (paths are illustrative):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/kanbus-compaction-right-now.sh"
          }
        ]
      }
    ]
  }
}
```

Copy and adapt from [docs/claude-code-compaction-right-now/](claude-code-compaction-right-now/).

### Cursor

Cursor's `preCompact` hook receives a `user_message` payload and is **observational only**. It cannot reinject agent context after compaction completes.

v1 for Cursor:

1. Document on-demand `kbs now` / `kbs now <id>` in AGENTS.md and CONTRIBUTING_AGENT.md.
2. Optionally add a `preCompact` hook that nudges the user or logs a reminder (stdout is not reinjected into the agent context post-compact).

Do **not** document Cursor compaction reinject as working.

### Codex

Codex SessionStart hooks support a `compact` source, similar to Claude Code. Use the same `kbs now --json --list` payload and formatting approach. A second concrete example will ship later.

### Antigravity

Antigravity IDE hooks have **no true post-compact reinject event**. v1 is on-demand `kbs now` documentation only.

Do **not** use PreInvocation hooks to inject Kanbus WIP on every turn as a compaction workaround. That adds noise and cost without matching compaction semantics.

## Related Kanbus surfaces

| Surface | Purpose |
| --- | --- |
| `kbs now` | Agent-facing WIP feed (this document) |
| `kbs lifecycle compact` | Issue body compaction inside Kanbus (unrelated to agent context compaction) |
| `.kanbus.yml` hooks | Kanbus CLI lifecycle hooks ([LIFECYCLE_HOOKS.md](LIFECYCLE_HOOKS.md)) |

## Example

See [docs/claude-code-compaction-right-now/](claude-code-compaction-right-now/) for a copy-paste Claude Code settings snippet and a soft-failing shell script that formats the JSON reminder.
