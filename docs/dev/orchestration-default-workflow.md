Kanbus orchestration uses one generic workflow for all tasks.

Default operator command:

```bash
kbs orchestrator run \
  --once \
  --max-concurrent 1 \
  --issue <issue-id> \
  --worker <worker-id>
```

Resolution order:

1. If `--workflow <path-or-preset>` is supplied, Kanbus uses that explicit workflow.
2. If the current Kanbus project has an `orchestration:` block in `.kanbus.yml`, Kanbus overlays it onto the built-in generic workflow and uses the result.
3. If the current Kanbus project has `workflows/default.md`, Kanbus uses it.
4. Otherwise Kanbus uses the built-in generic workflow.

Task-specific details belong in the Kanbus issue title and description. Workflow files describe project policy: target branch, validation command, publish mode, workspace root, branch naming, generic worker rules, and bounded procedure hooks.

The preferred repository default lives in `.kanbus.yml` so operators can run the same command for every task without supplying a workflow file:

```yaml
orchestration:
  target:
    branch: develop
    validation: make test
    publish: pull-request
  workspace:
    root: ~/.kanbus/orchestration-workspaces
  worker:
    branch_pattern: agent/{{ issue.identifier }}/{{ run.short_id }}
```

Workers use `codex-app-server` by default. A repository can opt into the Tactus worker runtime for controlled experiments by supplying a worker procedure:

```yaml
orchestration:
  worker:
    runtime: tactus
    branch_pattern: agent/{{ issue.identifier }}/{{ run.short_id }}
    procedure:
      runtime: tactus
      file: workflows/kanbus-worker.tac
      timeout_seconds: 3600
```

The Tactus procedure receives the assigned issue, repo policy, workspace path, run metadata, and rendered worker prompt. Kanbus also registers a `kanbus` host module for the procedure with path-checked tools for reading, writing, listing files, running guarded workspace commands, and commenting on the assigned issue. Kanbus still owns final validation, artifact checks, commit, push, and PR creation.

Legacy or highly specialized repository workflow files can still live at `workflows/default.md`, but they are lower precedence than `.kanbus.yml` because repo policy belongs with the rest of Kanbus project configuration.

Pull request copy is produced by the `procedures.pr_draft` hook. Kanbus sends a verified evidence bundle to the procedure, expects JSON with `title` and `body`, then validates the result before `gh pr create`.

The built-in and repository default use a deterministic Tactus procedure for PR drafting. Each invocation receives isolated Tactus file storage under the worker workspace, keyed by the Kanbus run id. The procedure formats verified Kanbus evidence into PR text before Kanbus validates the draft. Kanbus still owns publication and enforces:

- Conventional Commit PR titles.
- Required body sections: `Summary`, `Why`, `Validation`, `Expected Outcome`, and `Kanbus / Task Tracking`.
- No absolute local paths.
- No validation claims unless the configured validation command appears in the body.
- The assigned Kanbus issue id and run id must be present.
