---
target:
  repo: /Users/derek.norrbom/Projects/Call-Criteria-Python
  branch: develop
  validation: POETRY_PYTHON=/opt/homebrew/bin/python3.11 ./scripts/cc-prod && poetry run make test
  publish: push-only
workspace:
  root: /tmp/kanbus-maximus-workspaces
worker:
  branch_pattern: experiment/kanbus-maximus-{{ issue.identifier }}
codex:
  command: codex app-server
  timeout_seconds: 3600
---
You are working on the Call Criteria Python repository through Kanbus Maximus.

Issue:
- Identifier: {{ issue.identifier }}
- Title: {{ issue.title }}
- Description: {{ issue.description }}

Rules:
- Work only in the isolated workspace supplied by the App Server.
- Modify only the dedicated trial artifact requested by the issue.
- Do not alter production behavior.
- Run `make test` before finishing.
- Do not open a PR or merge anything.
