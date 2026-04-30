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

1. If the current Kanbus project has `workflows/default.md`, Kanbus uses it.
2. Otherwise Kanbus uses the built-in generic workflow.

Task-specific details belong in the Kanbus issue title and description. Workflow files describe project policy: target branch, validation command, publish mode, workspace root, branch naming, generic worker rules, and bounded procedure hooks.

The repository default workflow lives at `workflows/default.md`.

Pull request copy is produced by the `procedures.pr_draft` hook. Kanbus sends a verified evidence bundle to the procedure, expects JSON with `title` and `body`, then validates the result before `gh pr create`.

The built-in and repository default use a Tactus procedure for PR drafting. Each invocation receives isolated Tactus file storage under the worker workspace, keyed by the Kanbus run id. Kanbus still owns publication and enforces:

- Conventional Commit PR titles.
- Required body sections: `Summary`, `Why`, `Validation`, `Expected Outcome`, and `Kanbus / Task Tracking`.
- No absolute local paths.
- No validation claims unless the configured validation command appears in the body.
- The assigned Kanbus issue id and run id must be present.
