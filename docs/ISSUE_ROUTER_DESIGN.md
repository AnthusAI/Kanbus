# Issue Router design

The Issue Router is an optional reconciliation loop that dispatches bounded Kanbus issue packages to a coding agent. Kanbus issues and event history remain the durable source of truth. The router decides when work may start, provides an isolated worktree and claim, checks the structured result, and publishes accepted changes and review state.

The first adapter is Codex. The router does not ask a model to choose work, assign work, or perform review approval. Planning, package boundaries, capacity, retries, claim fencing, and GitHub lifecycle are deterministic.

## Configuration contract

Projects without a top-level `router:` block keep normal Kanbus behavior. Router commands fail with exit code 2 and `error: issue router is not configured`. The router block is strict: unknown fields and invalid values fail configuration loading with exit code 1.

The initial configuration is:

```yaml
router:
  workflow:
    pending: open
    active: in_progress
    review: review
    blocked: blocked
    terminal: [closed]
  limits:
    project_wip: 2
    review_wip: 1
    class_wip:
      implementation: 1
    provider_wip:
      codex-default: 1
  providers:
    codex-default:
      adapter: codex
      command: codex
      args: []
  classes:
    implementation:
      providers: [codex-default]
  forge:
    provider: github
    repository: anthusai/kanbus
    base_branch: main
    api_url: https://api.github.com
    token_env: GITHUB_TOKEN
  watch_interval: 30s
  retries:
    max_attempts: 3
```

`workflow` requires all five roles. `terminal` is a nonempty list of configured statuses. Workflow role names must map to distinct statuses, and every configured status must exist in the project workflow. `limits.project_wip` and `limits.review_wip` are required positive integers; review WIP cannot exceed project WIP. `class_wip` and `provider_wip` are optional maps of configured class/profile names to positive integers. Missing entries have no route-specific cap. `retries.max_attempts` defaults to 3. `watch_interval` defaults to `30s` and accepts a positive duration in seconds, minutes, or hours.

The only initial adapter is `codex`. Each provider profile requires `adapter: codex`. `command` defaults to `codex`; `args` defaults to an empty list and replaces the executable's default prefix for controlled environments such as the fake adapter used by specs. Class provider lists are ordered and nonempty. An exact provider route is pinned to that profile; a class route tries the configured profiles in order when a new claim or takeover begins.

`forge.repository` is required and accepts one `owner/repository` value. `provider` defaults to `github` and no other provider is accepted in the first slice. `base_branch` defaults to `main`, `api_url` defaults to `https://api.github.com`, and `token_env` defaults to `GITHUB_TOKEN`. Credentials are read only from the named environment variable; they are never stored in `.kanbus.yml`, and the router does not fall back to another token source.

The router uses existing top-level `coordination.providers` settings. `[git]` and `[mqtt, git]` are soft coordination: MQTT may improve claim visibility, but neither configuration guarantees exclusive starts. `[mutex_api, mqtt, git]` requests hard coordination. When Mutex API is first in the configured provider list, a router start requires a live Mutex API lease; falling back to MQTT or Git does not authorize an adapter start.

Watch mode polls on `router.watch_interval`. When MQTT coordination is available, it subscribes before claim publication and uses peer notifications to wake reconciliation before the next scheduled poll. If MQTT becomes unavailable, Git-backed router-state polling continues at the configured interval.

## Shared router state and publication

Shared router events and router-owned issue status records are published to `refs/heads/kanbus/router-state`. The router creates publication commits in an isolated hidden Git worktree, keeping the user's checkout index and uncommitted files out of router commits. Router events and affected issue records are written by the router; the adapter cannot write Kanbus project data directly. Without an `origin` remote, this state stays in the local repository and cannot coordinate with other clones. If a configured `origin` cannot be reached, state publication fails.

The Python implementation keeps a hidden worktree for this branch. The Rust implementation currently creates a temporary detached worktree for each publication. Both target the dedicated state ref, but the worktree lifetime differs between implementations.

## Routing and package boundaries

An issue opts into routing with exactly one of these labels:

- `agent-class:<class-name>` selects an ordered provider profile list from `router.classes`.
- `agent-provider:<profile-name>` pins the issue to that configured provider profile.

Labels are parsed as exact values. An issue with both label kinds, multiple routing labels, an unknown class, or an unknown provider profile is deferred with `invalid_route`. Human assignees are preserved and do not imply routing.

A tagged issue is one routed package. Untagged descendants belong to the nearest tagged ancestor. A tagged descendant begins its own package and is excluded from the ancestor's package. Package issue IDs are sorted by hierarchy traversal order, then issue ID for stable output. The adapter may propose transitions only for issue IDs in its package. The router validates that each transition is legal before applying it.

## Definition of Ready and plan order

A candidate can start only when it is in the configured pending status, has a valid route, has no unresolved blocking dependency, is within its package boundary, and passes project policy. Recoverable active work and packages with requested changes are planned before new pending work.

Pending work sorts by the latest time the issue entered the configured pending status, oldest first. Ties sort by `created_at` ascending and then issue ID ascending. `updated_at` is not a scheduling key. For a class route, the selected profile is the first configured profile below its capacity limit. A provider route never moves to another profile.

Deferred candidates use these reasons, in precedence order:

1. `paused`
2. `held`
3. `invalid_route`
4. `dependency_blocked`
5. `policy_rejected`
6. `retry_backoff`
7. `project_wip_limit`
8. `review_wip_limit`
9. `class_wip_limit`
10. `provider_wip_limit`

Issues outside the configured pending state and without recoverable active work are omitted from the plan. Project WIP counts every issue in configured active, review, or blocked statuses, including human-owned work. Review WIP counts every issue in review. Class and provider caps count router packages with those routes in active, review, or blocked status. Blocked and review packages consume WIP. These limits stop router starts; manual Kanbus transitions can exceed them.

`kanbus router plan` prints eligible rows and deferred rows in deterministic order. `kanbus router plan --json` prints a two-space indented JSON object with this fixed key order and shape:

```json
{
  "version": 1,
  "enabled": true,
  "paused": false,
  "eligible": [
    {
      "issue_id": "kbs-101",
      "route": {
        "kind": "class",
        "name": "implementation",
        "provider_profile": "codex-default"
      },
      "package_issue_ids": ["kbs-101", "kbs-102"],
      "pending_since": "2026-09-17T10:00:00Z",
      "attempt": 1
    }
  ],
  "deferred": [
    {"issue_id": "kbs-103", "reason": "provider_wip_limit"}
  ]
}
```

The JSON `route.kind` is `class` or `provider`. `name` is the class or profile named in the label. `provider_profile` is the profile selected for this attempt. `pending_since` is RFC3339 UTC. `attempt` is the attempt number that would start next. Arrays use plan ordering. The absent-config error is written to stderr and does not return a partial plan.

## Execution and operator controls

`kanbus router run --once` performs one reconciliation pass and processes at most the first eligible package synchronously. It creates a run-specific worktree and branch, executes the configured Codex adapter, validates the result, records the accepted checkpoint and artifact references in router history, and opens or updates a GitHub pull request for a completed result when a forge is configured. Its summary is:

```text
Issue Router run completed: started=1 completed=1 review=1 failed=0 deferred=0
```

The counters reflect that pass. A completed adapter outcome moves the package to review; a retryable failure increments `failed`; deferred counts the planned packages that could not start. A no-work pass succeeds with all zero counters.

`kanbus router run --watch` reconciles immediately and then repeats every `watch_interval`. Each cycle reads router history from the state branch, polls GitHub pull request state, and plans work. An MQTT peer notification can trigger an earlier cycle; an MQTT outage leaves the configured polling path in place. `kanbus router stop` asks the local watch process to finish its active adapter call, release its scheduler claim, and stop before starting more work. Watch process state is local to that clone.

`pause` and `resume` change the scheduler state for the current clone. `hold` and `unhold` change one configured class or provider profile in that clone. Control events are published to router history for audit, but the effective pause, holds, and watch-process state are stored in Git-private local state; another clone does not inherit them. A pause does not cancel an active package. A hold defers only matching routes. `status` reports the local running/stopped state, active/paused scheduling, active run count, and sorted holds. `cancel <package-id>` sends cancellation to the current adapter, blocks that package, and preserves the latest accepted checkpoint.

Both runtimes keep the active claim and adapter process identifier in Git-common local state. A separate `kanbus router cancel` invocation signals the child, records a durable cancellation request, and prevents the cancelled claim from publishing accepted results.

## Codex result and publication contract

The adapter returns one JSON object with these keys in this order:

```json
{
  "schema_version": 1,
  "outcome": "completed",
  "summary": "Implementation is ready for review.",
  "issue_updates": [],
  "checkpoint": {
    "ref": "refs/kanbus/router/checkpoints/kbs-101",
    "revision": 5
  },
  "artifacts": [
    {"name": "test-report", "ref": "refs/kanbus/router/artifacts/kbs-101/test-report-r5"}
  ]
}
```

`outcome` is `completed`, `blocked`, or `retryable_failure`. `issue_updates` contains `{issue_id, status}` proposals only. The router rejects an issue outside package scope and any transition that is not allowed by the configured workflow. `checkpoint` is either `null` or `{ref, revision}`. `artifacts` is a list of named refs. The adapter cannot publish a pull request, change the current claim, or move the package to a terminal state.

Every claim has a unique claim ID and a monotonically increasing logical package revision. A checkpoint or result is accepted only when both values match the current claim. The current claim fences issue transitions, checkpoint movement, artifact publication, branch push, and pull request updates. GitHub does not offer a transaction that can atomically test the Kanbus lease while creating a PR. The router therefore checks its exact claim immediately before and after the branch push and PR API call, and uses `--force-with-lease` compare-and-swap rollback if it loses the claim. A claim lost during an in-flight API request can leave a PR briefly visible; when remote branch state has concurrently changed, best-effort rollback may fail and requires operator inspection. Such an operation is not accepted into Kanbus router state. A stale claim may leave its temporary worktree but cannot move a durable router ref.

Checkpoint references use the `refs/kanbus/router/checkpoints/<package-id>` namespace. Both runtimes move the accepted checkpoint ref to the run commit and lease-push it to `origin`, allowing another clone to fetch and restore it. Artifact values such as `refs/kanbus/router/artifacts/<package-id>/<name>-r<revision>` are recorded as named references in router history; they are not materialized or pushed automatically, so consumers must not assume an artifact ref resolves unless the adapter published its object separately. A rejected or stale publication does not advance the accepted checkpoint or record the artifact as accepted.

## Failure and recovery

Retryable failures remain active until the final allowed attempt. Attempt `n` waits `min(30 seconds * 2^(n-1), 15 minutes)` before retry. With the default of three attempts, delays before attempts two and three are 30 and 60 seconds. The next adapter request includes the latest accepted checkpoint reference, which another clone can fetch from `origin`. The third retryable failure transitions it to the configured blocked status and records `maximum retry attempts reached`. A structured `blocked` outcome blocks immediately without retry.

The execution lease detects a dead process. Structured progress and accepted checkpoints from the current claim reset the default 24-hour stale-ownership clock; human comments and empty heartbeats do not. A package with stale ownership may be taken over with a new claim and higher logical revision. The new adapter request receives the latest accepted checkpoint reference and can fetch it from the shared remote.

## GitHub pull request lifecycle

For a completed result, the router creates or updates a pull request titled `[<package-id>] <issue-title>` on `codex/router/<package-id>/r<revision>`. Its body includes `Kanbus package: <package-id>`. The issue enters the configured review status. Opening or synchronizing a pull request keeps it in review.

The router polls GitHub during each watch reconciliation and consumes normalized events with schema version 1: `event_id`, `kind`, `action`, `repository`, `number`, `head_sha`, and `merged`; check-run events also include `conclusion`. Pull-request actions are `opened`, `synchronize`, `requested_changes`, `approved`, and `closed`. Check-run events use `kind: check_run`, `action: completed`, and a `conclusion` of `success` or `failure`. Event IDs are idempotent. Events for an unowned pull request or a repository mismatch are rejected.

Requested changes or a failed required check move the package from review to active, ahead of pending work; the next run updates the same pull request. A successful check leaves it in review. Approval alone leaves the package in review and is tied to that head SHA; a synchronize event invalidates approval for an older head. A merged event moves the package to a configured terminal status only when an approval for the current head was recorded. A closed, unmerged pull request moves the package to blocked. The router never merges a pull request.

## Multi-router guarantees

Git-only and MQTT-plus-Git coordination are soft. Competing workers can both start the same package if they cannot see one another's claims. Once a newer claim is visible, revision checks reject stale checkpoint and result publication. MQTT does not provide hard exclusion; it supplies a low-latency early-wake signal, while an outage falls back to Git polling at the configured interval.

With `[mutex_api, mqtt, git]`, the router requires a live Mutex API lease before starting a package. If Mutex API is unavailable, no adapter starts through a weaker provider. While the lease is live, only its owner may start the package; after expiry, another worker may take over with a new claim revision. Result fencing applies when the newer claim is visible to the publisher.

## Specification status

`features/router/` records the intended behavior contract for the first Codex vertical slice. Unit and feature tests cover selected router behavior. The offline integration harness exercises two connected clones against a disposable Git remote, including router-owned state publication; it does not simulate a network partition. Its optional live Mutex API and MQTT paths require explicit service configuration and should be described as validated only after an actual live run. There is no live GitHub or real-agent coverage in that harness. The generic coordination feature `features/coordination/revision_publication.feature` specifies revision-fenced reference publication. Future non-Codex adapters, automatic merge, LLM scheduling, provider cost budgets, and session-quota admission remain outside this slice and should be specified separately when approved.
