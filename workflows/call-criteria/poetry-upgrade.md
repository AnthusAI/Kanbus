---
target:
  repo: /Users/derek.norrbom/Projects/Call-Criteria-Python
  branch: develop
  validation: POETRY_PYTHON=/opt/homebrew/bin/python3.11 ./scripts/cc-prod && poetry run make test
  publish: push-only
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

Task:
Upgrade the requested Poetry dependency pin.

Rules:
- Work only in the isolated workspace supplied by Kanbus orchestration.
- Do not add or use requirements.txt.
- Use pyproject.toml and poetry.lock as the source of truth.
- Update only files required by the dependency pin upgrade.
- Do not change unrelated production behavior.
- Run the configured validation command before finishing.
- Push the branch only.
- Do not open a PR or merge.
