# Agent provenance

Coding agents should tag Kanbus creates and comments with the **product name**, **model name**, and a **session or bot name**. That is how a board with several agents stays readable.

Kanbus does not read Cursor, Claude Code, or other host config directories. Those files exist so **that product's agents** already know who they are when they call `kbs`.

## Who owns what

- **Host product config** (`.cursor/`, `.claude/`, Codex or Antigravity project instructions, Cloud environment variables): identity for agents running in that product. Product name, and the model for this session when you know it. Session name stays per-run.
- **`CONTRIBUTING_AGENT.md`**: how to tag. Title Case names, flags, environment variables, the warning, and how to fill tags later. Same procedure on every Kanbus site.
- **`AGENTS.md`**: pointer to `CONTRIBUTING_AGENT.md` only. Do not put product or model names there. Many hosts read the same file.
- **`kbs` / `kanbus`**: merges flags and `KANBUS_AGENT_*`. If provenance is incomplete, the write still succeeds and stderr prints a one-step `kbs update` or `kbs comment update` command. `--no-agent-provenance` silences that warning.

## Names

Use Title Case product and model names, the same words you would use in a handoff note.

Preferred products: Cursor, Codex, Claude Code, Antigravity, Grok Bot. If yours is not listed, use a short Title Case product name anyway.

Example models: Composer 2.5, GPT-5.6, Claude Sonnet 4, Grok 4. Prefer the official name from the host.

Session name (`--agent-name` / `KANBUS_AGENT_NAME`) is this run or bot (for example `Cloud Agent`), not the product.

## CLI usage

Prefer environment defaults when the host can set them. Still set a session name for this run:

```bash
export KANBUS_AGENT_PLATFORM="Cursor"
export KANBUS_AGENT_MODEL="Composer 2.5"

kbs comment kbs-abc "Progress: schema drafted" --agent-name "Cloud Agent"
```

If environment variables are not set, pass the names from the host instructions:

```bash
kbs create "Fix login" --type task \
  --agent-platform "Cursor" \
  --agent-model "Composer 2.5" \
  --agent-name "Cloud Agent"
```

If you omitted tags, copy the command from the warning:

```bash
kbs update kbs-abc --agent-platform "Cursor" --agent-model "Composer 2.5" --agent-name "Cloud Agent"
kbs comment update kbs-abc <comment-id> --agent-platform "Cursor" --agent-model "Composer 2.5" --agent-name "Cloud Agent"
```

`close` does not take agent flags. Settings (`--agent-settings`) are optional.

## Host identity snippets

Paste the block that matches the product into **that product's** project instructions or rules. Do not put these strings in shared `AGENTS.md`.

Each snippet tells the agent its product name. The model changes often: use the name the host shows for this session, or set `KANBUS_AGENT_MODEL` in the session environment.

### Cursor

Suggested location: a Cursor project rule (for example `.cursor/rules/kanbus-provenance.mdc`) that applies in this repository.

```text
When you create or comment on Kanbus issues, tag agent provenance.

Product: Cursor
Model: the model name for this session (Title Case, for example Composer 2.5)
Session name: a short label for this run (for example Cloud Agent)

If KANBUS_AGENT_PLATFORM and KANBUS_AGENT_MODEL are set, reuse them and still pass --agent-name.
Otherwise pass --agent-platform "Cursor" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns that provenance is incomplete, copy the printed kbs update or kbs comment update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata) for the procedure.
```

Cursor Cloud and similar hosts can inject session environment instead of relying on the rule alone:

```bash
KANBUS_AGENT_PLATFORM=Cursor
KANBUS_AGENT_MODEL=Composer 2.5
```

Use the environment or secrets UI only as a way to export those variables. They are not credentials.

### Claude Code

Suggested location: Claude Code project instructions under `.claude/` (not root `AGENTS.md`).

```text
When you create or comment on Kanbus issues, tag agent provenance.

Product: Claude Code
Model: the model name for this session (Title Case, for example Claude Sonnet 4)
Session name: a short label for this run

If KANBUS_AGENT_PLATFORM and KANBUS_AGENT_MODEL are set, reuse them and still pass --agent-name.
Otherwise pass --agent-platform "Claude Code" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns that provenance is incomplete, copy the printed update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).
```

### Codex

Suggested location: Codex project instructions for this workspace (not shared `AGENTS.md`).

```text
When you create or comment on Kanbus issues, tag agent provenance.

Product: Codex
Model: the model name for this session (Title Case, for example GPT-5.6)
Session name: a short label for this run

If KANBUS_AGENT_* defaults are set, reuse platform and model and still pass --agent-name.
Otherwise pass --agent-platform "Codex" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns, copy the printed kbs update or kbs comment update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).
```

### Antigravity

Suggested location: Antigravity project or agent instructions for this workspace.

```text
When you create or comment on Kanbus issues, tag agent provenance.

Product: Antigravity
Model: the model name for this session (Title Case)
Session name: a short label for this run

Prefer KANBUS_AGENT_PLATFORM and KANBUS_AGENT_MODEL when set; still pass --agent-name.
Otherwise pass --agent-platform "Antigravity" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns, copy the printed follow-up command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).
```

### Grok Bot

Suggested location: the bot or session instructions for that Grok Bot, not shared `AGENTS.md`.

```text
When you create or comment on Kanbus issues, tag agent provenance.

Product: Grok Bot
Model: the model name for this session (Title Case, for example Grok 4)
Session name: a short label for this bot or session

Prefer KANBUS_AGENT_* when set; still pass --agent-name.
Otherwise pass --agent-platform "Grok Bot" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns, copy the printed kbs update or kbs comment update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).
```

## See also

- `CONTRIBUTING_AGENT.md` — Agent provenance metadata
- [CLI Reference](CLI_REFERENCE.md) — flags and JSON shape
