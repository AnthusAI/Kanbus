# Orchestrator Architecture

This document describes how Kanbus drives AI-agent orchestration against real repositories. It is the authoritative design reference for the orchestrator workstream (epic [kbs-03f328](../project/issues/kbs-03f328a8-5434-42b5-bc22-e36d6ffc9039.json)) and for the Tactus procedure layer productionization workstream (epic [kbs-84c284](../project/issues/kbs-84c2848a-f313-468c-a2f1-fd94d9060983.json)).

Orchestration is implemented as a **standalone Python utility** that drives `kbs`/`kanbus` as execution primitives and imports [Tactus](https://github.com/AnthusAI/tactus) as the procedure runtime library. It is not compiled into the `kbs` Rust binary.

## Why orchestration lives outside the kbs binary

The `kbs` binary exists to read, write, and index issue JSON files fast enough that operators and agents can treat the project directory as a live queue. Orchestration has no hot inner loop that benefits from Rust: its latency budget is dominated by git operations, LLM calls, and validation commands, all of which are seconds to minutes. Putting orchestration logic inside `kbs` would:

- Force orchestration features to be implemented twice (Python + Rust) under Kanbus's parity regime, even though only one of those implementations is ever executed.
- Drag every orchestration iteration through Rust compile + Behave parity checks, slowing the loop that most needs to be fast.
- Couple the orchestrator's release cadence to the `kbs` binary's release cadence.

Keeping orchestration in a separate Python utility eliminates all three problems. The utility's "source of truth" is its own Behave feature suite, tested against the real Python utility only. No parity checker, no Rust mirror.

**Non-goal:** Python/Rust parity for orchestration behavior. The Python orchestrator is the single implementation.

## Layer responsibilities

```
┌─────────────────────────────────────────────────────────────────┐
│  Python Orchestrator (this workstream)                          │
│  • Workflow preset parsing                                      │
│  • Worker dispatch, retry, cancellation, timeouts               │
│  • Workspace setup and safety enforcement                       │
│  • Evidence assembly for commits and PR drafts                  │
│  • Tactus procedure invocation (library import)                 │
└─────────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ kbs / kanbus CLI │  │  Tactus library  │  │ git, gh, shell   │
│  (subprocess)    │  │    (import)      │  │  (subprocess)    │
│                  │  │                  │  │                  │
│ Issue state      │  │ Bounded agent    │  │ Branch, commit,  │
│ Claims / leases  │  │   turns          │  │   push, PR       │
│ Run records      │  │ Tool contracts   │  │ Validation cmds  │
│ Comments         │  │ Procedure flow   │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Kanbus owns

Kanbus is the source of truth for everything durable. The orchestrator never touches these state stores directly — it invokes the `kbs` or `kanbus` CLI, which writes to the JSON-file store under `project/`.

- **Issue state**: create, update, comment, close, assignee, status transitions.
- **Claims and leases**: `kbs claim-next` is the only correct way to mark an issue as being worked on. Lease expiry and staleness detection live in Kanbus.
- **Run records**: `kbs runs create|list|show|cancel`. Each run is a JSON file; the orchestrator writes to it by invoking these commands, not by touching files directly.
- **Workspace safety preconditions**: the orchestrator enforces rules the Kanbus roadmap already describes (canonical root, owned-marker file, origin remote verification) before any destructive operation. See [kbs-16ead9](../project/issues/kbs-16ead90b-5605-4020-afc0-a773debc403d.json).
- **Validation gates**: Kanbus exposes validation profiles (see [kbs-7223b4](../project/issues/kbs-7223b443-62ae-4b68-8576-8e3357f5e7e3.json)) and stores the selected profile + result on each run record.
- **PR publication rules**: Kanbus refuses to publish PRs that omit required sections. The orchestrator assembles the content; Kanbus is the gate.

### The Python orchestrator owns

Everything that is *control flow* rather than *state*:

- **Workflow preset loading**: parse `workflows/<name>.md` (YAML frontmatter + prompt body, same format in use today — see [workflows/default.md](../workflows/default.md)).
- **Worker dispatch**: call `kbs claim-next`, `kbs runs create`, set up an isolated workspace, run the worker turn, collect evidence.
- **Workspace lifecycle**: resolve the configured root, create `<root>/<issue>/<run>`, write the owned-marker file, verify remote, refuse destructive cleanup on unowned workspaces.
- **Branch naming and creation**: apply the `agent/<issue>/<run>` pattern in the target checkout.
- **Tactus procedure invocation**: directly import and call the Tactus runtime to execute bounded agent turns and PR-draft procedures.
- **Validation execution**: run the selected profile's command in the workspace, capture output, write the summary back to the run record via `kbs update` / `kbs runs`.
- **Commit, push, PR draft**: assemble evidence, invoke `git` and `gh` via subprocess, hand the PR draft to Kanbus's publication gate.
- **Retry, cancellation, timeouts**: enforce authoritative timeouts and honor `kbs runs cancel`. Stale-lease recovery ([kbs-c0e851](../project/issues/kbs-c0e8513d-2b30-4add-b4ae-027aae65361b.json)) is orchestrator logic that consults Kanbus lease state.

### Tactus owns

Tactus is the procedure runtime for bounded agent work. The orchestrator depends on it as a **library**, not a subprocess — `tactus` is declared in the orchestrator's `pyproject.toml` and imported directly.

- **Procedure execution**: a Tactus procedure is the unit of bounded agent work. The orchestrator calls procedures for worker turns and for PR-draft generation.
- **Tool contracts**: Tactus enforces the tool surface a procedure can use. The orchestrator configures that surface per procedure (narrow tool set for the worker, different surface for PR drafting).
- **Procedure output schemas**: Tactus procedures declare structured inputs/outputs. The orchestrator passes evidence in and receives typed results.
- **Per-run isolated Tactus storage**: Tactus writes its transient state (message history, checkpoints) to a location the orchestrator supplies per run, outside the target checkout.

**Boundary principle**: Tactus does not replace Kanbus. Tactus never mutates Kanbus state (issues, runs, comments); only the orchestrator does, via the `kbs`/`kanbus` CLI. A Tactus procedure that needs to record progress returns data to the orchestrator; the orchestrator decides whether to write it back to Kanbus.

The Kanbus/Tactus contract is enforced in code by keeping Tactus-facing modules free of any Kanbus CLI invocations, and enforced in tests by capability-contract scenarios ([kbs-a439b7](../project/issues/kbs-a439b7fd-6854-4237-a84d-2d5fd45f8cbb.json)).

## Run lifecycle

```
claim → create run → workspace → worker turn → validation → commit → push → PR draft → publish → record evidence
  │         │           │            │             │            │        │        │           │           │
  ▼         ▼           ▼            ▼             ▼            ▼        ▼        ▼           ▼           ▼
 kbs       kbs      orchestrator  Tactus       orchestrator   git      git     Tactus      kbs/gh      kbs
claim-   runs      (isolated     procedure    (profile cmd)                    procedure              runs /
 next    create    workspace)                                                                        comment
```

1. **Claim.** `kbs claim-next --assignee <worker>` (or claim an explicit issue for targeted runs). Kanbus sets the assignee and, for ready issues, transitions status. If no issue is claimable, the orchestrator exits cleanly.
2. **Create run.** `kbs runs create <issue> --worker <worker>` returns the run ID. All subsequent evidence attaches to this record.
3. **Workspace.** The orchestrator resolves the configured root, creates `<root>/<issue>/<run>`, writes the Kanbus-owned-marker file, clones or re-uses the target repo, verifies the origin remote. Workspace root must be outside the Kanbus repository.
4. **Branch.** Create `agent/<issue>/<run-short-id>` from the configured base branch.
5. **Worker turn.** Import Tactus; run the configured worker procedure with issue context, workspace path, and tool surface. Procedure returns structured output (changes applied, any comments to post, done reason).
6. **Validation.** Resolve the validation profile (explicit CLI arg > workflow config > repo default) and run its command. Capture stdout/stderr. A failure ends the run in `failed` status with the failure tail recorded on the run.
7. **Commit.** Assemble the conventional commit message from issue metadata + worker evidence ([kbs-e7f1f8](../project/issues/kbs-e7f1f8f5-7484-4e2e-83f6-1eca92a4b6bf.json)). Commit in the workspace branch.
8. **Push.** `git push origin agent/<issue>/<run>`. Record the remote branch on the run.
9. **PR draft.** Call the Tactus PR-draft procedure with evidence (issue, diff summary, validation result, run metadata). Receive structured `{title, body}`. Kanbus rejects drafts that omit required sections ([kbs-d3d7fa](../project/issues/kbs-d3d7fad8-1e1c-47aa-8d28-4dd6aad3444f.json)).
10. **Publish.** `gh pr create` with the drafted content. Record the PR URL on the run.
11. **Record evidence.** `kbs runs` update with the final status, commit SHA, remote branch, PR URL, validation summary. Optionally post a single summary comment on the assigned issue.

At any point, `kbs runs cancel <run>` transitions the run to `cancelled` and causes the orchestrator to tear down cleanly on next checkpoint. Timeouts use the same path.

## Failure and recovery modes

| Failure | Behavior |
|---|---|
| Claim finds no ready issue | Exit 0, no run created |
| Explicit issue not open / not ready | Exit 1, clear error, no run created |
| Unsafe workspace (symlinked, not owned, wrong remote) | Refuse; do not cleanup or overwrite; error before worker starts |
| Workflow preset missing | Exit 1 with "workflow preset not found" |
| Unknown publish mode / worker runtime | Exit 1 before worker starts |
| Worker procedure error | Run → `failed`, evidence + tail captured, workspace left in place for inspection |
| Validation failure | Run → `failed`, no commit, no push, no PR |
| Push / PR failure after commit | Run → `failed`, commit SHA recorded, workspace left in place |
| `kbs runs cancel` during run | Run → `cancelled` at next checkpoint, in-flight work abandoned |
| Stale lease on a prior run | Recovery flow ([kbs-c0e851](../project/issues/kbs-c0e8513d-2b30-4add-b4ae-027aae65361b.json)): refuse double-dispatch, preserve old evidence, require explicit retry |

The orchestrator never silently cleans up or retries. Any non-trivial recovery requires an operator decision or an explicit `--retry` invocation.

## CLI shape

The orchestrator exposes a small CLI (implementation tracked by [kbs-25eb65](../project/issues/kbs-25eb657f-2d8e-4369-a025-d5f593353e16.json)). Exact flags will match the existing `kbs orchestrator run` / `kbs worker run` surface so operator muscle memory carries over:

```
kanbus-orch run    [--issue <id>] [--workflow <preset>] [--once] [--max-concurrent N] [--worker <id>]
kanbus-orch worker <issue> [--workflow <preset>] [--target-repo <path>] [--worker <id>]
```

The CLI is a thin entrypoint; all logic is in importable Python modules so it can also be driven programmatically from tests.

## Testing model

Behave is the source of truth for orchestrator behavior. Scenarios are written outside-in against the real orchestrator binary with a local bare remote as the target repo. See [kbs-0ab475](../project/issues/kbs-0ab4754d-953b-4447-ab74-fccc34a807b5.json) and [kbs-9d5bfc](../project/issues/kbs-9d5bfcfe-e1e1-4757-8b9d-d4de5cba3093.json).

Unit tests are reserved for pure logic where a Behave scenario would be wasteful (workflow frontmatter parsing, branch-name templating, evidence-string assembly).

No parity checking exists for the orchestrator. The existing `@rust-only` scenarios in [features/workflow/orchestration.feature](../features/workflow/orchestration.feature) are obsolete artifacts of the prototype and will be removed as the Python orchestrator replaces them.

## What stays in the kbs binary

The primitives the orchestrator calls remain in `kbs` (and mirrored in `kanbus` under the existing parity regime):

- `kbs create | update | show | list | close | comment | delete`
- `kbs claim-next`
- `kbs runs create | list | show | cancel`
- `kbs ready`, `kbs dep`, `kbs validate`

These are not orchestration logic — they are state operations on the project store. They stay in Rust for speed and in Python for parity, exactly as the rest of the Kanbus CLI does.

## Prototype reference

A prior Rust implementation of orchestration lives on `feature/kanbus-maximus-trial` for historical reference. It shipped end-to-end (claim → worker → validate → push → PR) against a real Call Criteria task, which proves the run lifecycle above is executable. The Python utility reuses the same workflow preset format, branch-naming scheme, and run record JSON shape so that operator mental models and on-disk artifacts carry over; only the control-plane code is reimplemented.
