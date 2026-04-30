---
target:
  branch: develop
  validation: git diff --check
  publish: pull-request
workspace:
  root: ~/.kanbus/orchestration-workspaces
worker:
  branch_pattern: agent/{{ issue.identifier }}/{{ run.short_id }}
codex:
  command: codex app-server
  timeout_seconds: 300
procedures:
  pr_draft:
    runtime: tactus
    timeout_seconds: 120
    source: |
      local json = require("tactus.io.json")

      pr_writer = Agent {
          provider = "openai",
          model = "gpt-4o",
          system_prompt = [[You draft high-quality pull request titles and bodies from verified Kanbus orchestration evidence.

      Rules:
      - Return only structured output matching the schema.
      - Title must use Conventional Commit style.
      - Body must use these exact Markdown headings:
        **Summary**
        **Why**
        **Validation**
        **Expected Outcome**
        **Kanbus / Task Tracking**
      - Use repository-relative paths only.
      - Never include absolute local paths.
      - Do not invent validation commands or results.
      - Include the Kanbus issue id and run id.
      - Be concise, factual, and reviewer-focused.]],
          output = {
              title = field.string{required = true},
              body = field.string{required = true}
          }
      }

      Procedure {
          input = {
              evidence = field.object{required = true}
          },
          output = {
              title = field.string{required = true},
              body = field.string{required = true}
          },
          function(input)
              local evidence_json = json.encode(input.evidence)
              local result = pr_writer(evidence_json)
              return {
                  title = result.output.title,
                  body = result.output.body
              }
          end
      }
---
You are working in an isolated workspace for the assigned Kanbus issue.

Issue:
- Identifier: {{ issue.identifier }}
- Run: {{ run.id }}
- Title: {{ issue.title }}
- Type: {{ issue.issue_type }}
- Description:
{{ issue.description }}

Rules:
- Use the issue title and description as the source of truth for the task.
- Work only in the isolated workspace supplied by Kanbus orchestration.
- The assigned Kanbus issue is supplied by the orchestrator. Do not create, update, or close Kanbus issues from inside the target workspace.
- You may comment only on the assigned Kanbus issue when useful.
- Do not modify files under project/issues, project/events, or project/runs.
- Do not run git add, git commit, git push, gh pr create, or merge. Kanbus orchestration handles publication after validation.
- Use only non-interactive commands. Do not start shell sessions or commands that require stdin.
- Keep changes scoped to the assigned issue.
- Run the validation that is appropriate for the change before finishing.
