# Issue Router operator guide

This guide covers the first Codex-based Issue Router. Router configuration is optional. A project without `router:` can use every existing Kanbus command; router commands report that the router is not configured.

## Configure a project

Add a `review` status to the project workflow before enabling the router. Map all router roles to statuses that already exist in that workflow. Start with one Codex profile and a small WIP limit:

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
    repository: owner/repository
    base_branch: main
    api_url: https://api.github.com
    token_env: GITHUB_TOKEN
  watch_interval: 30s
  retries:
    max_attempts: 3
```

The router requires the workflow and limits blocks, one or more Codex provider profiles, and a GitHub repository. `base_branch` defaults to `main`, `api_url` defaults to `https://api.github.com`, and `token_env` defaults to `GITHUB_TOKEN`. Class routes use the configured provider order. The optional `command` and `args` values can point to a controlled fake adapter during tests. Put the GitHub token in the named environment variable, not in `.kanbus.yml`; the router does not read a fallback token.

The router publishes its event history and router-owned issue status records to the dedicated `refs/heads/kanbus/router-state` branch using an isolated hidden Git worktree. Without an `origin` remote, router state remains local to the repository. If a configured `origin` is unreachable, publication fails.

The router uses the project's existing `coordination.providers` configuration. `[git]` and `[mqtt, git]` are soft coordination; MQTT may improve claim visibility, but duplicate starts remain possible. `[mutex_api, mqtt, git]` requires a live Mutex API lease before work can start. If Mutex API is unavailable, the router does not start work through a weaker provider. Hard leases provide exclusion while they are live; expiry permits a newer claim to take over.

## Opt issues in and inspect the plan

Apply exactly one routing label to each package root:

- `agent-class:implementation` to use the named class's provider list.
- `agent-provider:codex-default` to pin work to one exact provider profile.

Do not change the human assignee to show execution ownership. The router keeps the assignee as accountability metadata. Untagged descendants stay in the nearest tagged package. A tagged descendant forms a separate package and is excluded from its ancestor's run.

Inspect the text or machine-readable plan before dispatch:

```bash
kanbus router plan
kanbus router plan --json
```

The plan identifies each package root, route, selected profile, package issue IDs, pending-entry time, and upcoming attempt. Deferred rows give one deterministic reason. Resolve invalid routes, blocking dependencies, or policy rejection on the issue. If a WIP limit is reached, review or blocked packages still consume capacity until their status changes.

## Run and watch

Run one synchronous scheduling pass:

```bash
kanbus router run --once
```

It processes at most the first eligible package, waits for the Codex adapter result, validates it, records accepted checkpoint and artifact references in router history, publishes router-owned status, and opens or updates a pull request when complete. The summary reports started, completed, review, failed, and deferred counts.

For ongoing operation, start watch mode:

```bash
kanbus router run --watch
```

Watch mode reconciles immediately and polls router state and GitHub pull requests at `watch_interval`. When MQTT coordination is available, the watcher also subscribes before publishing claims and uses peer notifications to wake reconciliation before the next scheduled poll. If MQTT is unavailable, the router continues on its bounded Git polling interval.

## Pause, hold, inspect, cancel, and stop

Use a global pause when no new router package should start. Active work continues unless you cancel it.

```bash
kanbus router pause
kanbus router resume
```

Hold one class or provider profile to defer only matching packages:

```bash
kanbus router hold --class implementation
kanbus router unhold --class implementation
kanbus router hold --provider-profile codex-default
kanbus router unhold --provider-profile codex-default
```

Inspect scheduler state, active run count, and sorted holds:

```bash
kanbus router status
```

Cancel an active package when its current work should stop. The router requests adapter cancellation, blocks the package, and preserves the latest accepted checkpoint:

```bash
kanbus router cancel kbs-123
```

Both runtimes record the active claim and adapter process in Git-common local state. A separate `kanbus router cancel` invocation signals that process, records the durable cancellation request, and fences later publication from the cancelled claim.

Stop watch mode running in this clone after the current adapter call finishes and release the scheduler claim:

```bash
kanbus router stop
```

Pause, resume, hold, unhold, and stop actions are written to router history for audit. The effective pause, holds, and watch state are kept in Git-private local state, so they apply to this clone and are not inherited by another clone. Releasing a hold does not clear the local global pause.

## Review and merge

The router opens a pull request after a completed adapter outcome and moves the package into the configured review status. The adapter completing work does not close the Kanbus issue. Opening or synchronizing a PR leaves the package in review. A failed required check returns the package to active for repair; a successful check leaves it in review.

GitHub requested changes move the package back to active and ahead of pending work. The next run continues the same pull request. Approval alone keeps the package in review, and a new commit invalidates approval for the old head. The router moves the package to a configured terminal status only after GitHub reports the current approved PR head as merged. Closing without merge moves the package to blocked. The router does not merge PRs.

## Failure recovery

Retryable adapter failures keep the package active, preserve the last accepted checkpoint, and use bounded backoff. With three maximum attempts, the first two retry delays are 30 and 60 seconds. The third retryable failure moves the package to blocked with a diagnostic. A structured `blocked` result blocks immediately.

After a process dies, a later router can take over after the execution lease expires or ownership becomes stale. It creates a new claim ID and logical revision and supplies the latest accepted checkpoint reference to the adapter. Accepted checkpoint refs are lease-pushed to `origin`, so another clone can restore the referenced commit. Artifact values remain named metadata references unless the adapter separately materializes and publishes their objects. Once the newer claim is visible, stale claims are rejected from accepted result publication. See the [design](ISSUE_ROUTER_DESIGN.md) for implementation details.

If hard coordination is configured and Mutex API is unavailable, restore the endpoint and credentials before retrying. The router intentionally starts no adapter through a weaker provider. In soft mode, duplicate starts are possible when workers cannot see each other's claims. Revision fencing rejects stale results after the newer claim becomes visible. The connected-clone offline scenario does not reproduce a network partition; the live mutex and MQTT harness paths also need to be run against configured services before treating them as validated. See the [integration harness notes](ISSUE_ROUTER_INTEGRATION_HARNESS.md) for the exact test scope.

See [Issue Router design](ISSUE_ROUTER_DESIGN.md) for the JSON contract, exact plan ordering, configuration validation, event schema, and detailed WIP rules.
