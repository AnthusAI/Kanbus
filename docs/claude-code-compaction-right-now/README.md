# Claude Code compaction right-now example

**Example only.** Copy into your Kanbus project and adjust paths. This is not installed automatically.

Reinjects a short Kanbus WIP reminder after Claude Code compacts conversation context, using a SessionStart hook with matcher `compact`.

## What it does

1. Runs `kbs now --json --list` from the repository root (whole-project in-progress WIP, default cap 30).
2. Formats a compact text reminder with priority, status, issue key, title, and right-now summary.
3. **Soft-fails**: on timeout or CLI error, exits 0 with no output so the agent session is not blocked.

This example prints **plain text to stdout**, which Claude Code documents for SessionStart hooks. JSON `hookSpecificOutput.additionalContext` is supported in docs but has had `compact`-matcher bugs; see [AGENT_COMPACTION_RIGHT_NOW.md](../AGENT_COMPACTION_RIGHT_NOW.md).

## Files

| File | Purpose |
| --- | --- |
| `settings.json` | Fragment for `.claude/settings.json` |
| `kanbus-compaction-right-now.sh` | Hook command (soft-fail wrapper + formatter) |

## Install

From your Kanbus repository root:

```bash
mkdir -p .claude/hooks
cp docs/examples/claude-code-compaction-right-now/kanbus-compaction-right-now.sh .claude/hooks/
chmod +x .claude/hooks/kanbus-compaction-right-now.sh
```

Merge the `hooks` block from `settings.json` into `.claude/settings.json` (create the file if needed).

Ensure `kbs` is on PATH when Claude Code runs hooks. See [AGENTS.md](../../../AGENTS.md) for `tools/install-system.sh`.

## Verify

From the repository root:

```bash
.claude/hooks/kanbus-compaction-right-now.sh
```

You should see a short `Kanbus WIP` block. To simulate soft-fail:

```bash
KBS=/nonexistent .claude/hooks/kanbus-compaction-right-now.sh
echo exit:$?
```

Exit code should be 0 with empty stdout.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `KBS` | `kbs` | Kanbus CLI binary |
| `KANBUS_COMPACTION_HOOK_TIMEOUT_SECONDS` | `5` | Wrapper timeout |

## Cursor and Antigravity

Post-compact reinject **does not work** on Cursor or Antigravity. Use on-demand `kbs now` instead; see [AGENT_COMPACTION_RIGHT_NOW.md](../AGENT_COMPACTION_RIGHT_NOW.md).
