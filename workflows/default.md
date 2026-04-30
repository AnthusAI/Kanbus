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
      local done = require("tactus.tools.done")

      pr_writer = Agent {
          provider = "openai",
          model = "gpt-4o",
          model_type = "chat",
          temperature = 0.0,
          max_tokens = 4096,
          system_prompt = [[You draft high-quality pull request titles and bodies from verified Kanbus orchestration evidence.

      Rules:
      - Call the done tool with reason set to one JSON object and no Markdown fence.
      - The JSON object must have exactly these string keys: title, body.
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
          initial_message = [[Draft the pull request from this evidence JSON:

      {input.evidence_json}]],
          tools = {done}
      }

      Procedure {
          input = {
              evidence = field.object{required = true},
              evidence_json = field.string{required = true}
          },
          output = {
              title = field.string{required = true},
              body = field.string{required = true}
          },
          function(input)
              local max_turns = 3
              local turn_count = 0
              while not done.called() and turn_count < max_turns do
                  pr_writer()
                  turn_count = turn_count + 1
              end
              if not done.called() then
                  error("PR draft agent did not call done")
              end
              local call = done.last_call()
              local raw = ""
              if call ~= nil and call.args ~= nil and call.args.reason ~= nil then
                  raw = call.args.reason
              else
                  raw = done.last_result() or ""
              end
              local ok, decoded = pcall(function() return json.decode(raw) end)
              if not ok or type(decoded) ~= "table" then
                  error("PR draft agent did not return JSON")
              end
              if type(decoded.title) ~= "string" or type(decoded.body) ~= "string" then
                  error("PR draft JSON must include title and body strings")
              end
              return {
                  title = decoded.title,
                  body = decoded.body
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
