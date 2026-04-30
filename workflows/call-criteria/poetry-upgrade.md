---
target:
  repo: /Users/derek.norrbom/Projects/Call-Criteria-Python
  branch: develop
  validation: poetry check --lock
  publish: pull-request
  allowed_paths:
    - pyproject.toml
    - poetry.lock
workspace:
  root: ~/.kanbus/orchestration-workspaces
worker:
  branch_pattern: agent/{{ issue.identifier }}/{{ run.short_id }}
codex:
  command: codex app-server
  timeout_seconds: 300
---
You are working on the Call Criteria Python repository through Kanbus orchestration.

Issue:
- Identifier: {{ issue.identifier }}
- Run: {{ run.id }}
- Title: {{ issue.title }}
- Description: {{ issue.description }}

Task:
Upgrade the requested Poetry dependency pin.

Rules:
- Work only in the isolated workspace supplied by Kanbus orchestration.
- The assigned Kanbus issue is supplied by the orchestrator. Do not create, update, or close Kanbus issues from inside the target workspace.
- Do not modify files under project/issues, project/events, or project/runs.
- Do not add or use requirements.txt.
- Use pyproject.toml and poetry.lock as the source of truth.
- Update only files required by the dependency pin upgrade.
- Do not change unrelated production behavior.
- Run the configured validation command before finishing.
- Do not run git add, git commit, git push, or open a PR. Kanbus orchestration handles commit and push after validation.
- Use only non-interactive commands. Do not start shell sessions or commands that require stdin.
- Do not open a PR or merge. Kanbus orchestration handles the configured publish mode after validation.
