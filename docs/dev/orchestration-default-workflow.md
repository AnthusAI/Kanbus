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

Task-specific details belong in the Kanbus issue title and description. Workflow files describe project policy: target branch, validation command, publish mode, workspace root, branch naming, and generic worker rules.

The repository default workflow lives at `workflows/default.md`.
