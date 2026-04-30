This workflow is installed as the reusable preset:

```bash
call-criteria/poetry-upgrade
```

Run it by name:

```bash
kbs worker run <issue-id> \
  --workflow call-criteria/poetry-upgrade \
  --target-repo /Users/derek.norrbom/Projects/Call-Criteria-Python
```

Workflow preset source: `workflows/call-criteria/poetry-upgrade.md`.

The Markdown below is the preset content.

---
target:
  repo: /Users/derek.norrbom/Projects/Call-Criteria-Python
  branch: develop
  validation: POETRY_PYTHON=/opt/homebrew/bin/python3.11 ./scripts/cc-prod && poetry run make test
  publish: push-only
  allowed_paths:
    - pyproject.toml
    - poetry.lock
workspace:
  root: ~/.kanbus/orchestration-workspaces
worker:
  branch_pattern: agent/{{ issue.identifier }}/{{ run.short_id }}
codex:
  command: codex app-server
  timeout_seconds: 3600
---
You are working on the Call Criteria Python repository through Kanbus orchestration.

Issue:
- Identifier: {{ issue.identifier }}
- Run: {{ run.id }}
- Title: {{ issue.title }}
- Description: {{ issue.description }}

Rules:
- Work only in the isolated workspace supplied by the App Server.
- The assigned Kanbus issue is supplied by the orchestrator. Do not create, update, or close Kanbus issues from inside the target workspace.
- Do not modify files under project/issues, project/events, or project/runs.
- Modify only files required by the issue.
- Do not run git add, git commit, git push, or open a PR. Kanbus orchestration handles commit and push after validation.
- Do not alter production behavior.
- Run `make test` before finishing.
- Do not open a PR or merge anything.
